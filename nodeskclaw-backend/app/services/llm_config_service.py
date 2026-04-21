"""LLM config service: read/write openclaw.json via kubectl exec."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from urllib.parse import urlparse as _urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_nodeskclaw_webhook_base_url, settings
from app.core.exceptions import AppException, BadRequestError
from app.models.base import not_deleted
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.models.instance_provider_config import InstanceProviderConfig
from app.models.org_llm_key import OrgModelProvider
from app.models.user_llm_key import UserLlmKey
from app.schemas.llm import OpenClawConfigResponse, OpenClawProviderEntry
from app.services.codex_provider import is_codex_provider, mask_personal_key, normalize_selected_models
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient
from app.services.nfs_mount import NFSMountError, RemoteFS, remote_fs
from app.utils.jsonc import ensure_exec_security, strip_jsonc

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_REL = Path(".openclaw") / "openclaw.json"

PROVIDER_BASE_URLS: dict[str, str] = {
    "codex": "",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "minimax-openai": "https://api.minimaxi.com/v1",
    "minimax-anthropic": "https://api.minimaxi.com/anthropic",
}

BUILTIN_PROVIDERS = {"openai", "anthropic", "gemini", "openrouter"}

PROVIDER_API_TYPE: dict[str, str] = {
    "codex": "openai-completions",
    "gemini": "google-generative-ai",
    "minimax-openai": "openai-completions",
    "minimax-anthropic": "anthropic-messages",
}

TRUSTED_PROXY_CIDRS = ["10.0.0.0/8", "100.64.0.0/10", "192.168.0.0/16"]
NODESKCLAW_TOOL_NAMES = (
    "nodeskclaw_blackboard",
    "nodeskclaw_topology",
    "nodeskclaw_performance",
    "nodeskclaw_proposals",
    "nodeskclaw_gene_discovery",
    "nodeskclaw_file_download",
    "nodeskclaw_chat_history",
)


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


def _build_providers_config(
    configs: list,
    wp_api_key: str,
    user_keys: dict[str, UserLlmKey],
    *,
    org_keys: dict[str, OrgModelProvider] | None = None,
    use_external_proxy: bool = False,
) -> dict:
    """Build the models.providers section for openclaw.json.

    configs: objects with .provider, .key_source, .selected_models
    (InstanceProviderConfig ORM or InstanceProviderConfigItem schema both work).
    Optionally reads .base_url / .api_type from config objects directly.
    """
    org_keys = org_keys or {}
    if use_external_proxy:
        proxy_url = (settings.LLM_PROXY_URL or "").rstrip("/")
    else:
        proxy_url = (settings.LLM_PROXY_INTERNAL_URL or settings.LLM_PROXY_URL or "").rstrip("/")
    providers: dict = {}
    for cfg in configs:
        provider = cfg.provider
        cfg_base_url = getattr(cfg, "base_url", None)
        cfg_api_type = getattr(cfg, "api_type", None)
        if is_codex_provider(provider):
            if not proxy_url:
                logger.error("LLM_PROXY_URL 未配置，Codex 模式无法生成 proxy URL")
                continue
            entry = {
                "baseUrl": f"{proxy_url}/{provider}/v1",
                "apiKey": wp_api_key,
            }
        elif cfg.key_source == "personal":
            uk = user_keys.get(provider)
            if not uk:
                logger.warning("个人 Key 缺失，跳过 provider=%s", provider)
                continue
            entry: dict = {
                "baseUrl": cfg_base_url or uk.base_url or PROVIDER_BASE_URLS.get(provider, ""),
                "apiKey": uk.api_key,
            }
        else:
            ok = org_keys.get(provider)
            if proxy_url:
                api_type = cfg_api_type or PROVIDER_API_TYPE.get(provider)
                skip_v1 = api_type in ("anthropic-messages", "google-generative-ai")
                entry = {
                    "baseUrl": f"{proxy_url}/{provider}" if skip_v1 else f"{proxy_url}/{provider}/v1",
                    "apiKey": wp_api_key,
                }
            else:
                if not ok:
                    raise AppException(
                        code=50001,
                        message=f"未找到团队 Provider 配置: {provider}",
                        status_code=500,
                    )
                entry = {
                    "baseUrl": cfg_base_url or ok.base_url or PROVIDER_BASE_URLS.get(provider, ""),
                    "apiKey": ok.api_key,
                }

        uk = user_keys.get(provider)
        ok = org_keys.get(provider)
        api_type = cfg_api_type or PROVIDER_API_TYPE.get(provider) or (uk.api_type if uk else None) or (ok.api_type if ok else None)
        if api_type:
            entry["api"] = api_type

        selected_models = normalize_selected_models(provider, cfg.selected_models)
        entry["models"] = _to_openclaw_models(selected_models) if selected_models else []

        providers[provider] = entry
    return providers


def _docker_rewrite_urls(providers: dict) -> dict:
    """Docker 实例使用宿主机可达地址，避免依赖主 compose 网络内的服务名。"""
    proxy_internal_url = (settings.LLM_PROXY_INTERNAL_URL or "").rstrip("/")
    proxy_external_url = _docker_rewrite_url((settings.LLM_PROXY_URL or "").rstrip("/"))
    for _provider_id, entry in providers.items():
        base_url = entry.get("baseUrl", "")
        if base_url:
            if proxy_internal_url and proxy_external_url and base_url.startswith(proxy_internal_url):
                entry["baseUrl"] = f"{proxy_external_url}{base_url[len(proxy_internal_url):]}"
            else:
                entry["baseUrl"] = _docker_rewrite_url(base_url)
    return providers


def _to_openclaw_models(selected: list[dict]) -> list[dict]:
    """Convert stored model metadata to OpenClaw models array format."""
    result = []
    for m in selected:
        item: dict = {"id": m["id"], "name": m.get("name", m["id"])}
        if m.get("context_window"):
            item["contextWindow"] = m["context_window"]
        if m.get("max_tokens"):
            item["maxTokens"] = m["max_tokens"]
        result.append(item)
    return result


async def _get_running_pod(k8s: K8sClient, instance: Instance) -> str | None:
    """Find a running Pod for the instance (only used by restart_runtime for kill)."""
    label_selector = f"app.kubernetes.io/name={_k8s_name(instance)}"
    pods = await k8s.list_pods(instance.namespace, label_selector)
    running = [p for p in pods if p["phase"] == "Running"]
    return running[0]["name"] if running else None


async def _get_k8s_client(instance: Instance, db: AsyncSession) -> K8sClient | None:
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, not_deleted(Cluster))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.is_k8s or not cluster.credentials_encrypted:
        return None
    api_client = await k8s_manager.get_or_create(cluster.id, cluster.credentials_encrypted)
    return K8sClient(api_client)



def _ensure_gateway_config(config: dict, instance: Instance) -> None:
    """Ensure gateway config is correct for reverse-proxy (Ingress) deployments.

    - gateway.auth.token: shared secret for Control UI WebSocket auth
    - gateway.auth.rateLimit: brute-force auth mitigation for non-loopback binds
    - gateway.trustedProxies: Ingress Controller IPs for header forwarding
    - gateway.controlUi.dangerouslyDisableDeviceAuth: skip device identity pairing
    - gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback: version-aware preserve
    """
    if "gateway" not in config:
        config["gateway"] = {}
    gw = config["gateway"]

    # gateway.token (legacy) -> gateway.auth.token
    gw.pop("token", None)
    if instance.proxy_token:
        gw.setdefault("auth", {})["token"] = instance.proxy_token

    auth = gw.setdefault("auth", {})
    if "rateLimit" not in auth:
        auth["rateLimit"] = {"maxAttempts": 10, "windowMs": 60000, "lockoutMs": 300000}

    if "trustedProxies" not in gw:
        gw["trustedProxies"] = list(TRUSTED_PROXY_CIDRS)

    control_ui = gw.setdefault("controlUi", {})
    control_ui["dangerouslyDisableDeviceAuth"] = True
    if "dangerouslyAllowHostHeaderOriginFallback" in control_ui:
        control_ui["dangerouslyAllowHostHeaderOriginFallback"] = True


def _set_default_agent_model(config: dict, providers: dict) -> None:
    """Set agents.defaults.model.primary from the first configured provider/model.

    OpenClaw uses this field to decide which model handles conversations.
    Format: "provider/model-id" (e.g. "minimax-openai/MiniMax-M2.5").
    """
    if not providers:
        return

    for provider_name, provider_cfg in providers.items():
        models = provider_cfg.get("models", [])
        if models:
            model_id = models[0].get("id", "")
            if model_id:
                primary = f"{provider_name}/{model_id}"
                agents = config.setdefault("agents", {})
                defaults = agents.setdefault("defaults", {})
                defaults["model"] = {"primary": primary}
                return

    logger.warning(
        "openclaw_llm_config: no model ids on configured providers, "
        "skipped updating agents.defaults.model",
    )


async def _read_config_file(fs: RemoteFS) -> dict | None:
    """Read openclaw.json from Pod via exec.

    Returns:
        dict  - parsed config on success
        None  - file doesn't exist (safe to create from scratch)

    Raises:
        ValueError - file exists but cannot be parsed (must NOT overwrite)
    """
    raw = await fs.read_text(str(OPENCLAW_CONFIG_REL))
    if raw is None:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(strip_jsonc(raw))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"openclaw.json 格式无法解析（已尝试去除注释）: {e}"
        ) from e


async def _write_config_file(fs: RemoteFS, data: dict) -> None:
    """Write openclaw.json to Pod via exec."""
    ensure_exec_security(data)
    await fs.write_text(
        str(OPENCLAW_CONFIG_REL),
        json.dumps(data, indent=2, ensure_ascii=False),
    )


async def read_openclaw_providers(
    instance: Instance, db: AsyncSession
) -> OpenClawConfigResponse:
    """Read openclaw.json via exec and enrich with DB key source info."""
    async with remote_fs(instance, db) as fs:
        try:
            raw_json = await _read_config_file(fs)
        except ValueError as e:
            logger.warning("读取 openclaw.json 解析失败: %s", e)
            raw_json = None

    if not raw_json:
        return OpenClawConfigResponse(data_source="nfs", providers=[])

    pod_providers: dict = raw_json.get("models", {}).get("providers", {})
    if not pod_providers:
        return OpenClawConfigResponse(data_source="nfs", providers=[])

    proxy_hosts = [
        h for h in (
            (settings.LLM_PROXY_INTERNAL_URL or "").rstrip("/"),
            (settings.LLM_PROXY_URL or "").rstrip("/"),
        ) if h
    ]

    ipc_result = await db.execute(
        select(InstanceProviderConfig).where(
            InstanceProviderConfig.instance_id == instance.id,
            not_deleted(InstanceProviderConfig),
        )
    )
    ipc_map = {c.provider: c for c in ipc_result.scalars().all()}

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
        is_proxy = any(h in base_url for h in proxy_hosts)

        key_source: str | None = None
        api_key_masked: str | None = None

        ipc = ipc_map.get(provider)
        if ipc:
            key_source = ipc.key_source
        elif is_proxy:
            key_source = "org"
        else:
            key_source = "personal"

        if key_source == "personal":
            uk = user_keys.get(provider)
            if uk:
                api_key_masked = mask_personal_key(uk.provider, uk.api_key)

        entries.append(OpenClawProviderEntry(
            provider=provider,
            base_url=base_url,
            is_proxy=is_proxy,
            key_source=key_source,
            api_key_masked=api_key_masked,
        ))

    return OpenClawConfigResponse(data_source="nfs", providers=entries)


def _from_openclaw_models(models: list[dict]) -> list[dict]:
    """Convert OpenClaw models array back to stored format (camelCase -> snake_case)."""
    result = []
    for m in models:
        item: dict = {"id": m["id"], "name": m.get("name", m["id"])}
        if m.get("contextWindow"):
            item["context_window"] = m["contextWindow"]
        if m.get("maxTokens"):
            item["max_tokens"] = m["maxTokens"]
        result.append(item)
    return result


async def read_instance_llm_configs(
    instance: Instance, db: AsyncSession, current_user_id: str,
) -> list[dict]:
    """Read LLM provider configs from DB (InstanceProviderConfig) + Pod openclaw.json.

    Returns a list of dicts suitable for InstanceProviderConfigEntry.
    """
    ipc_result = await db.execute(
        select(InstanceProviderConfig).where(
            InstanceProviderConfig.instance_id == instance.id,
            not_deleted(InstanceProviderConfig),
        )
    )
    ipc_map = {c.provider: c for c in ipc_result.scalars().all()}

    org_result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.org_id == instance.org_id,
            OrgModelProvider.is_active.is_(True),
            not_deleted(OrgModelProvider),
        )
    )
    org_providers = {op.provider for op in org_result.scalars().all()}

    user_keys_result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == current_user_id,
            not_deleted(UserLlmKey),
        )
    )
    user_keys = {k.provider: k for k in user_keys_result.scalars().all()}

    all_providers = set(ipc_map.keys()) if ipc_map else org_providers

    entries: list[dict] = []
    for provider in sorted(all_providers):
        ipc = ipc_map.get(provider)
        key_source = ipc.key_source if ipc else "org"
        selected_models = normalize_selected_models(
            provider, ipc.selected_models if ipc else None,
        )

        uk = user_keys.get(provider)
        personal_key_masked: str | None = None
        if key_source == "personal" and uk:
            personal_key_masked = mask_personal_key(uk.provider, uk.api_key)

        entries.append({
            "provider": provider,
            "key_source": key_source,
            "selected_models": selected_models,
            "personal_key_masked": personal_key_masked,
            "base_url": (ipc.base_url if ipc else None) or (uk.base_url if uk else None),
            "api_type": (ipc.api_type if ipc else None) or (uk.api_type if uk else None),
        })

    return entries


async def write_instance_llm_configs(
    instance: Instance, db: AsyncSession, configs: list, current_user_id: str,
) -> bool:
    """Write LLM provider configs to DB (InstanceProviderConfig) and Pod's openclaw.json.

    configs: list of InstanceProviderConfigItem (or anything with .provider, .key_source, .selected_models)

    Returns True if config was fully applied to the Pod, False if DB was committed
    but Pod write failed (pending — will be applied on next restart).
    """
    wp_api_key = instance.wp_api_key or ""

    existing_result = await db.execute(
        select(InstanceProviderConfig).where(
            InstanceProviderConfig.instance_id == instance.id,
            not_deleted(InstanceProviderConfig),
        )
    )
    existing_map = {ipc.provider: ipc for ipc in existing_result.scalars().all()}

    new_providers = set()
    for cfg in configs:
        new_providers.add(cfg.provider)
        selected_models = normalize_selected_models(cfg.provider, cfg.selected_models)
        cfg_base_url = getattr(cfg, "base_url", None)
        cfg_api_type = getattr(cfg, "api_type", None)
        existing = existing_map.get(cfg.provider)
        if existing:
            existing.key_source = cfg.key_source
            existing.selected_models = selected_models
            existing.base_url = cfg_base_url
            existing.api_type = cfg_api_type
        else:
            db.add(InstanceProviderConfig(
                instance_id=instance.id,
                provider=cfg.provider,
                key_source=cfg.key_source,
                selected_models=selected_models,
                base_url=cfg_base_url,
                api_type=cfg_api_type,
            ))

    for provider, ipc in existing_map.items():
        if provider not in new_providers:
            ipc.soft_delete()

    await db.commit()

    personal_providers = [c.provider for c in configs if c.key_source == "personal"]
    user_keys: dict[str, UserLlmKey] = {}
    if personal_providers:
        uk_result = await db.execute(
            select(UserLlmKey).where(
                UserLlmKey.user_id == current_user_id,
                UserLlmKey.provider.in_(personal_providers),
                not_deleted(UserLlmKey),
            )
        )
        user_keys = {k.provider: k for k in uk_result.scalars().all()}
    org_providers = [c.provider for c in configs if c.key_source == "org"]
    org_keys: dict[str, OrgModelProvider] = {}
    if org_providers:
        ok_result = await db.execute(
            select(OrgModelProvider).where(
                OrgModelProvider.org_id == instance.org_id,
                OrgModelProvider.provider.in_(org_providers),
                OrgModelProvider.is_active.is_(True),
                not_deleted(OrgModelProvider),
            )
        )
        org_keys = {k.provider: k for k in ok_result.scalars().all()}

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, not_deleted(Cluster))
    )
    cluster = cluster_result.scalar_one_or_none()
    use_external = bool(cluster and cluster.proxy_endpoint)

    providers = _build_providers_config(
        configs, wp_api_key, user_keys,
        org_keys=org_keys, use_external_proxy=use_external,
    )
    if configs and not providers:
        raise AppException(
            code=50001,
            message="未生成任何 LLM Provider 配置，请检查团队 Key / 个人 Key 配置",
            status_code=500,
        )
    if instance.compute_provider == "docker":
        _docker_rewrite_urls(providers)

    try:
        async with remote_fs(instance, db) as fs:
            try:
                existing_json = await _read_config_file(fs)
            except ValueError as e:
                logger.error("openclaw.json parse error, aborting write: %s", e)
                raise AppException(
                    code=50001,
                    message=f"openclaw.json parse error: {e}",
                    status_code=500,
                ) from e

            if existing_json is None:
                existing_json = {}

            if "models" not in existing_json:
                existing_json["models"] = {}
            existing_json["models"]["providers"] = providers

            _ensure_gateway_config(existing_json, instance)
            if "codex" in providers:
                existing_json["gateway"].setdefault("mode", "local")
            _set_default_agent_model(existing_json, providers)
            await _write_config_file(fs, existing_json)
    except NFSMountError:
        logger.warning(
            "Pod 不可用，LLM 配置已保存到 DB，标记 pending: instance=%s",
            instance.name,
        )
        instance.llm_config_pending = True
        await db.commit()
        return False

    instance.llm_config_pending = False
    logger.info(
        "write_instance_llm_configs: instance=%s providers=%s",
        instance.name, list(providers.keys()),
    )
    return True


async def sync_openclaw_llm_config(instance: Instance, db: AsyncSession) -> None:
    """Write LLM config to openclaw.json via NFS.

    Reads from InstanceProviderConfig + OrgModelProvider to build provider list.
    org  -> proxy URL + proxy token
    personal -> provider base URL + real API key
    """
    from types import SimpleNamespace

    ipc_result = await db.execute(
        select(InstanceProviderConfig).where(
            InstanceProviderConfig.instance_id == instance.id,
            not_deleted(InstanceProviderConfig),
        )
    )
    ipc_list = list(ipc_result.scalars().all())
    ipc_providers = {ipc.provider for ipc in ipc_list}

    org_result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.org_id == instance.org_id,
            OrgModelProvider.is_active.is_(True),
            not_deleted(OrgModelProvider),
        )
    )
    org_items = list(org_result.scalars().all())
    org_keys = {op.provider: op for op in org_items}
    org_providers = set(org_keys.keys())

    configs: list = list(ipc_list)
    for provider in (org_providers - ipc_providers) if not ipc_list else []:
        configs.append(SimpleNamespace(
            provider=provider,
            key_source="org",
            selected_models=None,
            base_url=None,
            api_type=None,
        ))

    if not configs:
        logger.info("实例 %s 无 LLM 配置，跳过写入", instance.name)
        return

    wp_api_key = instance.wp_api_key or ""

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

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, not_deleted(Cluster))
    )
    cluster = cluster_result.scalar_one_or_none()
    use_external = bool(cluster and cluster.proxy_endpoint)

    providers = _build_providers_config(
        configs, wp_api_key, user_keys,
        org_keys=org_keys, use_external_proxy=use_external,
    )
    if configs and not providers:
        raise AppException(
            code=50001,
            message="未生成任何 LLM Provider 配置，请检查团队 Key / 个人 Key 配置",
            status_code=500,
        )
    if instance.compute_provider == "docker":
        _docker_rewrite_urls(providers)

    async with remote_fs(instance, db) as fs:
        try:
            existing_json = await _read_config_file(fs)
        except ValueError as e:
            logger.error("openclaw.json 解析失败，中止写入以防覆盖原有配置: %s", e)
            raise AppException(
                code=50001,
                message=f"openclaw.json 无法解析，中止写入以保护现有配置: {e}",
                status_code=500,
            ) from e

        if existing_json is None:
            existing_json = {}

        if "models" not in existing_json:
            existing_json["models"] = {}
        existing_json["models"]["providers"] = providers

        _ensure_gateway_config(existing_json, instance)
        if "codex" in providers:
            existing_json["gateway"].setdefault("mode", "local")
        _set_default_agent_model(existing_json, providers)
        await _write_config_file(fs, existing_json)

    logger.info(
        "已写入 openclaw.json LLM 配置: instance=%s providers=%s",
        instance.name, list(providers.keys()),
    )


async def ensure_openclaw_gateway_config(instance: Instance, db: AsyncSession) -> None:
    """Ensure gateway.token and trustedProxies are in openclaw.json.

    Called after deployment succeeds to fix the case where the entrypoint
    skips config generation because the file already exists.
    """
    try:
        async with remote_fs(instance, db) as fs:
            try:
                existing = await _read_config_file(fs)
            except ValueError as e:
                logger.warning("ensure_gateway_config: 解析失败 %s", e)
                return
            if existing is None:
                existing = {}
            _ensure_gateway_config(existing, instance)
            await _write_config_file(fs, existing)
        logger.info("已注入 gateway 配置: instance=%s", instance.name)
    except Exception as e:
        logger.warning("注入 gateway 配置失败（非致命）: %s", e)


CHANNEL_PLUGIN_DIR = "openclaw-channel-nodeskclaw"
PLUGIN_FILES = [
    "index.ts",
    "package.json",
    "openclaw.plugin.json",
    "src/channel.ts",
    "src/runtime.ts",
    "src/types.ts",
    "src/tunnel-client.ts",
    "src/tools.ts",
]


def _get_plugin_source_dir() -> Path:
    """Locate the channel plugin source directory relative to project root."""
    candidates = [
        Path(__file__).resolve().parents[3] / CHANNEL_PLUGIN_DIR,
        Path("/app") / CHANNEL_PLUGIN_DIR,
    ]
    for p in candidates:
        if p.exists() and (p / "index.ts").exists():
            return p
    raise FileNotFoundError(
        f"Channel plugin source not found. Checked: {[str(c) for c in candidates]}"
    )


async def _deploy_plugin_files_generic(
    fs: RemoteFS, source_dir: Path, spec: ChannelPluginSpec,
) -> None:
    """Copy channel plugin files to the Pod and write a content hash marker."""
    target_base = f".openclaw/extensions/{spec.dir_name}"
    await fs.mkdir(f"{target_base}/src")

    for rel_path in spec.file_list:
        src = source_dir / rel_path
        if src.exists():
            await fs.write_text(
                f"{target_base}/{rel_path}",
                src.read_text(encoding="utf-8"),
            )

    content_hash = _get_plugin_hash(spec.plugin_id)
    if content_hash:
        await fs.write_text(f"{target_base}/.plugin-hash", content_hash)


async def _deploy_plugin_files(fs: RemoteFS, plugin_source: Path) -> None:
    """Copy nodeskclaw channel plugin files (backward-compat wrapper)."""
    await _deploy_plugin_files_generic(
        fs, plugin_source, CHANNEL_PLUGIN_REGISTRY["nodeskclaw"],
    )


def _docker_rewrite_url(url: str) -> str:
    """Docker 容器内 localhost/127.0.0.1 不可达宿主机，替换为 host.docker.internal。"""
    return re.sub(
        r"(https?://|wss?://)(localhost|127\.0\.0\.1)(:\d+)?",
        r"\1host.docker.internal\3",
        url,
    )


def _make_account_entry(instance: Instance, workspace_id: str) -> dict:
    """Build a single nodeskclaw account entry for a workspace."""
    api_url = settings.AGENT_API_BASE_URL
    if instance.compute_provider == "docker":
        api_url = _docker_rewrite_url(api_url)
    elif instance.compute_provider == "k8s":
        parsed = _urlparse(api_url)
        if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise BadRequestError(
                message="AGENT_API_BASE_URL 当前为 localhost，K8s 实例无法回连。",
                message_key="errors.deploy.localhost_not_reachable",
            )
    _env = json.loads(instance.env_vars or "{}")
    return {
        "enabled": True,
        "apiUrl": api_url,
        "workspaceId": workspace_id,
        "instanceId": instance.id,
        "apiToken": _env.get("GATEWAY_TOKEN") or _env.get("OPENCLAW_GATEWAY_TOKEN", ""),
    }


def _inject_channel_config(
    config: dict,
    instance: Instance,
    workspace_id: str,
) -> None:
    """Inject nodeskclaw channel config and plugin load path into openclaw.json.

    Preserves existing accounts; adds or updates the given workspace_id account.
    """
    if "channels" not in config:
        config["channels"] = {}
    ch = config["channels"].setdefault("nodeskclaw", {})
    if settings.TUNNEL_BASE_URL:
        tunnel_url = settings.TUNNEL_BASE_URL
        if instance.compute_provider == "docker":
            tunnel_url = _docker_rewrite_url(tunnel_url)
        ch["tunnelUrl"] = tunnel_url
    accounts = ch.setdefault("accounts", {})
    entry = _make_account_entry(instance, workspace_id)
    accounts[workspace_id] = entry
    accounts["default"] = entry

    plugins = config.setdefault("plugins", {})
    load = plugins.setdefault("load", {})
    paths = load.setdefault("paths", [])
    old_relative = f".openclaw/extensions/{CHANNEL_PLUGIN_DIR}"
    if old_relative in paths:
        paths.remove(old_relative)
    plugin_path = f"/root/.openclaw/extensions/{CHANNEL_PLUGIN_DIR}"
    if plugin_path not in paths:
        paths.append(plugin_path)

    entries = plugins.setdefault("entries", {})
    entries["nodeskclaw"] = {"enabled": True}

    gw = config.setdefault("gateway", {})
    http_cfg = gw.setdefault("http", {})
    endpoints = http_cfg.setdefault("endpoints", {})
    endpoints["chatCompletions"] = {"enabled": True}

    tools_cfg = config.setdefault("tools", {})
    allow = tools_cfg.setdefault("allow", [])
    for tool_name in NODESKCLAW_TOOL_NAMES:
        if tool_name not in allow:
            allow.append(tool_name)

    skills = config.setdefault("skills", {})
    s_load = skills.setdefault("load", {})
    extra_dirs = s_load.setdefault("extraDirs", [])
    skills_dir = "/root/.openclaw/skills"
    if skills_dir not in extra_dirs:
        extra_dirs.append(skills_dir)


async def deploy_nodeskclaw_channel_plugin(
    instance: Instance, db: AsyncSession, workspace_id: str,
) -> None:
    """Deploy the nodeskclaw channel plugin to an OpenClaw instance via NFS.

    1. Copy plugin source files to .openclaw/extensions/
    2. Inject channel config + plugin load path into openclaw.json
    3. Ensure chatCompletions is enabled in gateway config
    """
    plugin_source = _get_plugin_source_dir()

    async with remote_fs(instance, db) as fs:
        await _deploy_plugin_files(fs, plugin_source)

        try:
            existing = await _read_config_file(fs)
        except ValueError as e:
            logger.error("deploy_channel_plugin: openclaw.json 解析失败: %s", e)
            raise

        if existing is None:
            existing = {}

        _inject_channel_config(existing, instance, workspace_id)
        _ensure_gateway_config(existing, instance)
        await _write_config_file(fs, existing)

    logger.info(
        "已部署 nodeskclaw channel plugin: instance=%s workspace=%s",
        instance.name, workspace_id,
    )


async def add_workspace_channel_account(
    instance: Instance, db: AsyncSession, workspace_id: str,
) -> None:
    """Add a workspace's account to nodeskclaw channel config without overwriting existing."""
    async with remote_fs(instance, db) as fs:
        try:
            existing = await _read_config_file(fs)
        except ValueError as e:
            logger.error("add_workspace_channel_account: openclaw.json 解析失败: %s", e)
            raise
        if existing is None:
            existing = {}

        ch = existing.setdefault("channels", {}).setdefault("nodeskclaw", {})
        accounts = ch.setdefault("accounts", {})
        entry = _make_account_entry(instance, workspace_id)
        accounts[workspace_id] = entry
        accounts["default"] = entry

        tools_cfg = existing.setdefault("tools", {})
        allow = tools_cfg.setdefault("allow", [])
        for tool_name in NODESKCLAW_TOOL_NAMES:
            if tool_name not in allow:
                allow.append(tool_name)

        _ensure_gateway_config(existing, instance)
        await _write_config_file(fs, existing)

    logger.info(
        "已添加 workspace channel account: instance=%s workspace=%s",
        instance.name, workspace_id,
    )


