"""LLM config service: read/write openclaw.json via kubectl exec."""

import asyncio
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.base import not_deleted
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.models.user_llm_config import UserLlmConfig
from app.models.user_llm_key import UserLlmKey
from app.schemas.llm import OpenClawConfigResponse, OpenClawProviderEntry
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient
from app.services.nfs_mount import RemoteFS, remote_fs

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_REL = Path(".openclaw") / "openclaw.json"


def _strip_jsonc(text: str) -> str:
    """Strip JS-style comments (// and /* */) and trailing commas from JSON text."""
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text

PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "minimax-openai": "https://api.minimaxi.com/v1",
    "minimax-anthropic": "https://api.minimaxi.com/anthropic",
}

BUILTIN_PROVIDERS = {"openai", "anthropic", "gemini", "openrouter"}

PROVIDER_API_TYPE: dict[str, str] = {
    "minimax-openai": "openai-completions",
    "minimax-anthropic": "anthropic-messages",
}

TRUSTED_PROXY_CIDRS = ["10.0.0.0/8", "100.64.0.0/10", "192.168.0.0/16"]


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


def _build_providers_config(
    configs: list,
    wp_api_key: str,
    user_keys: dict[str, UserLlmKey],
    *,
    use_external_proxy: bool = False,
) -> dict:
    """Build the models.providers section for openclaw.json.

    configs: objects with .provider, .key_source, .selected_models
    (UserLlmConfig ORM or InstanceLlmConfigItem schema both work)

    org  key_source  -> proxy URL + wp_api_key
    personal key_source -> provider base URL + user's real API key

    use_external_proxy: True when the instance is on a remote cluster
    (K8s internal DNS unreachable), forcing the external LLM proxy URL.
    """
    if use_external_proxy:
        proxy_url = (settings.LLM_PROXY_URL or "").rstrip("/")
    else:
        proxy_url = (settings.LLM_PROXY_INTERNAL_URL or settings.LLM_PROXY_URL or "").rstrip("/")
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
            if not proxy_url:
                logger.error("LLM_PROXY_URL 未配置，Working Plan 模式无法生成 proxy URL")
                continue
            api_type = PROVIDER_API_TYPE.get(provider)
            is_anthropic_style = api_type == "anthropic-messages"
            entry = {
                "baseUrl": f"{proxy_url}/{provider}" if is_anthropic_style else f"{proxy_url}/{provider}/v1",
                "apiKey": wp_api_key,
            }

        uk = user_keys.get(provider)
        api_type = PROVIDER_API_TYPE.get(provider) or (uk.api_type if uk else None)
        if api_type:
            entry["api"] = api_type

        if cfg.selected_models:
            entry["models"] = _to_openclaw_models(cfg.selected_models)

        providers[provider] = entry
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


