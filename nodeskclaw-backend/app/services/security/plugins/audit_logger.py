"""Audit Logger plugin — records tool execution events to operation audit system.

Runs in both Before and After phases. Emits audit events through the
CE hook system (app.core.hooks), which EE's operation_audit handler picks up.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..types import (
    AfterResult,
    BeforeResult,
    ExecutionContext,
    ExecutionResult,
)

logger = logging.getLogger(__name__)


class AuditLoggerPlugin:
    def __init__(self, priority: int = 90) -> None:
        self._id = "audit-logger"
        self._priority = priority
        self._log_before: bool = False
        self._log_after: bool = True

    @property
    def id(self) -> str:
        return self._id

    @property
    def priority(self) -> int:
        return self._priority

    async def initialize(self, config: dict[str, Any]) -> None:
        self._log_before = config.get("log_before", False)
        self._log_after = config.get("log_after", True)

    async def destroy(self) -> None:
        pass

    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult:
        if self._log_before:
            await self._emit_audit(
                ctx=ctx,
                phase="before",
                detail={"params": ctx.params},
            )
        return BeforeResult()

    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult:
        if self._log_after:
            await self._emit_audit(
                ctx=ctx,
                phase="after",
                detail={
                    "duration_ms": result.duration_ms,
                    "has_error": result.error is not None,
                },
            )
        return AfterResult()

    async def _emit_audit(
        self,
        ctx: ExecutionContext,
        phase: str,
        detail: dict[str, Any],
    ) -> None:
        try:
            from app.core import hooks

            await hooks.emit(
                "operation_audit",
                actor_type="agent",
                actor_id=ctx.agent_instance_id,
                action=f"tool.{phase}.{ctx.tool_name}",
                resource_type="tool_call",
                resource_id=ctx.tool_name,
                workspace_id=ctx.workspace_id,
                detail=detail,
                timestamp=time.time(),
            )
        except Exception:
            logger.debug("Audit emit failed (non-fatal)", exc_info=True)
