"""Channel config service: discover, read/write channel configs (runtime-aware)."""

import json
import logging
import textwrap
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, BadRequestError, UnsupportedCapabilityError
from app.models.instance import Instance
from app.services.nfs_mount import remote_fs
from app.services.runtime.config_adapter import get_config_adapter
from app.services.runtime.registries.runtime_registry import runtime_supports_capability
from app.services.unified_channel_schema import (
    UNIFIED_CHANNEL_REGISTRY,
    get_legacy_channel_schemas,
)

logger = logging.getLogger(__name__)

SYSTEM_CHANNEL_IDS = {"nodeskclaw", "learning"}


CHANNEL_LABELS: dict[str, str] = {
    "feishu": "Feishu / 飞书",
    "dingtalk": "DingTalk / 钉钉",
    "slack": "Slack",
    "telegram": "Telegram",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "irc": "IRC",
    "signal": "Signal",
    "googlechat": "Google Chat",
    "msteams": "Microsoft Teams",
    "matrix": "Matrix",
    "line": "LINE",
    "mattermost": "Mattermost",
    "bluebubbles": "BlueBubbles",
    "nextcloud-talk": "Nextcloud Talk",
    "synology-chat": "Synology Chat",
    "nostr": "Nostr",
    "tlon": "Tlon",
    "twitch": "Twitch",
    "imessage": "iMessage",
    "zalo": "Zalo",
    "zalouser": "Zalo Personal",
}

CHANNEL_ORDER: dict[str, int] = {
    "feishu": 35,
    "dingtalk": 36,
    "slack": 40,
    "telegram": 45,
    "discord": 50,
    "googlechat": 55,
    "nostr": 55,
    "msteams": 60,
    "mattermost": 65,
    "nextcloud-talk": 65,
    "matrix": 70,
    "bluebubbles": 75,
    "line": 75,
    "zalo": 80,
    "zalouser": 85,
    "synology-chat": 90,
    "tlon": 90,
    "whatsapp": 95,
    "irc": 95,
    "signal": 95,
    "imessage": 95,
    "twitch": 95,
}


# Backward-compatible CHANNEL_SCHEMAS generated from UNIFIED_CHANNEL_REGISTRY
CHANNEL_SCHEMAS: dict[str, list[dict]] = get_legacy_channel_schemas()

SENSITIVE_KEYS = {
    "appSecret", "botToken", "appToken", "token", "appPassword",
    "accessToken", "encryptKey", "verificationToken", "apiKey",
    "serviceAccountKeyFile", "clientSecret",
    "app_secret", "bot_token", "app_token", "client_secret",
    "encrypt_key", "verification_token",
}


# ── Repo Channel Plugins ─────────────────────────────────

REPO_CHANNEL_PLUGINS: dict[str, dict] = {}