def _ensure_gateway_config(config: dict, instance: Instance) -> None:
    """Ensure gateway config is correct for reverse-proxy (Ingress) deployments.

    - gateway.auth.token: shared secret for Control UI WebSocket auth
    - gateway.trustedProxies: Ingress Controller IPs for header forwarding
    - gateway.controlUi.allowInsecureAuth: bypass device pairing for non-localhost
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

    if "trustedProxies" not in gw:
        gw["trustedProxies"] = list(TRUSTED_PROXY_CIDRS)

    control_ui = gw.setdefault("controlUi", {})
    control_ui["allowInsecureAuth"] = True
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

    first_provider = next(iter(providers))
    agents = config.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    defaults["model"] = {"primary": first_provider}


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
        return json.loads(_strip_jsonc(raw))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"openclaw.json 格式无法解析（已尝试去除注释）: {e}"
        ) from e


async def _write_config_file(fs: RemoteFS, data: dict) -> None:
    """Write openclaw.json to Pod via exec."""
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
        is_proxy = any(h in base_url for h in proxy_hosts)

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
    """Read LLM provider configs directly from Pod's openclaw.json.

    Returns a list of dicts suitable for InstanceLlmConfigEntry.
    """
    async with remote_fs(instance, db) as fs:
        try:
            raw_json = await _read_config_file(fs)
        except ValueError as e:
            logger.warning("read_instance_llm_configs: parse error: %s", e)
            raw_json = None

    if not raw_json:
        return []

    pod_providers: dict = raw_json.get("models", {}).get("providers", {})
    if not pod_providers:
        return []

    proxy_hosts = [
        h for h in (
            (settings.LLM_PROXY_INTERNAL_URL or "").rstrip("/"),
            (settings.LLM_PROXY_URL or "").rstrip("/"),
        ) if h
    ]

    user_keys_result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == current_user_id,
            not_deleted(UserLlmKey),
        )
    )
    user_keys = {k.provider: k for k in user_keys_result.scalars().all()}

    entries: list[dict] = []
    for provider, prov_cfg in pod_providers.items():
        base_url = prov_cfg.get("baseUrl", "")
        is_proxy = any(h in base_url for h in proxy_hosts)
        key_source = "org" if is_proxy else "personal"

        models_raw = prov_cfg.get("models", [])
        selected_models = _from_openclaw_models(models_raw) if models_raw else None

        personal_key_masked: str | None = None
        if key_source == "personal":
            uk = user_keys.get(provider)
            if uk:
                personal_key_masked = _mask_key(uk.api_key)

        entries.append({
            "provider": provider,
            "key_source": key_source,
            "selected_models": selected_models,
            "personal_key_masked": personal_key_masked,
        })

    return entries


async def write_instance_llm_configs(
    instance: Instance, db: AsyncSession, configs: list, current_user_id: str,
) -> None:
    """Write LLM provider configs directly to Pod's openclaw.json.

    configs: list of InstanceLlmConfigItem (or anything with .provider, .key_source, .selected_models)
    """
    wp_api_key = instance.wp_api_key or ""

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

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    use_external = bool(cluster and cluster.proxy_endpoint)

    providers = _build_providers_config(
        configs, wp_api_key, user_keys, use_external_proxy=use_external,
    )

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
        _set_default_agent_model(existing_json, providers)
        await _write_config_file(fs, existing_json)

    logger.info(
        "write_instance_llm_configs: instance=%s providers=%s",
        instance.name, list(providers.keys()),
    )


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

    if instance.llm_providers:
        allowed = set(instance.llm_providers)
        configs = [c for c in configs if c.provider in allowed]

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

    has_org = any(c.key_source == "org" for c in configs)
    if has_org and not wp_api_key:
        logger.warning("实例 %s 缺少 wp_api_key，Working Plan 模式无法写入", instance.name)

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    use_external = bool(cluster and cluster.proxy_endpoint)

    providers = _build_providers_config(
        configs, wp_api_key, user_keys, use_external_proxy=use_external,
    )

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
    "src/sse-server.ts",
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


async def _deploy_plugin_files(fs: RemoteFS, plugin_source: Path) -> None:
    """Copy channel plugin files to the Pod (.openclaw/extensions/)."""
    target_base = f".openclaw/extensions/{CHANNEL_PLUGIN_DIR}"
    await fs.mkdir(f"{target_base}/src")

    for rel_path in PLUGIN_FILES:
        src = plugin_source / rel_path
        if src.exists():
            await fs.write_text(
                f"{target_base}/{rel_path}",
                src.read_text(encoding="utf-8"),
            )


def _make_account_entry(instance: Instance, workspace_id: str) -> dict:
    """Build a single nodeskclaw account entry for a workspace."""
    return {
        "enabled": True,
        "apiUrl": settings.AGENT_API_BASE_URL,
        "workspaceId": workspace_id,
        "instanceId": instance.id,
        "apiToken": json.loads(instance.env_vars or "{}").get(
            "OPENCLAW_GATEWAY_TOKEN", ""
        ),
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
    for tool_name in (
        "nodeskclaw_blackboard",
        "nodeskclaw_topology",
        "nodeskclaw_performance",
        "nodeskclaw_proposals",
        "nodeskclaw_gene_discovery",
    ):
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
        for tool_name in (
            "nodeskclaw_blackboard", "nodeskclaw_topology",
            "nodeskclaw_performance", "nodeskclaw_proposals",
            "nodeskclaw_gene_discovery",
        ):
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
    target_base = f".openclaw/extensions/{LEARNING_PLUGIN_DIR}"
    await fs.mkdir(f"{target_base}/src")

    for rel_path in LEARNING_PLUGIN_FILES:
        src = plugin_source / rel_path
        if src.exists():
            await fs.write_text(
                f"{target_base}/{rel_path}",
                src.read_text(encoding="utf-8"),
            )


def _inject_learning_channel_config(
    config: dict,
    instance: Instance,
) -> None:
    if "channels" not in config:
        config["channels"] = {}

    callback_base = getattr(settings, "NODESKCLAW_WEBHOOK_BASE_URL", "") or ""

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


async def restart_openclaw(instance: Instance, db: AsyncSession) -> dict:
    """Restart OpenClaw (config is assumed to be already written by the caller).

    Strategy: try graceful SIGTERM first; if exec fails (pod crashed / not ready),
    fall back to Deployment rolling restart.
    Docker: delegate to DockerComputeProvider.restart_instance.
    """
    if instance.compute_provider == "docker":
        return await _restart_openclaw_docker(instance)

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


async def _restart_openclaw_docker(instance: Instance) -> dict:
    """Restart an OpenClaw Docker container."""
    from app.services.instance_service import _build_docker_handle, _get_docker_provider
    try:
        provider = _get_docker_provider()
        handle = _build_docker_handle(instance)
        await provider.restart_instance(handle)
        logger.info("Docker 实例 %s OpenClaw 重启完成", instance.name)
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
    plugin_source = _get_plugin_source_dir()
    repaired = []
    skipped = []
    failed = []

    for inst in instances:
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
                await _deploy_plugin_files(fs, plugin_source)

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
                for tool_name in (
                    "nodeskclaw_blackboard", "nodeskclaw_topology",
                    "nodeskclaw_performance", "nodeskclaw_proposals",
                    "nodeskclaw_gene_discovery",
                ):
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
