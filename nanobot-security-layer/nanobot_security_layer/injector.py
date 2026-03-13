"""Monkey-patch nanobot's ToolRegistry.execute to run security pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Coroutine

from .loader import create_plugins, load_security_config
from .pipeline import SecurityPipeline
from .types import AfterAction, BeforeAction, ExecutionContext, ExecutionResult

logger = logging.getLogger("nanobot_security_layer")

_pipeline: SecurityPipeline | None = None
_initialized = False


def _get_pipeline() -> SecurityPipeline:
    global _pipeline, _initialized
    if _pipeline is None:
        _pipeline = SecurityPipeline()
    if not _initialized:
        _initialized = True
        config = load_security_config()
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_async_init(_pipeline, config))
        else:
            loop.run_until_complete(_async_init(_pipeline, config))
    return _pipeline


async def _async_init(pipeline: SecurityPipeline, config: Any) -> None:
    plugins = await create_plugins(config)
    for p in plugins:
        pipeline.add_plugin(p)
    logger.info("Security pipeline ready (%d plugins active)", len(plugins))


def inject_security_layer() -> None:
    """Monkey-patch ToolRegistry.execute with security pipeline wrapper.

    Call this ONCE before nanobot starts (e.g. in startup.py).
    The patch is applied at the class level, so all ToolRegistry instances
    created afterwards will use the secured execute method.
    """
    try:
        from nanobot.agent.tools.registry import ToolRegistry
    except ImportError:
        logger.error("Cannot import nanobot.agent.tools.registry — is nanobot-ai installed?")
        return

    if getattr(ToolRegistry.execute, "_security_patched", False):
        logger.warning("ToolRegistry.execute already patched, skipping")
        return

    original_execute = ToolRegistry.execute

    @wraps(original_execute)
    async def secured_execute(self: Any, name: str, params: dict[str, Any]) -> str:
        pipeline = _get_pipeline()

        ctx = ExecutionContext(
            tool_name=name,
            params=dict(params) if params else {},
            timestamp=time.time(),
            metadata={},
        )

        before = await pipeline.run_before(ctx)

        if before.action == BeforeAction.DENY:
            msg = before.message or before.reason or "Blocked by security policy"
            return f"Error: {msg}\n[This tool call was blocked by security policy.]"

        execute_params = before.modified_params if before.action == BeforeAction.MODIFY and before.modified_params else params

        t0 = time.monotonic()
        result = await original_execute(self, name, execute_params)
        duration_ms = (time.monotonic() - t0) * 1000

        exec_result = ExecutionResult(
            result=result,
            error=result if isinstance(result, str) and result.startswith("Error") else None,
            duration_ms=duration_ms,
        )

        after = await pipeline.run_after(ctx, exec_result)

        if after.action == AfterAction.REDACT and after.modified_result is not None:
            result = after.modified_result
        if after.message:
            result = f"{result}\n\n[Security note: {after.message}]"

        return result

    secured_execute._security_patched = True  # type: ignore[attr-defined]
    ToolRegistry.execute = secured_execute  # type: ignore[assignment]
    logger.info("ToolRegistry.execute patched with security pipeline")
