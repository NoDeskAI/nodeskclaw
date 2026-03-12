"""Channel config service: discover, read/write channel configs in openclaw.json."""

import json
import logging
import textwrap
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, BadRequestError
from app.models.instance import Instance
from app.services.llm_config_service import (
    _read_config_file,
    _write_config_file,
    restart_openclaw,
)
from app.services.nfs_mount import RemoteFS, remote_fs

logger = logging.getLogger(__name__)

SYSTEM_CHANNEL_IDS = {"nodeskclaw", "learning"}


CHANNEL_LABELS: dict[str, str] = {
    "feishu": "Feishu / 飞书",
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


# ── Channel Schema Registry ──────────────────────────────

CHANNEL_SCHEMAS: dict[str, list[dict]] = {
    "feishu": [
        {"key": "appId", "label": "App ID", "type": "string", "required": True,
         "placeholder": "cli_xxxx"},
        {"key": "appSecret", "label": "App Secret", "type": "password", "required": True,
         "placeholder": "飞书应用的 App Secret"},
        {"key": "domain", "label": "Domain（域名）", "type": "select", "required": False,
         "options": [
             {"value": "feishu", "label": "feishu（飞书国内）"},
             {"value": "lark", "label": "lark（海外 Lark）"},
         ], "default": "feishu"},
        {"key": "connectionMode", "label": "Connection Mode（连接方式）", "type": "select",
         "required": False,
         "options": [
             {"value": "websocket", "label": "WebSocket（长连接，推荐）"},
             {"value": "webhook", "label": "Webhook（需公网回调）"},
         ], "default": "websocket"},
        {"key": "dmPolicy", "label": "DM Policy（私聊策略）", "type": "select",
         "required": False,
         "options": [
             {"value": "open", "label": "open（所有人可用）"},
             {"value": "pairing", "label": "pairing（需配对）"},
             {"value": "allowlist", "label": "allowlist（白名单）"},
         ], "default": "open"},
        {"key": "groupPolicy", "label": "Group Policy（群聊策略）", "type": "select",
         "required": False,
         "options": [
             {"value": "open", "label": "open（开放）"},
             {"value": "allowlist", "label": "allowlist（白名单）"},
             {"value": "disabled", "label": "disabled（禁用群聊）"},
         ], "default": "open"},
        {"key": "requireMention", "label": "Require Mention（需@提及）", "type": "boolean",
         "required": False, "default": False},
        {"key": "topicSessionMode", "label": "Topic Session Mode（话题模式）",
         "type": "select", "required": False,
         "options": [
             {"value": "disabled", "label": "disabled"},
             {"value": "enabled", "label": "enabled"},
         ], "default": "disabled"},
        {"key": "encryptKey", "label": "Encrypt Key（事件加密密钥）", "type": "password",
         "required": False, "placeholder": "可选，Webhook 模式下使用"},
        {"key": "verificationToken", "label": "Verification Token（验证令牌）",
         "type": "password", "required": False, "placeholder": "可选，Webhook 模式下使用"},
    ],
    "slack": [
        {"key": "botToken", "label": "Bot Token", "type": "password", "required": True,
         "placeholder": "xoxb-xxxx"},
        {"key": "appToken", "label": "App Token", "type": "password", "required": True,
         "placeholder": "xapp-xxxx"},
    ],
    "telegram": [
        {"key": "botToken", "label": "Bot Token", "type": "password", "required": True,
         "placeholder": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"},
    ],
    "discord": [
        {"key": "token", "label": "Bot Token", "type": "password", "required": True,
         "placeholder": "Discord Bot Token"},
    ],
    "whatsapp": [
        {"key": "phoneNumber", "label": "Phone Number（手机号）", "type": "string",
         "required": False, "placeholder": "关联的手机号"},
    ],
    "msteams": [
        {"key": "appId", "label": "App ID", "type": "string", "required": True,
         "placeholder": "Azure Bot App ID"},
        {"key": "appPassword", "label": "App Password", "type": "password",
         "required": True, "placeholder": "Azure Bot App Password"},
    ],
    "googlechat": [
        {"key": "serviceAccountKeyFile", "label": "Service Account Key File（服务账号密钥路径）",
         "type": "string", "required": True,
         "placeholder": "/root/.openclaw/google-sa-key.json"},
    ],
    "mattermost": [
        {"key": "url", "label": "Server URL（服务器地址）", "type": "string",
         "required": True, "placeholder": "https://mattermost.example.com"},
        {"key": "token", "label": "Bot Token", "type": "password", "required": True,
         "placeholder": "Mattermost Bot Access Token"},
    ],
    "matrix": [
        {"key": "homeserverUrl", "label": "Homeserver URL", "type": "string",
         "required": True, "placeholder": "https://matrix.org"},
        {"key": "accessToken", "label": "Access Token", "type": "password",
         "required": True, "placeholder": "Matrix Access Token"},
    ],
}

SENSITIVE_KEYS = {
    "appSecret", "botToken", "appToken", "token", "appPassword",
    "accessToken", "encryptKey", "verificationToken", "apiKey",
    "serviceAccountKeyFile",
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
    """Scan Pod/container for available channel plugins and return metadata list."""
    async with remote_fs(instance, db) as fs:
        try:
            if instance.compute_provider == "docker":
                from app.services.nfs_mount import DockerFS
                assert isinstance(fs, DockerFS)
                raw = await fs.exec_command(["node", "-e", _DISCOVER_SCRIPT])
            else:
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
            "has_schema": cid in CHANNEL_SCHEMAS,
        })

    channels.sort(key=lambda c: (c["order"], c["id"]))

    for info in REPO_CHANNEL_PLUGINS.values():
        pass

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
    """Read channels section from openclaw.json, excluding system channels."""
    async with remote_fs(instance, db) as fs:
        try:
            config = await _read_config_file(fs)
        except ValueError as e:
            logger.warning("读取 openclaw.json 失败: %s", e)
            raise AppException(
                code=50200,
                message=f"配置文件解析失败: {e}",
                status_code=502,
                message_key="errors.channel.config_read_failed",
            )

    if config is None:
        return {}

    all_channels: dict = config.get("channels", {})
    user_channels = {}
    for cid, cfg in all_channels.items():
        if cid in SYSTEM_CHANNEL_IDS:
            continue
        user_channels[cid] = _mask_sensitive(cfg) if isinstance(cfg, dict) else cfg

    return user_channels


async def write_channel_configs(
    instance: Instance, db: AsyncSession, channel_configs: dict,
) -> dict:
    """Write user channel configs to openclaw.json and restart OpenClaw.

    Preserves system channel configs and other non-channel sections.
    """
    async with remote_fs(instance, db) as fs:
        try:
            config = await _read_config_file(fs)
        except ValueError as e:
            raise AppException(
                code=50200,
                message=f"配置文件解析失败: {e}",
                status_code=502,
                message_key="errors.channel.config_read_failed",
            )

        if config is None:
            config = {}

        existing_channels = config.get("channels", {})

        for cid, new_cfg in channel_configs.items():
            if not isinstance(new_cfg, dict):
                continue
            old_cfg = existing_channels.get(cid)
            if not isinstance(old_cfg, dict):
                continue
            for k, v in new_cfg.items():
                if isinstance(v, str) and "***" in v and k in old_cfg:
                    new_cfg[k] = old_cfg[k]

        system_configs = {
            cid: cfg for cid, cfg in existing_channels.items()
            if cid in SYSTEM_CHANNEL_IDS
        }

        merged = {**system_configs, **channel_configs}

        config["channels"] = merged

        plugins = config.setdefault("plugins", {})
        entries = plugins.setdefault("entries", {})
        old_user_channels = {
            cid for cid in existing_channels if cid not in SYSTEM_CHANNEL_IDS
        }
        for cid in channel_configs:
            entries[cid] = {"enabled": True}
        for cid in old_user_channels - set(channel_configs):
            entries[cid] = {"enabled": False}

        try:
            await _write_config_file(fs, config)
        except AppException:
            raise
        except Exception as e:
            logger.error("写入 Channel 配置失败: %s", e)
            raise AppException(
                code=50200, status_code=502,
                message="Channel 配置写入失败，实例可能正在重启中，请稍后重试",
                message_key="errors.channel.config_write_failed",
            )

    logger.info("已写入 Channel 配置: instance=%s channels=%s",
                instance.name, list(channel_configs.keys()))

    result = await restart_openclaw(instance, db)
    return result


# ── Schema ────────────────────────────────────────────────

def get_channel_schema(channel_id: str) -> list[dict] | None:
    """Return the config form schema for a known channel, or None."""
    return CHANNEL_SCHEMAS.get(channel_id)


# ── Custom Channel Deployment ─────────────────────────────

async def deploy_repo_channel(
    instance: Instance, db: AsyncSession, channel_id: str,
) -> dict:
    """Deploy a repo-based channel plugin to the instance Pod."""
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

        config = await _read_config_file(fs) or {}
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
        await _write_config_file(fs, config)

    logger.info("已部署仓库 Channel 插件: instance=%s channel=%s",
                instance.name, channel_id)
    return {"channel_id": channel_id, "status": "deployed"}


async def install_npm_channel(
    instance: Instance, db: AsyncSession, package_name: str,
) -> dict:
    """Install a third-party channel plugin via openclaw CLI in the Pod."""
    if not package_name or not package_name.strip():
        raise BadRequestError(
            message="npm 包名不能为空",
            message_key="errors.channel.empty_package_name",
        )

    async with remote_fs(instance, db) as fs:
        try:
            if instance.compute_provider == "docker":
                from app.services.nfs_mount import DockerFS
                assert isinstance(fs, DockerFS)
                output = await fs.exec_command(
                    ["npx", "openclaw", "plugins", "install", package_name.strip()],
                )
            else:
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
    if not plugin_id:
        raise BadRequestError(
            message="插件 ID 不能为空",
            message_key="errors.channel.empty_plugin_id",
        )

    async with remote_fs(instance, db) as fs:
        target_base = f".openclaw/extensions/{plugin_id}"
        for rel_path, content in plugin_files.items():
            parent = str(Path(f"{target_base}/{rel_path}").parent)
            if parent != target_base:
                await fs.mkdir(parent)
            await fs.write_text(f"{target_base}/{rel_path}", content)

        config = await _read_config_file(fs) or {}
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
        await _write_config_file(fs, config)

    logger.info("已部署上传 Channel 插件: instance=%s plugin=%s",
                instance.name, plugin_id)
    return {"plugin_id": plugin_id, "status": "deployed"}
