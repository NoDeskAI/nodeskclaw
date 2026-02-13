"""Registry service: fetch image tags from Docker Registry HTTP API v2.

支持两种认证方式：
1. Basic Auth（直接带用户名密码）
2. Bearer Token（Harbor 风格：先用 Basic Auth 换 Token，再用 Token 请求）
   火山云 CR 使用这种方式。
"""

import logging
import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config_service import get_config

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0


async def _get_registry_auth(db: AsyncSession) -> tuple[str, str] | None:
    """从数据库读取镜像仓库的认证凭证，返回 (username, password)。"""
    username = await get_config("registry_username", db)
    password = await get_config("registry_password", db)
    if not username or not password:
        return None
    return (username, password)


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
    """根据 Www-Authenticate 头获取 Bearer Token（Harbor / 火山云 CR 认证流程）。"""
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
) -> list[dict]:
    """
    Query a Docker Registry v2 for available tags.
    Returns list of {"tag": str, "digest": str | None}.

    认证流程：
    1. 先尝试直接请求（可能带 Basic Auth）
    2. 如果返回 401 且有 Www-Authenticate: Bearer，走 Token 换取流程
    """
    if not registry_url:
        registry_url = await get_config("image_registry", db)

    registry = (registry_url or "").strip().rstrip("/")
    if not registry:
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
    credentials = await _get_registry_auth(db)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
            # 第一次请求
            resp = await client.get(tags_url)

            # 401 → 尝试认证
            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "")

                if "bearer" in www_auth.lower():
                    # Harbor / 火山云 CR 风格：Bearer Token 认证
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
                if t == "latest":
                    return (0, t)
                if t.startswith("v") and any(c.isdigit() for c in t):
                    return (1, t)
                return (2, t)

            raw_tags.sort(key=_sort_key)
            return [{"tag": t, "digest": None} for t in raw_tags]

    except httpx.HTTPStatusError as e:
        logger.warning("Registry 返回错误 %s: %s", e.response.status_code, tags_url)
        return []
    except Exception as e:
        logger.warning("Registry 请求失败 (%s): %s", tags_url, e)
        return []
