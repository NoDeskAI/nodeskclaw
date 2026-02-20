"""LLM config service: read/write openclaw.json via NFS mount."""

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.base import not_deleted
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.models.user_llm_config import UserLlmConfig
from app.models.user_llm_key import UserLlmKey
from app.schemas.llm import OpenClawConfigResponse, OpenClawProviderEntry
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient
from app.services.nfs_mount import nfs_mount

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_REL = Path(".openclaw") / "openclaw.json"

PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "minimax-openai": "https://api.minimax.chat/v1",
    "minimax-anthropic": "https://api.minimax.chat/v1",
}

BUILTIN_PROVIDERS = {"openai", "anthropic", "gemini", "openrouter"}

_MINIMAX_MODELS = [
    {"id": "MiniMax-M2.5", "name": "MiniMax M2.5", "reasoning": True, "input": ["text"], "contextWindow": 204800, "maxTokens": 32000},
    {"id": "MiniMax-M2.5-highspeed", "name": "MiniMax M2.5 Highspeed", "reasoning": True, "input": ["text"], "contextWindow": 204800, "maxTokens": 32000},
    {"id": "MiniMax-M2.1", "name": "MiniMax M2.1", "reasoning": True, "input": ["text"], "contextWindow": 204800, "maxTokens": 32000},
    {"id": "MiniMax-M2", "name": "MiniMax M2", "reasoning": True, "input": ["text"], "contextWindow": 204800, "maxTokens": 32000},
]

CUSTOM_PROVIDER_EXTRA: dict[str, dict] = {
    "minimax-openai": {
        "api": "openai-completions",
        "models": _MINIMAX_MODELS,
    },
    "minimax-anthropic": {
        "api": "anthropic-messages",
        "models": _MINIMAX_MODELS,
    },
}


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


def _build_providers_config(
    configs: list[UserLlmConfig],
    proxy_token: str,
    user_keys: dict[str, UserLlmKey],
) -> dict:
    """Build the models.providers section for openclaw.json.

    org  key_source  -> proxy URL + proxy token
    personal key_source -> provider base URL + user's real API key
    """
    host = settings.CLAWBUDDY_HOST.rstrip("/") if settings.CLAWBUDDY_HOST else ""
    providers: dict = {}
    for cfg in configs:
        provider = cfg.provider
        if cfg.key_source == "personal":
            uk = user_keys.get(provider)
            if not uk:
                logger.warning("个人 Key 缺失，跳过 provider=%s", provider)
                continue
            entry: dict = {
                "baseUrl": uk.base_url or PROVIDER_BASE_URLS.get(provider, ""),
                "apiKey": uk.api_key,
            }
        else:
            if host:
                base_url = f"{host}/llm-proxy/{provider}/v1"
            else:
                base_url = f"http://localhost:8000/llm-proxy/{provider}/v1"
            entry = {
                "baseUrl": base_url,
                "apiKey": proxy_token,
            }

        extra = CUSTOM_PROVIDER_EXTRA.get(provider)
        if extra:
            entry.update(extra)

        providers[provider] = entry
    return providers


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:6] + "***" + key[-3:]


async def _get_running_pod(k8s: K8sClient, instance: Instance) -> str | None:
    """Find a running Pod for the instance (only used by restart_openclaw for kill)."""
    label_selector = f"app.kubernetes.io/name={_k8s_name(instance)}"
    pods = await k8s.list_pods(instance.namespace, label_selector)
    running = [p for p in pods if p["phase"] == "Running"]
    return running[0]["name"] if running else None


async def _get_k8s_client(instance: Instance, db: AsyncSession) -> K8sClient | None:
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.kubeconfig_encrypted:
        return None
    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    return K8sClient(api_client)


def _read_config_file(mount_path: Path) -> dict:
    """Read openclaw.json from NFS mount, return empty dict if file doesn't exist."""
    config_path = mount_path / OPENCLAW_CONFIG_REL
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取 openclaw.json 失败: %s", e)
        return {}