async def remove_workspace_channel_account(
    instance: Instance, db: AsyncSession, workspace_id: str,
) -> None:
    """Remove a workspace's account from nodeskclaw channel config."""
    try:
        async with remote_fs(instance, db) as fs:
            try:
                existing = await _read_config_file(fs)
            except ValueError:
                return
            if existing is None:
                return

            channels = existing.get("channels", {})
            ch = channels.get("nodeskclaw", {})
            accounts = ch.get("accounts", {})
            accounts.pop(workspace_id, None)
            default_acct = accounts.get("default")
            if isinstance(default_acct, dict) and default_acct.get("workspaceId") == workspace_id:
                remaining = [v for k, v in accounts.items()
                             if k != "default" and isinstance(v, dict)]
                if remaining:
                    accounts["default"] = dict(remaining[0])
                else:
                    accounts.pop("default", None)
            ws_accounts = [k for k in accounts if k != "default"]
            if not ws_accounts:
                channels.pop("nodeskclaw", None)
                paths = existing.get("plugins", {}).get("load", {}).get("paths", [])
                for p in (f"/root/.openclaw/extensions/{CHANNEL_PLUGIN_DIR}",
                          f".openclaw/extensions/{CHANNEL_PLUGIN_DIR}"):
                    if p in paths:
                        paths.remove(p)
                existing.get("plugins", {}).get("entries", {}).pop("nodeskclaw", None)

            await _write_config_file(fs, existing)
        logger.info(
            "已移除 workspace channel account: instance=%s workspace=%s",
            instance.name, workspace_id,
        )
    except Exception as e:
        logger.warning("移除 workspace channel account 失败（非致命）: %s", e)


