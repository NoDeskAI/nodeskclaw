"""Monkey-patch nanobot's ToolRegistry.execute to route through backend security evaluation."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from functools import wraps
from typing import Any

from .types import AfterAction, BeforeAction
from .ws_client import connect, evaluate_after, evaluate_before

logger = logging.getLogger("nanobot_security_layer")


def inject_security_layer() -> None:
    """Monkey-patch ToolRegistry.execute with security WebSocket client wrapper.

    Call this ONCE before nanobot starts (e.g. in startup.py).
    When SECURITY_LAYER_ENABLED=false, this is a no-op.
    """
    if os.environ.get("SECURITY_LAYER_ENABLED", "true") == "false":
        logger.info("Security layer disabled via SECURITY_LAYER_ENABLED=false")
        return

    try:
        from nanobot.agent.tools.registry import ToolRegistry
    except ImportError:
        logger.error("Cannot import nanobot.agent.tools.registry -- is nanobot-ai installed?")
        return

    if getattr(ToolRegistry.execute, "_security_patched", False):
        logger.warning("ToolRegistry.execute already patched, skipping")
        return

    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(connect())
    else:
        loop.run_until_complete(connect())

    original_execute = ToolRegistry.execute

    @wraps(original_execute)
    async def secured_execute(self: Any, name: str, params: dict[str, Any]) -> str:
        before = await evaluate_before(name, dict(params) if params else {})

        if before.action == BeforeAction.DENY:
            msg = before.message or before.reason or "Blocked by security policy"
            return f"Error: {msg}\n[This tool call was blocked by security policy.]"

        execute_params = before.modified_params if before.action == BeforeAction.MODIFY and before.modified_params else params

        t0 = time.monotonic()
        result = await original_execute(self, name, execute_params)
        duration_ms = (time.monotonic() - t0) * 1000

        after = await evaluate_after(
            name,
            dict(params) if params else {},
            exec_result=result,
            exec_error=result if isinstance(result, str) and result.startswith("Error") else None,
            duration_ms=duration_ms,
        )

        if after.action == AfterAction.REDACT and after.modified_result is not None:
            result = after.modified_result
        if after.message:
            result = f"{result}\n\n[Security note: {after.message}]"

        return result

    secured_execute._security_patched = True  # type: ignore[attr-defined]
    ToolRegistry.execute = secured_execute  # type: ignore[assignment]
    logger.info("ToolRegistry.execute patched with security WebSocket client")
