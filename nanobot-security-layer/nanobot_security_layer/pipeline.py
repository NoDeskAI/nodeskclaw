from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .types import (
    AfterAction,
    AfterResult,
    BeforeAction,
    BeforeResult,
    Finding,
)

if TYPE_CHECKING:
    from .types import ExecutionContext, ExecutionResult, SecurityPlugin

logger = logging.getLogger("nanobot_security_layer")


class SecurityPipeline:

    def __init__(self) -> None:
        self._plugins: list[SecurityPlugin] = []

    def add_plugin(self, plugin: SecurityPlugin) -> None:
        self._plugins.append(plugin)
        self._plugins.sort(key=lambda p: p.priority)

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
                result.findings = all_findings or None
                return result

            if result.action == BeforeAction.MODIFY and result.modified_params:
                ctx.params.update(result.modified_params)

        return BeforeResult(
            action=BeforeAction.ALLOW,
            findings=all_findings or None,
        )

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
                logger.exception("Plugin '%s' destroy error", plugin.id)
        self._plugins.clear()