async def remove_nodeskclaw_channel_plugin(
    instance: Instance, db: AsyncSession,
) -> None:
    """Remove nodeskclaw channel config from openclaw.json when agent leaves workspace."""
    try:
        async with remote_fs(instance, db) as fs:
            try:
                existing = await _read_config_file(fs)
            except ValueError:
                return
            if existing is None:
                return

            channels = existing.get("channels", {})
            channels.pop("nodeskclaw", None)

            paths = existing.get("plugins", {}).get("load", {}).get("paths", [])
            for p in (f"/root/.openclaw/extensions/{CHANNEL_PLUGIN_DIR}",
                      f".openclaw/extensions/{CHANNEL_PLUGIN_DIR}"):
                if p in paths:
                    paths.remove(p)

            existing.get("plugins", {}).get("entries", {}).pop("nodeskclaw", None)

            await _write_config_file(fs, existing)
        logger.info("已移除 nodeskclaw channel 配置: instance=%s", instance.name)
    except Exception as e:
        logger.warning("移除 channel 配置失败（非致命）: %s", e)


# ── Learning Channel Plugin ──────────────────────

LEARNING_PLUGIN_DIR = "openclaw-channel-learning"
LEARNING_PLUGIN_FILES = [
    "index.ts",
    "package.json",
    "openclaw.plugin.json",
    "src/channel.ts",
    "src/runtime.ts",
    "src/types.ts",
]