def _discover_repo_channel_plugins() -> None:
    """Scan project repo for deployable channel plugins (dirs matching openclaw-channel-*)."""
    global REPO_CHANNEL_PLUGINS  # noqa: PLW0603
    candidates = [
        Path(__file__).resolve().parents[3],
        Path("/app"),
    ]
    for root in candidates:
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            if not d.name.startswith("openclaw-channel-"):
                continue
            if not (d / "index.ts").exists():
                continue
            plugin_json = d / "openclaw.plugin.json"
            if not plugin_json.exists():
                continue
            try:
                meta = json.loads(plugin_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            channels = meta.get("channels", [])
            if not channels:
                continue
            channel_id = channels[0]
            if channel_id in SYSTEM_CHANNEL_IDS:
                continue
            files = _collect_plugin_files(d)
            if files:
                REPO_CHANNEL_PLUGINS[channel_id] = {
                    "dir_name": d.name,
                    "source_root": str(root),
                    "files": files,
                }
        if REPO_CHANNEL_PLUGINS:
            break


def _collect_plugin_files(plugin_dir: Path, prefix: str = "") -> list[str]:
    """Recursively collect relative file paths in a plugin directory."""
    result = []
    for item in sorted(plugin_dir.iterdir()):
        if item.name.startswith(".") or item.name == "node_modules":
            continue
        rel = f"{prefix}{item.name}" if not prefix else f"{prefix}/{item.name}"
        if item.is_file():
            result.append(rel)
        elif item.is_dir():
            result.extend(_collect_plugin_files(item, rel))
    return result


_discover_repo_channel_plugins()


# ── Discovery ─────────────────────────────────────────────

_DISCOVER_SCRIPT = textwrap.dedent("""\
    const path = require('path');
    const fs = require('fs');
    const result = [];
    function scan(dir, origin) {
      if (!fs.existsSync(dir)) return;
      for (const name of fs.readdirSync(dir)) {
        const pj = path.join(dir, name, 'openclaw.plugin.json');
        const pkj = path.join(dir, name, 'package.json');
        if (!fs.existsSync(pj)) continue;
        try {
          const plugin = JSON.parse(fs.readFileSync(pj, 'utf8'));
          if (!plugin.channels || !plugin.channels.length) continue;
          let pkg = {};
          try { pkg = JSON.parse(fs.readFileSync(pkj, 'utf8')); } catch(e) {}
          const ch = (pkg.openclaw || {}).channel || {};
          result.push({
            id: plugin.channels[0],
            pluginId: plugin.id || name,
            label: ch.label || ch.selectionLabel || plugin.id || name,
            description: pkg.description || '',
            origin: origin,
            order: ch.order || 999,
          });
        } catch(e) {}
      }
    }
    // Bundled extensions (OpenClaw is globally installed in the Pod)
    try {
      const globalRoot = require('child_process').execSync('npm root -g').toString().trim();
      scan(path.join(globalRoot, 'openclaw', 'extensions'), 'bundled');
    } catch(e) {}
    // Workspace extensions
    scan('/root/.openclaw/extensions', 'workspace');
    console.log(JSON.stringify(result));
""")


async def discover_available_channels(
    instance: Instance, db: AsyncSession,
) -> list[dict]:
    """Discover available channel plugins (runtime-aware).

    OpenClaw: Node.js exec scan of plugin directories.
    Other runtimes: return static list from adapter.supported_channels().

    After collecting runtime-native channels, augment with UNIFIED_CHANNEL_REGISTRY
    entries to ensure a consistent view across all runtimes.
    """
    runtime = instance.runtime or "openclaw"
    try:
        adapter = get_config_adapter(runtime)
    except ValueError:
        raise BadRequestError(
            message=f"不支持的 runtime: {runtime}",
            message_key="errors.channel.unsupported_runtime",
        )

    if runtime == "openclaw":
        raw_channels = await _discover_openclaw_channels(instance, db)
    else:
        raw_channels = []
        for cid in adapter.supported_channels():
            if cid in SYSTEM_CHANNEL_IDS:
                continue
            defn = UNIFIED_CHANNEL_REGISTRY.get(cid)
            raw_channels.append({
                "id": cid,
                "label": defn.label if defn else CHANNEL_LABELS.get(cid, cid),
                "description": "",
                "origin": "builtin",
                "order": defn.order if defn else CHANNEL_ORDER.get(cid, 999),
                "has_schema": cid in UNIFIED_CHANNEL_REGISTRY or cid in CHANNEL_SCHEMAS,
            })

    seen_ids = {ch["id"] for ch in raw_channels}
    native_channels = set(adapter.supported_channels())

    for cid, defn in UNIFIED_CHANNEL_REGISTRY.items():
        if cid in seen_ids or cid in SYSTEM_CHANNEL_IDS:
            continue
        supported = runtime in defn.supported_runtimes
        raw_channels.append({
            "id": cid,
            "label": defn.label,
            "description": "",
            "origin": "builtin",
            "order": defn.order,
            "has_schema": True,
            "supported": supported,
        })

    for ch in raw_channels:
        if "supported" not in ch:
            ch["supported"] = ch["id"] in native_channels

    raw_channels.sort(key=lambda c: (c["order"], c["id"]))
    return raw_channels


async def _discover_openclaw_channels(
    instance: Instance, db: AsyncSession,
) -> list[dict]:
    """OpenClaw-specific: Node.js exec scan of plugin directories."""
    async with remote_fs(instance, db) as fs:
        try:
            raw = await fs._k8s.exec_in_pod(
                fs._ns, fs._pod,
                ["node", "-e", _DISCOVER_SCRIPT],
                container=fs._container,
            )
        except Exception as e:
            logger.error("Channel discovery exec failed: %s", e)
            raise AppException(
                code=50200,
                message=f"Channel 发现失败: {e}",
                status_code=502,
                message_key="errors.channel.discovery_failed",
            )

    if not raw:
        return []

    try:
        items: list[dict] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Channel discovery returned non-JSON: %s", raw[:200])
        return []

    channels = []
    for item in items:
        cid = item.get("id", "")
        if cid in SYSTEM_CHANNEL_IDS:
            continue
        channels.append({
            "id": cid,
            "label": CHANNEL_LABELS.get(cid, item.get("label", cid)),
            "description": item.get("description", ""),
            "origin": item.get("origin", "unknown"),
            "order": CHANNEL_ORDER.get(cid, item.get("order", 999)),
            "has_schema": cid in UNIFIED_CHANNEL_REGISTRY or cid in CHANNEL_SCHEMAS,
        })

    channels.sort(key=lambda c: (c["order"], c["id"]))

    return channels


# ── Config Read / Write ───────────────────────────────────

def _mask_sensitive(config: dict) -> dict:
    """Mask sensitive fields in a channel config dict for frontend display."""
    masked = {}
    for k, v in config.items():
        if k in SENSITIVE_KEYS and isinstance(v, str) and len(v) > 4:
            masked[k] = v[:4] + "***" + v[-2:]
        else:
            masked[k] = v
    return masked


async def read_channel_configs(
    instance: Instance, db: AsyncSession,
) -> dict:
    """Read channels section from config file, excluding system channels (runtime-aware)."""
    runtime = instance.runtime or "openclaw"
    try:
        adapter = get_config_adapter(runtime)
    except ValueError:
        raise BadRequestError(
            message=f"不支持的 runtime: {runtime}",
            message_key="errors.channel.unsupported_runtime",
        )

    async with remote_fs(instance, db) as fs:
        try:
            config = await adapter.read_config(fs)
        except ValueError as e:
            logger.warning("读取配置文件失败 (runtime=%s): %s", runtime, e)
            raise AppException(
                code=50200,
                message=f"配置文件解析失败: {e}",
                status_code=502,
                message_key="errors.channel.config_read_failed",
            )

    if config is None:
        return {}

    all_channels: dict = adapter.extract_channels(config)
    user_channels = {}
    for cid, cfg in all_channels.items():
        if cid in SYSTEM_CHANNEL_IDS:
            continue
        if isinstance(cfg, dict):
            canonical = adapter.translate_from_runtime(cfg, cid)
            user_channels[cid] = _mask_sensitive(canonical)
        else:
            user_channels[cid] = cfg

    return user_channels


async def write_channel_configs(
    instance: Instance, db: AsyncSession, channel_configs: dict,
) -> dict:
    """Write user channel configs and restart instance (runtime-aware).

    Preserves system channel configs and other non-channel sections.
    """
    runtime = instance.runtime or "openclaw"
    try:
        adapter = get_config_adapter(runtime)
    except ValueError:
        raise BadRequestError(
            message=f"不支持的 runtime: {runtime}",
            message_key="errors.channel.unsupported_runtime",
        )

    async with remote_fs(instance, db) as fs:
        try:
            config = await adapter.read_config(fs)
        except ValueError as e:
            raise AppException(
                code=50200,
                message=f"配置文件解析失败: {e}",
                status_code=502,
                message_key="errors.channel.config_read_failed",
            )

        if config is None:
            config = {}

        existing_channels = adapter.extract_channels(config)

        for cid, new_cfg in channel_configs.items():
            if not isinstance(new_cfg, dict):
                continue
            old_native = existing_channels.get(cid)
            if not isinstance(old_native, dict):
                continue
            old_canonical = adapter.translate_from_runtime(old_native, cid)
            for k, v in new_cfg.items():
                if isinstance(v, str) and "***" in v and k in old_canonical:
                    new_cfg[k] = old_canonical[k]

        system_configs = {
            cid: cfg for cid, cfg in existing_channels.items()
            if cid in SYSTEM_CHANNEL_IDS
        }

        native_channels = {}
        for cid, cfg in channel_configs.items():
            if isinstance(cfg, dict):
                native_channels[cid] = adapter.translate_to_runtime(cfg, cid)
            else:
                native_channels[cid] = cfg

        merged = {**system_configs, **native_channels}
        config = adapter.merge_channels(config, merged)

        try:
            await adapter.write_config(fs, config)
        except AppException:
            raise
        except Exception as e:
            logger.error("写入 Channel 配置失败: %s", e)
            raise AppException(
                code=50200, status_code=502,
                message="Channel 配置写入失败，实例可能正在重启中，请稍后重试",
                message_key="errors.channel.config_write_failed",
            )

    logger.info("已写入 Channel 配置: instance=%s runtime=%s channels=%s",
                instance.name, runtime, list(channel_configs.keys()))

    result = await adapter.restart(instance, db)
    return result


# ── Custom Channel Deployment ─────────────────────────────

def _require_runtime_capability(
    instance: Instance,
    capability: str,
    operation: str,
) -> None:
    runtime = instance.runtime or "openclaw"
    if not runtime_supports_capability(runtime, capability):
        raise UnsupportedCapabilityError(
            runtime_id=runtime,
            capability=capability,
            operation=operation,
        )


def _require_openclaw_channel_capability(
    instance: Instance,
    capability: str,
    operation: str,
) -> None:
    runtime = instance.runtime or "openclaw"
    if runtime != "openclaw":
        raise UnsupportedCapabilityError(
            runtime_id=runtime,
            capability=capability,
            operation=operation,
        )
    _require_runtime_capability(instance, capability, operation)


async def deploy_repo_channel(
    instance: Instance, db: AsyncSession, channel_id: str,
) -> dict:
    """Deploy a repo-based channel plugin to the instance Pod."""
    _require_openclaw_channel_capability(instance, "repo_channel_sync", "channel.deploy_repo_plugin")
    plugin_info = REPO_CHANNEL_PLUGINS.get(channel_id)
    if not plugin_info:
        raise BadRequestError(
            message=f"项目仓库中未找到 Channel: {channel_id}",
            message_key="errors.channel.repo_plugin_not_found",
        )

    source_root = Path(plugin_info["source_root"])
    dir_name = plugin_info["dir_name"]
    source_dir = source_root / dir_name

    if not source_dir.exists():
        raise BadRequestError(
            message=f"Channel 插件源目录不存在: {dir_name}",
            message_key="errors.channel.source_not_found",
        )

    adapter = get_config_adapter("openclaw")
    async with remote_fs(instance, db) as fs:
        target_base = f".openclaw/extensions/{dir_name}"
        for rel_path in plugin_info["files"]:
            src = source_dir / rel_path
            if not src.exists():
                continue
            parent = str(Path(f"{target_base}/{rel_path}").parent)
            if parent != target_base:
                await fs.mkdir(parent)
            await fs.write_text(
                f"{target_base}/{rel_path}",
                src.read_text(encoding="utf-8"),
            )

        config = await adapter.read_config(fs) or {}
        plugins = config.setdefault("plugins", {})
        load = plugins.setdefault("load", {})
        paths: list = load.setdefault("paths", [])
        old_relative = f".openclaw/extensions/{dir_name}"
        if old_relative in paths:
            paths.remove(old_relative)
        plugin_path = f"/root/.openclaw/extensions/{dir_name}"
        if plugin_path not in paths:
            paths.append(plugin_path)

        entries = plugins.setdefault("entries", {})
        entries[channel_id] = {"enabled": True}
        await adapter.write_config(fs, config)

    logger.info("已部署仓库 Channel 插件: instance=%s channel=%s",
                instance.name, channel_id)
    return {"channel_id": channel_id, "status": "deployed"}


async def install_npm_channel(
    instance: Instance, db: AsyncSession, package_name: str,
) -> dict:
    """Install a third-party channel plugin via runtime tooling in the Pod."""
    _require_openclaw_channel_capability(instance, "npm_channel_install", "channel.install_npm_plugin")
    if not package_name or not package_name.strip():
        raise BadRequestError(
            message="npm 包名不能为空",
            message_key="errors.channel.empty_package_name",
        )

    async with remote_fs(instance, db) as fs:
        try:
            output = await fs._k8s.exec_in_pod(
                fs._ns, fs._pod,
                ["npx", "openclaw", "plugins", "install", package_name.strip()],
                container=fs._container,
            )
        except Exception as e:
            logger.error("npm channel install failed: %s", e)
            raise AppException(
                code=50200,
                message=f"Channel 安装失败: {e}",
                status_code=502,
                message_key="errors.channel.install_failed",
            )

    logger.info("已安装 npm Channel: instance=%s package=%s",
                instance.name, package_name)
    return {"package": package_name, "status": "installed", "output": output}


async def upload_channel_plugin(
    instance: Instance, db: AsyncSession,
    plugin_files: dict[str, str],
    plugin_id: str,
) -> dict:
    """Deploy uploaded channel plugin files to the instance Pod.

    plugin_files: dict mapping relative paths to file contents (text).
    """
    _require_openclaw_channel_capability(instance, "upload_channel_plugin", "channel.upload_plugin")
    if not plugin_id:
        raise BadRequestError(
            message="插件 ID 不能为空",
            message_key="errors.channel.empty_plugin_id",
        )

    adapter = get_config_adapter("openclaw")
    async with remote_fs(instance, db) as fs:
        target_base = f".openclaw/extensions/{plugin_id}"
        for rel_path, content in plugin_files.items():
            parent = str(Path(f"{target_base}/{rel_path}").parent)
            if parent != target_base:
                await fs.mkdir(parent)
            await fs.write_text(f"{target_base}/{rel_path}", content)

        config = await adapter.read_config(fs) or {}
        plugins = config.setdefault("plugins", {})
        load = plugins.setdefault("load", {})
        paths: list = load.setdefault("paths", [])
        old_relative = f".openclaw/extensions/{plugin_id}"
        if old_relative in paths:
            paths.remove(old_relative)
        plugin_path = f"/root/.openclaw/extensions/{plugin_id}"
        if plugin_path not in paths:
            paths.append(plugin_path)

        entries = plugins.setdefault("entries", {})
        entries[plugin_id] = {"enabled": True}
        await adapter.write_config(fs, config)

    logger.info("已部署上传 Channel 插件: instance=%s plugin=%s",
                instance.name, plugin_id)
    return {"plugin_id": plugin_id, "status": "deployed"}