def _write_config_file(mount_path: Path, data: dict) -> None:
    """Write openclaw.json to NFS mount. Permissions are fixed at mount time."""
    config_path = mount_path / OPENCLAW_CONFIG_REL
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def read_openclaw_providers(
    instance: Instance, db: AsyncSession
) -> OpenClawConfigResponse:
    """Read openclaw.json via NFS and enrich with DB key source info."""
    async with nfs_mount(instance, db) as mount_path:
        raw_json = _read_config_file(mount_path)

    pod_providers: dict = raw_json.get("models", {}).get("providers", {})
    if not pod_providers:
        return OpenClawConfigResponse(data_source="nfs", providers=[])

    host = (settings.CLAWBUDDY_HOST or "").rstrip("/")

    configs_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == instance.created_by,
            UserLlmConfig.org_id == instance.org_id,
            not_deleted(UserLlmConfig),
        )
    )
    db_configs = {c.provider: c for c in configs_result.scalars().all()}

    user_keys_result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == instance.created_by,
            not_deleted(UserLlmKey),
        )
    )
    user_keys = {k.provider: k for k in user_keys_result.scalars().all()}

    entries: list[OpenClawProviderEntry] = []
    for provider, prov_cfg in pod_providers.items():
        base_url = prov_cfg.get("baseUrl", "")
        is_proxy = bool(host) and host in base_url

        key_source: str | None = None
        api_key_masked: str | None = None

        db_cfg = db_configs.get(provider)
        if db_cfg:
            key_source = db_cfg.key_source
            if db_cfg.key_source == "personal":
                uk = user_keys.get(provider)
                if uk:
                    api_key_masked = _mask_key(uk.api_key)

        entries.append(OpenClawProviderEntry(
            provider=provider,
            base_url=base_url,
            is_proxy=is_proxy,
            key_source=key_source,
            api_key_masked=api_key_masked,
        ))

    return OpenClawConfigResponse(data_source="nfs", providers=entries)


async def sync_openclaw_llm_config(instance: Instance, db: AsyncSession) -> None:
    """Write LLM config to openclaw.json via NFS.

    org  -> proxy URL + proxy token
    personal -> provider base URL + real API key
    """
    configs_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == instance.created_by,
            UserLlmConfig.org_id == instance.org_id,
            not_deleted(UserLlmConfig),
        )
    )
    configs = list(configs_result.scalars().all())

    if not configs:
        logger.info("实例 %s 无 LLM 配置，跳过写入", instance.name)
        return

    proxy_token = instance.proxy_token or ""

    personal_providers = [c.provider for c in configs if c.key_source == "personal"]
    user_keys: dict[str, UserLlmKey] = {}
    if personal_providers:
        uk_result = await db.execute(
            select(UserLlmKey).where(
                UserLlmKey.user_id == instance.created_by,
                UserLlmKey.provider.in_(personal_providers),
                not_deleted(UserLlmKey),
            )
        )
        user_keys = {k.provider: k for k in uk_result.scalars().all()}

    has_org = any(c.key_source == "org" for c in configs)
    if has_org and not proxy_token:
        logger.warning("实例 %s 缺少 proxy_token，组织 Key 模式无法写入", instance.name)

    providers = _build_providers_config(configs, proxy_token, user_keys)

    async with nfs_mount(instance, db) as mount_path:
        existing_json = _read_config_file(mount_path)
        if "models" not in existing_json:
            existing_json["models"] = {}
        existing_json["models"]["providers"] = providers
        _write_config_file(mount_path, existing_json)

    logger.info(
        "已写入 openclaw.json LLM 配置 (NFS): instance=%s providers=%s",
        instance.name, list(providers.keys()),
    )


async def restart_openclaw(instance: Instance, db: AsyncSession) -> dict:
    """Update openclaw.json via NFS and restart OpenClaw.

    Strategy: try graceful SIGTERM first; if exec fails (pod crashed / not ready),
    fall back to Deployment rolling restart.
    """
    await sync_openclaw_llm_config(instance, db)

    k8s = await _get_k8s_client(instance, db)
    if k8s is None:
        return {"status": "error", "message": "集群不可用"}

    deploy_name = _k8s_name(instance)
    restarted_via = "sigterm"

    pod_name = await _get_running_pod(k8s, instance)
    if pod_name:
        try:
            await k8s.exec_in_pod(
                instance.namespace, pod_name,
                ["kill", "-SIGTERM", "1"],
            )
            logger.info("已发送 SIGTERM 到实例 %s 的 PID 1", instance.name)
        except Exception as e:
            logger.warning(
                "exec kill 失败 (pod=%s)，降级为 Deployment 滚动重启: %s",
                pod_name, e,
            )
            await k8s.restart_deployment(instance.namespace, deploy_name)
            restarted_via = "rollout"
    else:
        logger.info("无运行中的 Pod，触发 Deployment 滚动重启: %s", deploy_name)
        await k8s.restart_deployment(instance.namespace, deploy_name)
        restarted_via = "rollout"

    for _ in range(30):
        await asyncio.sleep(2)
        pods = await k8s.list_pods(
            instance.namespace,
            f"app.kubernetes.io/name={deploy_name}",
        )
        running = [p for p in pods if p["phase"] == "Running"]
        if running:
            for p in running:
                ready = all(c.get("ready", False) for c in p.get("containers", []))
                if ready:
                    logger.info("实例 %s OpenClaw 重启完成 (via %s)", instance.name, restarted_via)
                    return {"status": "ok", "message": "重启完成"}

    return {"status": "timeout", "message": "重启超时（60s），请检查实例状态"}