def _get_learning_plugin_source_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parents[3] / LEARNING_PLUGIN_DIR,
        Path("/app") / LEARNING_PLUGIN_DIR,
    ]
    for p in candidates:
        if p.exists() and (p / "index.ts").exists():
            return p
    raise FileNotFoundError(
        f"Learning plugin source not found. Checked: {[str(c) for c in candidates]}"
    )


async def _deploy_learning_plugin_files(fs: RemoteFS, plugin_source: Path) -> None:
    """Copy learning channel plugin files (backward-compat wrapper)."""
    await _deploy_plugin_files_generic(
        fs, plugin_source, CHANNEL_PLUGIN_REGISTRY["learning"],
    )


def _inject_learning_channel_config(
    config: dict,
    instance: Instance,
) -> None:
    if "channels" not in config:
        config["channels"] = {}

    callback_base = get_nodeskclaw_webhook_base_url()

    config["channels"]["learning"] = {
        "accounts": {
            "default": {
                "enabled": True,
                "callbackBaseUrl": callback_base,
                "instanceId": instance.id,
            }
        }
    }

    plugins = config.setdefault("plugins", {})
    load = plugins.setdefault("load", {})
    paths = load.setdefault("paths", [])
    old_relative = f".openclaw/extensions/{LEARNING_PLUGIN_DIR}"
    if old_relative in paths:
        paths.remove(old_relative)
    plugin_path = f"/root/.openclaw/extensions/{LEARNING_PLUGIN_DIR}"
    if plugin_path not in paths:
        paths.append(plugin_path)

    entries = plugins.setdefault("entries", {})
    entries["learning"] = {"enabled": True}


