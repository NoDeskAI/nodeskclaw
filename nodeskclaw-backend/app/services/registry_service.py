"""Registry service: fetch image tags from Docker Registry HTTP API v2.

支持两种认证方式：
1. Basic Auth（直接带用户名密码）
2. Bearer Token（Harbor 风格：先用 Basic Auth 换 Token，再用 Token 请求）
   容器镜像仓库 使用这种方式。
"""

import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RegistryError
from app.services.config_service import get_config
from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
REGISTRY_MODES = {"custom", "hosted"}


@dataclass(frozen=True)
class ResolvedRegistryConfig:
    mode: str
    image_registry: str | None
    username: str | None
    password: str | None

    @property
    def credentials(self) -> tuple[str, str] | None:
        if not self.username or not self.password:
            return None
        return self.username, self.password


def normalize_registry_repository(value: str | None) -> str | None:
    repository = (value or "").strip().rstrip("/")
    if not repository:
        return None
    if "://" in repository:
        repository = repository.split("://", 1)[1]
    return repository.rstrip("/") or None


async def resolve_registry_config(
    db: AsyncSession,
    runtime: str | None = None,
) -> ResolvedRegistryConfig:
    mode = (await get_config("registry_mode", db) or "custom").strip().lower()
    if mode not in REGISTRY_MODES:
        mode = "custom"

    if mode == "hosted":
        root = normalize_registry_repository(await get_config("hosted_registry_url", db))
        image_registry = f"{root}/deskclaw-{runtime}" if root and runtime else root
        return ResolvedRegistryConfig(
            mode=mode,
            image_registry=image_registry,
            username=await get_config("hosted_registry_username", db),
            password=await get_config("hosted_registry_password", db),
        )

    image_registry: str | None = None
    if runtime:
        spec = RUNTIME_REGISTRY.get(runtime)
        if spec:
            image_registry = await get_config(spec.image_registry_key, db)
    if not image_registry:
        image_registry = await get_config("image_registry", db)
    return ResolvedRegistryConfig(
        mode=mode,
        image_registry=normalize_registry_repository(image_registry),
        username=await get_config("registry_username", db),
        password=await get_config("registry_password", db),
    )


async def resolve_image_registry(
    db: AsyncSession, runtime: str | None = None,
) -> str | None:
    """解析当前模式下指定引擎的完整镜像仓库地址。"""
    return (await resolve_registry_config(db, runtime)).image_registry


async def ensure_registry_pull_secret(
    k8s,
    namespace: str,
    config: ResolvedRegistryConfig,
) -> str | None:
    if not config.image_registry or not config.credentials:
        return None
    from app.services.k8s.resource_builder import REGISTRY_SECRET_NAME, build_registry_secret

    secret = build_registry_secret(
        namespace,
        config.image_registry,
        config.credentials[0],
        config.credentials[1],
    )
    await k8s.create_or_skip(k8s.core.create_namespaced_secret, namespace, secret)
    return REGISTRY_SECRET_NAME


def _parse_www_authenticate(header: str) -> dict[str, str]:
    """解析 Www-Authenticate: Bearer realm="...",service="...",scope="..." 头。"""
    result: dict[str, str] = {}
    for match in re.finditer(r'(\w+)="([^"]*)"', header):
        result[match.group(1)] = match.group(2)
    return result


async def _get_bearer_token(
    client: httpx.AsyncClient,
    www_auth: str,
    repo: str,
    credentials: tuple[str, str] | None,
) -> str | None:
    """根据 Www-Authenticate 头获取 Bearer Token（Harbor / 容器镜像仓库 认证流程）。"""
    params = _parse_www_authenticate(www_auth)
    realm = params.get("realm")
    if not realm:
        return None

    token_params = {"service": params.get("service", "")}
    # scope 未在 Www-Authenticate 中提供时，手动构造
    if "scope" in params:
        token_params["scope"] = params["scope"]
    else:
        token_params["scope"] = f"repository:{repo}:pull"

    kwargs: dict = {}
    if credentials:
        kwargs["auth"] = credentials

    try:
        resp = await client.get(realm, params=token_params, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        return data.get("token") or data.get("access_token")
    except Exception as e:
        logger.warning("获取 Bearer Token 失败: %s", e)
        return None


async def list_image_tags(
    db: AsyncSession,
    registry_url: str | None = None,
    runtime: str | None = None,
) -> list[dict]:
    """
    Query a Docker Registry v2 for available tags.
    Returns list of {"tag": str, "digest": str | None}.

    认证流程：
    1. 先尝试直接请求（可能带 Basic Auth）
    2. 如果返回 401 且有 Www-Authenticate: Bearer，走 Token 换取流程
    """
    resolved = await resolve_registry_config(db, runtime)
    credentials = resolved.credentials
    if registry_url:
        registry_url = normalize_registry_repository(registry_url)
        custom_username = await get_config("registry_username", db)
        custom_password = await get_config("registry_password", db)
        credentials = (
            (custom_username, custom_password)
            if custom_username and custom_password
            else None
        )
    else:
        registry_url = resolved.image_registry

    registry = (registry_url or "").strip().rstrip("/")
    if not registry:
        logger.warning("镜像仓库地址未配置 (runtime=%s)", runtime)
        return []

    if "://" in registry:
        url = registry
    else:
        url = f"https://{registry}"

    parts = url.split("/")
    if len(parts) >= 4:
        base_url = "/".join(parts[:3])
        repo = "/".join(parts[3:])
    else:
        base_url = url
        repo = "library/openclaw"

    if not repo:
        repo = "library/openclaw"

    tags_url = f"{base_url}/v2/{repo}/tags/list"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False, trust_env=False) as client:
            # 第一次请求
            resp = await client.get(tags_url)

            # 401 → 尝试认证
            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "")

                if "bearer" in www_auth.lower():
                    token = await _get_bearer_token(client, www_auth, repo, credentials)
                    if token:
                        resp = await client.get(
                            tags_url, headers={"Authorization": f"Bearer {token}"}
                        )
                elif credentials:
                    # 普通 Basic Auth
                    resp = await client.get(tags_url, auth=credentials)

            resp.raise_for_status()
            data = resp.json()
            raw_tags = data.get("tags") or []

            def _sort_key(t: str) -> tuple:
                """排序: latest 最前，其余按字符串倒序（日期类 tag 新的在前）。"""
                if t == "latest":
                    return (0, "")
                return (1, t)

            raw_tags.sort(key=_sort_key, reverse=False)
            # 除 latest 外倒序排列，让最新 tag 排在最前
            latest = [t for t in raw_tags if t == "latest"]
            others = sorted([t for t in raw_tags if t != "latest"], reverse=True)
            sorted_tags = latest + others
            return [{"tag": t, "digest": None} for t in sorted_tags]

    except httpx.HTTPStatusError as e:
        logger.warning("Registry 返回错误 %s: %s", e.response.status_code, tags_url)
        raise RegistryError(f"Registry 返回 HTTP {e.response.status_code}")
    except Exception as e:
        logger.warning("Registry 请求失败 (%s): %s", tags_url, e)
        raise RegistryError(f"Registry 请求失败: {e}")
