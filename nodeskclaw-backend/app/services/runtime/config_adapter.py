"""RuntimeConfigAdapter — abstracts config file I/O and channel translation per runtime."""

from __future__ import annotations

import copy
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import yaml

from app.utils.jsonc import ensure_exec_security, strip_jsonc

if TYPE_CHECKING:
    from app.models.instance import Instance
    from app.services.nfs_mount import RemoteFS
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RuntimeConfigAdapter(ABC):
    @abstractmethod
    async def read_config(self, fs: RemoteFS) -> dict | None:
        """Read the full config file. Returns None if not found."""
        ...

    @abstractmethod
    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        """Write the full config file."""
        ...

    @abstractmethod
    def extract_channels(self, config: dict) -> dict:
        """Extract the channels section from the full config."""
        ...

    @abstractmethod
    def merge_channels(self, config: dict, channels: dict) -> dict:
        """Merge channel configs back into the full config, returning the updated config."""
        ...

    @abstractmethod
    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        """Restart the runtime instance after config changes."""
        ...

    @abstractmethod
    def supported_channels(self) -> list[str]:
        """Return list of channel IDs this runtime supports."""
        ...

    @abstractmethod
    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        """Translate canonical (camelCase) field names to runtime-native keys."""
        ...

    @abstractmethod
    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        """Translate runtime-native keys to canonical (camelCase) field names."""
        ...


class OpenClawConfigAdapter(RuntimeConfigAdapter):

    _CONFIG_REL = ".openclaw/openclaw.json"

    async def read_config(self, fs: RemoteFS) -> dict | None:
        raw = await fs.read_text(self._CONFIG_REL)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(strip_jsonc(raw))
        except json.JSONDecodeError as e:
            raise ValueError(f"openclaw.json 格式无法解析: {e}") from e

    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        ensure_exec_security(data)
        await fs.write_text(
            self._CONFIG_REL,
            json.dumps(data, indent=2, ensure_ascii=False),
        )

    def extract_channels(self, config: dict) -> dict:
        return config.get("channels", {})

    def merge_channels(self, config: dict, channels: dict) -> dict:
        config["channels"] = channels

        plugins = config.setdefault("plugins", {})
        entries = plugins.setdefault("entries", {})
        for cid in channels:
            entries[cid] = {"enabled": True}
        return config

    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        from app.services.llm_config_service import restart_runtime
        return await restart_runtime(instance, db)

    def supported_channels(self) -> list[str]:
        return [
            "feishu", "dingtalk", "telegram", "discord", "slack", "whatsapp",
            "irc", "signal", "googlechat", "msteams", "matrix",
            "mattermost", "bluebubbles", "nextcloud-talk", "imessage",
            "line", "nostr", "tlon", "twitch", "synology-chat",
            "zalo", "zalouser",
        ]

    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        return canonical

    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        return native


class NanobotConfigAdapter(RuntimeConfigAdapter):

    _CONFIG_REL = ".nanobot/config.json"

    async def read_config(self, fs: RemoteFS) -> dict | None:
        raw = await fs.read_text(self._CONFIG_REL)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"nanobot config.json 格式无法解析: {e}") from e

    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        await fs.write_text(
            self._CONFIG_REL,
            json.dumps(data, indent=2, ensure_ascii=False),
        )

    def extract_channels(self, config: dict) -> dict:
        return config.get("channels", {})

    def merge_channels(self, config: dict, channels: dict) -> dict:
        config["channels"] = channels
        return config

    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        return await _restart_container(instance, db)

    def supported_channels(self) -> list[str]:
        return [
            "feishu", "telegram", "discord", "slack", "matrix",
            "whatsapp", "email", "dingtalk", "qq", "wecom", "mochat",
        ]

    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY
        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return canonical
        result: dict = {}
        for field_def in defn.fields:
            runtime_key = field_def.runtime_key.get("nanobot")
            if runtime_key and field_def.key in canonical:
                result[runtime_key] = canonical[field_def.key]
        for k, v in canonical.items():
            if not any(f.key == k for f in defn.fields):
                result[k] = v
        return result

    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY
        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return native
        result: dict = {}
        reverse_map: dict[str, str] = {}
        for field_def in defn.fields:
            runtime_key = field_def.runtime_key.get("nanobot")
            if runtime_key:
                reverse_map[runtime_key] = field_def.key
        for k, v in native.items():
            result[reverse_map.get(k, k)] = v
        return result