async def deploy_learning_channel_plugin(
    instance: Instance, db: AsyncSession,
) -> None:
    try:
        plugin_source = _get_learning_plugin_source_dir()
    except FileNotFoundError:
        logger.warning("Learning plugin source not found, skipping deployment")
        return

    async with remote_fs(instance, db) as fs:
        await _deploy_learning_plugin_files(fs, plugin_source)

        try:
            existing = await _read_config_file(fs)
        except ValueError as e:
            logger.error("deploy_learning_plugin: openclaw.json parse error: %s", e)
            raise

        if existing is None:
            existing = {}

        _inject_learning_channel_config(existing, instance)
        await _write_config_file(fs, existing)

    logger.info("已部署 learning channel plugin: instance=%s", instance.name)


# ── DingTalk Channel Plugin ──────────────────────

DINGTALK_PLUGIN_DIR = "openclaw-channel-dingtalk"
DINGTALK_PLUGIN_FILES = [
    "index.ts",
    "package.json",
    "openclaw.plugin.json",
    "src/channel.ts",
    "src/runtime.ts",
    "src/types.ts",
    "src/stream.ts",
    "src/send.ts",
]


def _get_dingtalk_plugin_source_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parents[3] / DINGTALK_PLUGIN_DIR,
        Path("/app") / DINGTALK_PLUGIN_DIR,
    ]
    for p in candidates:
        if p.exists() and (p / "index.ts").exists():
            return p
    raise FileNotFoundError(
        f"DingTalk plugin source not found. Checked: {[str(c) for c in candidates]}"
    )


