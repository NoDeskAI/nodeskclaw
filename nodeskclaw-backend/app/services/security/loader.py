"""Plugin loader — discovers and instantiates SecurityPlugin implementations."""

from __future__ import annotations

import logging
from typing import Any

from .types import SecurityPlugin

logger = logging.getLogger(__name__)

BUILTIN_PLUGINS: dict[str, type] = {}


def register_builtin(plugin_id: str, cls: type) -> None:
    BUILTIN_PLUGINS[plugin_id] = cls


def _ensure_builtins_registered() -> None:
    if not BUILTIN_PLUGINS:
        import app.services.security.plugins  # noqa: F401


async def create_plugins(config: list[dict[str, Any]]) -> list[SecurityPlugin]:
    """Instantiate and initialize plugins from configuration.

    Config format:
    [
        {"id": "policy-gate", "enabled": true, "priority": 10, "config": {...}},
        {"id": "dlp-scanner", "enabled": true, "priority": 20, "config": {...}},
    ]
    """
    _ensure_builtins_registered()
    plugins: list[SecurityPlugin] = []

    for entry in config:
        plugin_id = entry.get("id", "")
        if not entry.get("enabled", True):
            continue

        cls = BUILTIN_PLUGINS.get(plugin_id)
        if cls is None:
            logger.warning("Unknown plugin '%s', skipping", plugin_id)
            continue

        priority = entry.get("priority", 100)
        plugin_config = entry.get("config", {})

        try:
            plugin = cls(priority=priority)
            await plugin.initialize(plugin_config)
            logger.info("Plugin '%s' initialized (priority=%d)", plugin_id, priority)
            plugins.append(plugin)
        except Exception:
            logger.exception("Failed to initialize plugin '%s'", plugin_id)

    return plugins