class HermesConfigAdapter(RuntimeConfigAdapter):

    _CONFIG_REL = ".hermes/config.yaml"
    _SUPPORTED_CHANNELS = ["feishu", "telegram", "discord", "dingtalk"]
    _TOP_LEVEL_FIELD_MIRRORS = {
        "telegram": {
            "extra.require_mention": "require_mention",
            "extra.mention_patterns": "mention_patterns",
            "extra.free_response_chats": "free_response_chats",
        },
        "discord": {
            "extra.require_mention": "require_mention",
            "extra.free_response_channels": "free_response_channels",
        },
    }

    async def read_config(self, fs: RemoteFS) -> dict | None:
        raw = await fs.read_text(self._CONFIG_REL)
        if raw is None:
            return None
        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"hermes config.yaml 格式无法解析: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("hermes config.yaml 根节点必须为对象")
        return data

    async def write_config(self, fs: RemoteFS, data: dict) -> None:
        await fs.write_text(
            self._CONFIG_REL,
            yaml.safe_dump(
                data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ),
        )

    def extract_channels(self, config: dict) -> dict:
        platforms = config.get("platforms", {})
        if not isinstance(platforms, dict):
            platforms = {}

        result: dict[str, dict] = {}
        for channel_id in self._SUPPORTED_CHANNELS:
            native = platforms.get(channel_id)
            merged = copy.deepcopy(native) if isinstance(native, dict) else {}
            top_level = config.get(channel_id)
            if isinstance(top_level, dict):
                self._apply_top_level_overrides(channel_id, merged, top_level)
            if merged:
                result[channel_id] = merged
        return result

    def merge_channels(self, config: dict, channels: dict) -> dict:
        updated = copy.deepcopy(config)
        platforms = updated.get("platforms", {})
        if not isinstance(platforms, dict):
            platforms = {}
        else:
            platforms = copy.deepcopy(platforms)

        for channel_id in self._SUPPORTED_CHANNELS:
            platforms.pop(channel_id, None)

        for channel_id, channel_config in channels.items():
            if channel_id not in self._SUPPORTED_CHANNELS or not isinstance(channel_config, dict):
                continue
            merged = copy.deepcopy(channel_config)
            if merged:
                merged.setdefault("enabled", True)
                platforms[channel_id] = merged

        updated["platforms"] = platforms

        for channel_id in self._SUPPORTED_CHANNELS:
            top_level = updated.get(channel_id)
            if not isinstance(top_level, dict):
                top_level = {}
            else:
                top_level = copy.deepcopy(top_level)
            for top_key in self._TOP_LEVEL_FIELD_MIRRORS.get(channel_id, {}).values():
                top_level.pop(top_key, None)

            native = platforms.get(channel_id)
            if isinstance(native, dict):
                for native_path, top_key in self._TOP_LEVEL_FIELD_MIRRORS.get(channel_id, {}).items():
                    value = self._get_nested(native, native_path)
                    if value is not None:
                        top_level[top_key] = copy.deepcopy(value)

            if top_level:
                updated[channel_id] = top_level
            else:
                updated.pop(channel_id, None)

        return updated

    async def restart(self, instance: Instance, db: AsyncSession) -> dict:
        return await _restart_container(instance, db)

    def supported_channels(self) -> list[str]:
        return list(self._SUPPORTED_CHANNELS)

    def translate_to_runtime(self, canonical: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY

        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return canonical

        result = copy.deepcopy(canonical)
        for field_def in defn.fields:
            runtime_key = field_def.runtime_key.get("hermes")
            if not runtime_key or field_def.key not in canonical:
                continue
            result.pop(field_def.key, None)
            runtime_value = self._canonical_to_runtime_value(channel_id, field_def.key, canonical[field_def.key])
            if runtime_value is None:
                continue
            self._set_nested(result, runtime_key, runtime_value)
        return result

    def translate_from_runtime(self, native: dict, channel_id: str) -> dict:
        from app.services.unified_channel_schema import UNIFIED_CHANNEL_REGISTRY

        defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
        if not defn:
            return native

        remaining = copy.deepcopy(native)
        result: dict[str, object] = {}
        for field_def in defn.fields:
            runtime_key = field_def.runtime_key.get("hermes")
            if not runtime_key:
                continue
            runtime_value = self._get_nested(native, runtime_key)
            if runtime_value is None:
                continue
            result[field_def.key] = self._runtime_to_canonical_value(channel_id, field_def.key, runtime_value)
            self._delete_nested(remaining, runtime_key)

        if isinstance(remaining, dict):
            result.update(remaining)
        return result

    def _apply_top_level_overrides(self, channel_id: str, native: dict, top_level: dict) -> None:
        for native_path, top_key in self._TOP_LEVEL_FIELD_MIRRORS.get(channel_id, {}).items():
            if top_key in top_level:
                self._set_nested(native, native_path, copy.deepcopy(top_level[top_key]))

    @staticmethod
    def _set_nested(data: dict, path: str, value: object) -> None:
        parts = path.split(".")
        cursor = data
        for key in parts[:-1]:
            child = cursor.get(key)
            if not isinstance(child, dict):
                child = {}
                cursor[key] = child
            cursor = child
        cursor[parts[-1]] = value

    @staticmethod
    def _get_nested(data: dict, path: str) -> object | None:
        cursor: object = data
        for key in path.split("."):
            if not isinstance(cursor, dict):
                return None
            cursor = cursor.get(key)
            if cursor is None:
                return None
        return cursor

    @classmethod
    def _delete_nested(cls, data: dict, path: str) -> None:
        parts = path.split(".")
        cursor = data
        parents: list[tuple[dict, str]] = []
        for key in parts[:-1]:
            child = cursor.get(key)
            if not isinstance(child, dict):
                return
            parents.append((cursor, key))
            cursor = child
        cursor.pop(parts[-1], None)

        for parent, key in reversed(parents):
            child = parent.get(key)
            if isinstance(child, dict) and not child:
                parent.pop(key, None)
            else:
                break

    @staticmethod
    def _canonical_to_runtime_value(channel_id: str, field_key: str, value: object) -> object | None:
        if channel_id in {"telegram", "discord"} and field_key == "groupPolicy":
            if value == "mention":
                return True
            if value == "open":
                return False
            return None
        return copy.deepcopy(value)

    @staticmethod
    def _runtime_to_canonical_value(channel_id: str, field_key: str, value: object) -> object:
        if channel_id in {"telegram", "discord"} and field_key == "groupPolicy":
            return "mention" if bool(value) else "open"
        return copy.deepcopy(value)


async def _restart_container(instance: Instance, db: AsyncSession) -> dict:
    """Generic container restart for NanoBot (SIGTERM + wait)."""
    if instance.compute_provider == "docker":
        from app.services.instance_service import _build_docker_handle, _get_docker_provider
        try:
            provider = _get_docker_provider()
            handle = _build_docker_handle(instance)
            await provider.restart_instance(handle)
            return {"status": "ok", "message": "重启完成"}
        except Exception as e:
            logger.error("Docker 实例 %s 重启失败: %s", instance.name, e)
            return {"status": "error", "message": f"Docker 重启失败: {e}"}

    import asyncio
    from app.services.nfs_mount import _get_k8s_client, _k8s_name

    k8s = await _get_k8s_client(instance, db)
    deploy_name = _k8s_name(instance)

    from app.services.nfs_mount import _find_running_pod
    try:
        pod_name, container = await _find_running_pod(k8s, instance)
        await k8s.exec_in_pod(
            instance.namespace, pod_name,
            ["kill", "-SIGTERM", "1"],
            container=container,
        )
        logger.info("已发送 SIGTERM 到实例 %s 的 PID 1", instance.name)
    except Exception as e:
        logger.warning("exec kill 失败，降级为 Deployment 滚动重启: %s", e)
        await k8s.restart_deployment(instance.namespace, deploy_name)

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
                    return {"status": "ok", "message": "重启完成"}

    return {"status": "timeout", "message": "重启超时（60s），请检查实例状态"}


_ADAPTERS: dict[str, RuntimeConfigAdapter] = {
    "openclaw": OpenClawConfigAdapter(),
    "nanobot": NanobotConfigAdapter(),
    "hermes": HermesConfigAdapter(),
}


def get_config_adapter(runtime: str) -> RuntimeConfigAdapter:
    adapter = _ADAPTERS.get(runtime)
    if adapter is None:
        raise ValueError(f"不支持的 runtime: {runtime}")
    return adapter