async def _deploy_dingtalk_plugin_files(fs: RemoteFS, plugin_source: Path) -> None:
    """Copy dingtalk channel plugin files (backward-compat wrapper)."""
    await _deploy_plugin_files_generic(
        fs, plugin_source, CHANNEL_PLUGIN_REGISTRY["dingtalk"],
    )


def _inject_dingtalk_plugin_path(config: dict) -> None:
    plugins = config.setdefault("plugins", {})
    load = plugins.setdefault("load", {})
    paths = load.setdefault("paths", [])
    old_relative = f".openclaw/extensions/{DINGTALK_PLUGIN_DIR}"
    if old_relative in paths:
        paths.remove(old_relative)
    plugin_path = f"/root/.openclaw/extensions/{DINGTALK_PLUGIN_DIR}"
    if plugin_path not in paths:
        paths.append(plugin_path)

    entries = plugins.setdefault("entries", {})
    entries["dingtalk"] = {"enabled": True}


async def deploy_dingtalk_channel_plugin(
    instance: Instance, db: AsyncSession,
) -> None:
    try:
        plugin_source = _get_dingtalk_plugin_source_dir()
    except FileNotFoundError:
        logger.warning("DingTalk plugin source not found, skipping deployment")
        return

    async with remote_fs(instance, db) as fs:
        await _deploy_dingtalk_plugin_files(fs, plugin_source)

        try:
            existing = await _read_config_file(fs)
        except ValueError as e:
            logger.error("deploy_dingtalk_plugin: openclaw.json parse error: %s", e)
            raise

        if existing is None:
            existing = {}

        _inject_dingtalk_plugin_path(existing)
        await _write_config_file(fs, existing)

    logger.info("已部署 dingtalk channel plugin: instance=%s", instance.name)


# ── Channel Plugin Registry & Auto-Sync ──────────────────────


@dataclass(frozen=True)
class ChannelPluginSpec:
    plugin_id: str
    dir_name: str
    file_list: tuple[str, ...]
    min_openclaw_version: tuple[int, ...]


CHANNEL_PLUGIN_REGISTRY: dict[str, ChannelPluginSpec] = {
    "nodeskclaw": ChannelPluginSpec(
        plugin_id="nodeskclaw",
        dir_name=CHANNEL_PLUGIN_DIR,
        file_list=tuple(PLUGIN_FILES),
        min_openclaw_version=(2026, 1, 0),
    ),
    "learning": ChannelPluginSpec(
        plugin_id="learning",
        dir_name=LEARNING_PLUGIN_DIR,
        file_list=tuple(LEARNING_PLUGIN_FILES),
        min_openclaw_version=(2026, 1, 0),
    ),
    "dingtalk": ChannelPluginSpec(
        plugin_id="dingtalk",
        dir_name=DINGTALK_PLUGIN_DIR,
        file_list=tuple(DINGTALK_PLUGIN_FILES),
        min_openclaw_version=(2026, 1, 0),
    ),
}


def _find_plugin_source_dir(dir_name: str) -> Path | None:
    """Locate a channel plugin source directory. Returns None if not found."""
    candidates = [
        Path(__file__).resolve().parents[3] / dir_name,
        Path("/app") / dir_name,
    ]
    for p in candidates:
        if p.exists() and (p / "index.ts").exists():
            return p
    return None


