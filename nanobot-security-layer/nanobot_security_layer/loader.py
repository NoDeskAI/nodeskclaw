from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .plugins.policy_gate import PolicyGatePlugin
from .types import SecurityConfig, PluginEntry

if TYPE_CHECKING:
    from .types import SecurityPlugin

logger = logging.getLogger("nanobot_security_layer")

DEFAULT_CONFIG_PATHS = [
    "/opt/nanobot/config/security-policy.json",
    Path.home() / ".nanobot" / "config" / "security-policy.json",
]

BUILTIN_FACTORIES: dict[str, type] = {
    "policy-gate": PolicyGatePlugin,
}


def load_security_config() -> SecurityConfig:
    config_path = os.environ.get("SECURITY_POLICY_PATH")
    if not config_path:
        for candidate in DEFAULT_CONFIG_PATHS:
            if Path(candidate).is_file():
                config_path = str(candidate)
                break

    if not config_path or not Path(config_path).is_file():
        logger.warning("No security config found, pipeline will have no plugins")
        return SecurityConfig(plugins=[])

    try:
        raw = Path(config_path).read_text(encoding="utf-8")
        data = json.loads(raw)
        entries = [
            PluginEntry(
                id=e["id"],
                enabled=e.get("enabled", True),
                priority=e.get("priority", 100),
                config=e.get("config"),
            )
            for e in data.get("plugins", [])
        ]
        logger.info("Loaded config from %s (%d plugin entries)", config_path, len(entries))
        return SecurityConfig(plugins=entries)
    except Exception:
        logger.exception("Failed to parse security config at %s", config_path)
        return SecurityConfig(plugins=[])


async def create_plugins(config: SecurityConfig) -> list[SecurityPlugin]:
    plugins: list[SecurityPlugin] = []

    for entry in config.plugins:
        if not entry.enabled:
            continue

        factory_cls = BUILTIN_FACTORIES.get(entry.id)
        if not factory_cls:
            logger.warning("Unknown plugin '%s', skipping", entry.id)
            continue

        try:
            plugin = factory_cls()
            plugin.priority = entry.priority
            await plugin.initialize(entry.config or {})
            plugins.append(plugin)
            logger.info("Plugin '%s' initialized (priority=%d)", entry.id, entry.priority)
        except Exception:
            logger.exception("Failed to initialize plugin '%s'", entry.id)

    return plugins
