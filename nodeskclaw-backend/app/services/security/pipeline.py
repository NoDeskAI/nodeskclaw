"""SecurityPipeline — central orchestrator for before/after plugin execution.

Zero built-in security logic. All security capabilities are provided by
SecurityPlugin instances registered via add_plugin().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .types import (
    AfterAction,
    AfterResult,
    BeforeAction,
    BeforeResult,
    ExecutionContext,
    ExecutionResult,
    Finding,
)

if TYPE_CHECKING:
    from .types import SecurityPlugin

logger = logging.getLogger(__name__)


class SecurityPipeline:
    def __init__(self) -> None:
        self._plugins: list[SecurityPlugin] = []

    def add_plugin(self, plugin: SecurityPlugin) -> None:
        self._plugins.append(plugin)
        self._plugins.sort(key=lambda p: p.priority)

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    async def run_before(self, ctx: ExecutionContext) -> BeforeResult:
        all_findings: list[Finding] = []

        for plugin in self._plugins:
            try:
                result = await plugin.before_execute(ctx)
            except Exception:
                logger.exception("Plugin '%s' before_execute error", plugin.id)
                continue

            if result.findings:
                all_findings.extend(result.findings)

            if result.action == BeforeAction.DENY:
                return BeforeResult(
                    action=BeforeAction.DENY,
                    reason=result.reason,
                    message=result.message,
                    findings=all_findings or None,
                )

            if result.action == BeforeAction.MODIFY and result.modified_params:
                ctx.params = result.modified_params

        return BeforeResult(findings=all_findings or None)

    async def run_after(self, ctx: ExecutionContext, exec_result: ExecutionResult) -> AfterResult:
        final_action = AfterAction.PASS
        final_reason: str | None = None
        final_message: str | None = None
        final_modified: str | None = None
        all_findings: list[Finding] = []

        for plugin in self._plugins:
            try:
                result = await plugin.after_execute(ctx, exec_result)
            except Exception:
                logger.exception("Plugin '%s' after_execute error", plugin.id)
                continue

            if result.findings:
                all_findings.extend(result.findings)

            if result.action == AfterAction.REDACT:
                final_action = AfterAction.REDACT
                final_reason = result.reason
                final_message = result.message
                if result.modified_result is not None:
                    final_modified = result.modified_result
            elif result.action == AfterAction.FLAG and final_action == AfterAction.PASS:
                final_action = AfterAction.FLAG
                final_reason = result.reason
                final_message = result.message

        return AfterResult(
            action=final_action,
            reason=final_reason,
            message=final_message,
            modified_result=final_modified,
            findings=all_findings or None,
        )

    async def destroy(self) -> None:
        for plugin in self._plugins:
            try:
                await plugin.destroy()
            except Exception:
                logger.warning("Plugin '%s' destroy error", plugin.id, exc_info=True)
        self._plugins.clear()