@cache
def _get_plugin_hash(plugin_id: str) -> str | None:
    """Compute content hash for a channel plugin (lazy, cached).

    Returns 16-char hex digest, or None if source dir not found.
    """
    spec = CHANNEL_PLUGIN_REGISTRY.get(plugin_id)
    if not spec:
        return None
    source_dir = _find_plugin_source_dir(spec.dir_name)
    if source_dir is None:
        return None
    h = hashlib.sha256()
    for rel_path in sorted(spec.file_list):
        src = source_dir / rel_path
        if src.exists():
            h.update(rel_path.encode())
            h.update(src.read_bytes())
    return h.hexdigest()[:16]


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse '2026.4.8' or 'v2026.4.8' into a comparable tuple.

    Returns (0,) on parse failure — treated as "unknown, allow sync".
    """
    if not version_str:
        return (0,)
    cleaned = version_str.lstrip("v")
    try:
        return tuple(int(x) for x in cleaned.split("."))
    except (ValueError, TypeError):
        return (0,)


async def _check_plugin_stale(
    fs: RemoteFS, spec: ChannelPluginSpec,
) -> bool | None:
    """Check if a deployed plugin needs updating.

    Returns:
        True  - plugin is deployed but hash mismatches (stale)
        False - plugin is deployed and hash matches (up-to-date)
        None  - plugin is not deployed on this instance
    """
    target_base = f".openclaw/extensions/{spec.dir_name}"
    expected_hash = _get_plugin_hash(spec.plugin_id)
    if expected_hash is None:
        return None

    try:
        remote_hash = (await fs.read_text(f"{target_base}/.plugin-hash")).strip()
        return remote_hash != expected_hash
    except Exception:
        pass

    try:
        await fs.read_text(f"{target_base}/index.ts")
        return True
    except Exception:
        return None


async def _sync_stale_plugins(
    fs: RemoteFS, instance: Instance,
) -> list[str]:
    """Check all registered plugins and re-deploy stale ones.

    Respects the version guard: skips sync if the instance's OpenClaw version
    is lower than the plugin's min_openclaw_version.

    Returns list of plugin_ids that were actually updated.
    """
    instance_version = _parse_version(instance.image_version)
    updated: list[str] = []

    for plugin_id, spec in CHANNEL_PLUGIN_REGISTRY.items():
        if _get_plugin_hash(plugin_id) is None:
            continue

        stale = await _check_plugin_stale(fs, spec)
        if stale is None or stale is False:
            continue

        if instance_version >= spec.min_openclaw_version:
            source_dir = _find_plugin_source_dir(spec.dir_name)
            if source_dir is None:
                continue
            await _deploy_plugin_files_generic(fs, source_dir, spec)
            updated.append(plugin_id)
            logger.info(
                "Plugin %s 已同步: instance=%s", plugin_id, instance.name,
            )
        else:
            logger.warning(
                "Plugin %s 要求 OpenClaw >= %s，实例 %s 运行 %s，跳过同步",
                plugin_id,
                ".".join(str(x) for x in spec.min_openclaw_version),
                instance.name,
                instance.image_version,
            )

    return updated


async def restart_runtime(instance: Instance, db: AsyncSession) -> dict:
    """Restart runtime process (config is assumed to be already written by the caller).

    Strategy: try graceful SIGTERM first; if exec fails (pod crashed / not ready),
    fall back to Deployment rolling restart.
    Docker: delegate to DockerComputeProvider.restart_instance.

    When instance.llm_config_pending is True, runs the force-reconfig recovery:
    1. Inject OPENCLAW_FORCE_RECONFIG=true env → rolling restart → Pod starts with clean config
    2. sync_openclaw_llm_config writes correct config from DB to Pod
    3. Remove FORCE_RECONFIG env → second rolling restart → Pod reads correct config
    4. Clear llm_config_pending flag
    """
    if instance.runtime == "openclaw":
        try:
            async with remote_fs(instance, db) as fs:
                updated = await _sync_stale_plugins(fs, instance)
                if updated:
                    logger.info(
                        "restart_runtime: 已同步 plugin %s: instance=%s",
                        updated, instance.name,
                    )
        except Exception as e:
            logger.warning(
                "restart_runtime: plugin 同步失败（不阻断重启）: instance=%s error=%s",
                instance.name, e,
            )

    if instance.compute_provider == "docker":
        return await _restart_runtime_docker(instance)

    k8s = await _get_k8s_client(instance, db)
    if k8s is None:
        return {"status": "error", "message": "集群不可用"}

    deploy_name = _k8s_name(instance)

    if instance.llm_config_pending:
        return await _restart_with_force_reconfig(instance, db, k8s, deploy_name)

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

    result = await _poll_pod_ready(k8s, instance.namespace, deploy_name)
    if result:
        logger.info("实例 %s Runtime 重启完成 (via %s)", instance.name, restarted_via)
        return {"status": "ok", "message": "重启完成"}

    return {"status": "timeout", "message": "重启超时（60s），请检查实例状态"}


async def _poll_pod_ready(
    k8s: K8sClient, namespace: str, deploy_name: str, max_rounds: int = 30,
) -> bool:
    """Poll until a Running+Ready Pod appears. Returns True on success."""
    for _ in range(max_rounds):
        await asyncio.sleep(2)
        pods = await k8s.list_pods(namespace, f"app.kubernetes.io/name={deploy_name}")
        for p in pods:
            if p["phase"] == "Running" and all(
                c.get("ready", False) for c in p.get("containers", [])
            ):
                return True
    return False


async def _restart_with_force_reconfig(
    instance: Instance, db: AsyncSession, k8s: K8sClient, deploy_name: str,
) -> dict:
    """Recovery path: Pod crashed due to bad config on PVC.

    Phase 1: FORCE_RECONFIG env → rolling restart → Pod starts with clean template config
    Phase 2: sync_openclaw_llm_config writes correct config from DB
    Phase 3: remove FORCE_RECONFIG env → second rolling restart → Pod reads correct config
    Phase 4: clear llm_config_pending
    """
    ns = instance.namespace
    container_name = deploy_name

    logger.info(
        "force-reconfig 恢复流程开始: instance=%s deploy=%s",
        instance.name, deploy_name,
    )

    # Phase 1: inject FORCE_RECONFIG and trigger rolling restart
    await k8s.set_deployment_env(ns, deploy_name, container_name, "OPENCLAW_FORCE_RECONFIG", "true")
    logger.info("Phase 1: 已注入 OPENCLAW_FORCE_RECONFIG=true，等待 Pod Running")

    if not await _poll_pod_ready(k8s, ns, deploy_name):
        logger.error("force-reconfig Phase 1 超时: Pod 未恢复 Running")
        return {"status": "timeout", "message": "配置恢复超时（Phase 1: Pod 未启动），请检查实例状态"}

    # Phase 2: write correct LLM config from DB to Pod
    logger.info("Phase 2: Pod Running，开始写入正确的 LLM 配置")
    try:
        await sync_openclaw_llm_config(instance, db)
    except Exception as e:
        logger.error("force-reconfig Phase 2 exec 写入失败: %s", e)
        return {"status": "error", "message": f"配置恢复失败（Phase 2: 写入失败）: {e}"}

    # Phase 3: remove FORCE_RECONFIG → triggers second rolling restart with correct config
    logger.info("Phase 3: 移除 OPENCLAW_FORCE_RECONFIG，触发第二次滚动重启")
    await k8s.remove_deployment_env(ns, deploy_name, container_name, "OPENCLAW_FORCE_RECONFIG")

    if not await _poll_pod_ready(k8s, ns, deploy_name):
        logger.error("force-reconfig Phase 3 超时: 第二次 restart 后 Pod 未就绪")
        return {"status": "timeout", "message": "配置恢复超时（Phase 3: 重启未完成），请检查实例状态"}

    # Phase 4: clear pending flag
    instance.llm_config_pending = False
    await db.commit()
    logger.info("force-reconfig 恢复完成: instance=%s", instance.name)
    return {"status": "ok", "message": "配置已恢复并重启完成"}


async def _restart_runtime_docker(instance: Instance) -> dict:
    """Restart a runtime Docker container."""
    from app.services.instance_service import _build_docker_handle, _get_docker_provider
    try:
        provider = _get_docker_provider()
        handle = _build_docker_handle(instance)
        await provider.restart_instance(handle)
        logger.info("Docker 实例 %s Runtime 重启完成", instance.name)
        return {"status": "ok", "message": "重启完成"}
    except Exception as e:
        logger.error("Docker 实例 %s 重启失败: %s", instance.name, e)
        return {"status": "error", "message": f"Docker 重启失败: {e}"}


async def repair_channel_account_urls(db: AsyncSession) -> dict:
    """Repair channel accounts: fix apiUrl, workspaceId, sync plugin files.

    For each active instance in any workspace:
    1. Query WorkspaceAgent to get all workspace memberships
    2. Ensure each workspace has a correct account entry
    3. Set 'default' to the most recently joined workspace
    4. Fix apiUrl across all accounts
    5. Re-deploy plugin source files (tools.ts factory mode etc.)
    """
    from app.models.workspace_agent import WorkspaceAgent

    wa_result = await db.execute(
        select(WorkspaceAgent.instance_id)
        .where(WorkspaceAgent.deleted_at.is_(None))
        .distinct()
    )
    instance_ids = [r.instance_id for r in wa_result.all()]

    if not instance_ids:
        return {"repaired": [], "skipped": [], "failed": []}

    inst_result = await db.execute(
        select(Instance).where(
            Instance.id.in_(instance_ids),
            Instance.deleted_at.is_(None),
        )
    )
    instances = list(inst_result.scalars().all())

    new_api_url = settings.AGENT_API_BASE_URL
    repaired = []
    skipped = []
    failed = []

    for inst in instances:
        if inst.runtime != "openclaw":
            skipped.append({"id": inst.id, "name": inst.name, "reason": f"runtime={inst.runtime}"})
            continue
        try:
            ws_result = await db.execute(
                select(WorkspaceAgent.workspace_id)
                .where(
                    WorkspaceAgent.instance_id == inst.id,
                    WorkspaceAgent.deleted_at.is_(None),
                )
                .order_by(WorkspaceAgent.created_at.desc())
            )
            workspace_ids = [r.workspace_id for r in ws_result.all()]

            if not workspace_ids:
                skipped.append({"id": inst.id, "name": inst.name, "reason": "no workspace_agent"})
                continue

            async with remote_fs(inst, db) as fs:
                await _sync_stale_plugins(fs, inst)

                try:
                    config = await _read_config_file(fs)
                except ValueError as e:
                    failed.append({"id": inst.id, "name": inst.name, "error": f"parse: {e}"})
                    continue
                if config is None:
                    config = {}

                ch = config.setdefault("channels", {}).setdefault("nodeskclaw", {})
                accounts = ch.setdefault("accounts", {})

                changed = False

                for ws_id in workspace_ids:
                    correct = _make_account_entry(inst, ws_id)
                    existing = accounts.get(ws_id)
                    if not isinstance(existing, dict) or existing != correct:
                        accounts[ws_id] = correct
                        changed = True

                primary_entry = _make_account_entry(inst, workspace_ids[0])
                cur_default = accounts.get("default")
                if not isinstance(cur_default, dict) or cur_default != primary_entry:
                    accounts["default"] = primary_entry
                    changed = True

                for key, acct in list(accounts.items()):
                    if isinstance(acct, dict) and acct.get("apiUrl") != new_api_url:
                        acct["apiUrl"] = new_api_url
                        changed = True

                tools_cfg = config.setdefault("tools", {})
                allow = tools_cfg.setdefault("allow", [])
                for tool_name in NODESKCLAW_TOOL_NAMES:
                    if tool_name not in allow:
                        allow.append(tool_name)
                        changed = True

                if changed:
                    await _write_config_file(fs, config)
                    repaired.append({"id": inst.id, "name": inst.name, "workspaces": workspace_ids})
                else:
                    skipped.append({"id": inst.id, "name": inst.name, "reason": "already correct"})
        except Exception as e:
            failed.append({"id": inst.id, "name": inst.name, "error": str(e)})

    logger.info(
        "repair_channel_account_urls: repaired=%d skipped=%d failed=%d",
        len(repaired), len(skipped), len(failed),
    )
    return {"repaired": repaired, "skipped": skipped, "failed": failed}


async def startup_plugin_sync(db: AsyncSession) -> dict:
    """Scan all active OpenClaw instances and update stale plugin files.

    Called as a background task during backend startup.
    Only updates files — does NOT restart instances.
    """
    from app.models.workspace_agent import WorkspaceAgent

    wa_result = await db.execute(
        select(WorkspaceAgent.instance_id)
        .where(WorkspaceAgent.deleted_at.is_(None))
        .distinct()
    )
    instance_ids_with_workspace = {r.instance_id for r in wa_result.all()}

    if not instance_ids_with_workspace:
        logger.info("startup_plugin_sync: 无 WorkspaceAgent 记录，跳过")
        return {"updated": 0, "skipped": 0, "failed": 0}

    inst_result = await db.execute(
        select(Instance).where(
            Instance.id.in_(instance_ids_with_workspace),
            Instance.deleted_at.is_(None),
            Instance.runtime == "openclaw",
            Instance.status == "running",
        )
    )
    instances = list(inst_result.scalars().all())

    updated_count = 0
    skipped_count = 0
    failed_list: list[dict] = []

    for inst in instances:
        try:
            async with remote_fs(inst, db) as fs:
                updated = await _sync_stale_plugins(fs, inst)
                if updated:
                    updated_count += 1
                else:
                    skipped_count += 1
        except Exception as e:
            failed_list.append({"id": inst.id, "name": inst.name, "error": str(e)})
            logger.warning(
                "startup_plugin_sync: 实例 %s 同步失败: %s", inst.name, e,
            )

    logger.info(
        "startup_plugin_sync: updated=%d skipped=%d failed=%d",
        updated_count, skipped_count, len(failed_list),
    )
    return {
        "updated": updated_count,
        "skipped": skipped_count,
        "failed": len(failed_list),
    }
