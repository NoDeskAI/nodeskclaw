"""Policy Gate plugin — tool allow/deny, path ACL, command blacklist.

Runs in the Before phase. Evaluates tool calls against configured rules
and returns allow/deny/monitor decisions.
"""

from __future__ import annotations

import logging
import re
from fnmatch import fnmatch
from typing import Any

from ..types import (
    AfterResult,
    BeforeAction,
    BeforeResult,
    ExecutionContext,
    ExecutionResult,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)


class _ToolRule:
    __slots__ = ("action", "denied_paths", "denied_commands")

    def __init__(
        self,
        action: str = "allow",
        denied_paths: list[str] | None = None,
        denied_commands: list[re.Pattern[str]] | None = None,
    ) -> None:
        self.action = action
        self.denied_paths = denied_paths or []
        self.denied_commands = denied_commands or []


class PolicyGatePlugin:
    def __init__(self, priority: int = 10) -> None:
        self._id = "policy-gate"
        self._priority = priority
        self._mode: str = "monitor"
        self._rules: dict[str, _ToolRule] = {}

    @property
    def id(self) -> str:
        return self._id

    @property
    def priority(self) -> int:
        return self._priority

    async def initialize(self, config: dict[str, Any]) -> None:
        self._mode = config.get("mode", "monitor")
        tools_cfg = config.get("tools", {})
        for tool_name, rule_raw in tools_cfg.items():
            self._rules[tool_name] = _ToolRule(
                action=rule_raw.get("action", "allow"),
                denied_paths=rule_raw.get("denied_paths", []),
                denied_commands=[
                    re.compile(p) for p in rule_raw.get("denied_commands", [])
                ],
            )

    async def destroy(self) -> None:
        pass

    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult:
        if self._mode == "disable":
            return BeforeResult()

        rule = self._rules.get(ctx.tool_name)
        if not rule:
            return BeforeResult()

        if rule.action == "deny":
            return self._deny(ctx.tool_name, f"Tool '{ctx.tool_name}' is denied by policy")

        violation = self._check_params(ctx.tool_name, ctx.params, rule)
        if violation:
            return self._deny(ctx.tool_name, violation)

        return BeforeResult()

    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult:
        return AfterResult()

    def _check_params(self, tool_name: str, params: dict[str, Any], rule: _ToolRule) -> str | None:
        if tool_name in ("exec", "shell", "bash"):
            cmd = str(params.get("command", params.get("cmd", "")))
            for pattern in rule.denied_commands:
                if pattern.search(cmd):
                    return f"Command matches denied pattern: {pattern.pattern}"

        if tool_name in ("read_file", "write_file", "edit_file", "file_read", "file_write", "file_edit"):
            file_path = str(params.get("path", params.get("file_path", "")))
            for pattern in rule.denied_paths:
                if fnmatch(file_path, pattern) or file_path.endswith(pattern.lstrip("*")):
                    return f"Path '{file_path}' matches denied pattern: {pattern}"

        return None

    def _deny(self, tool_name: str, reason: str) -> BeforeResult:
        finding = Finding(
            plugin_id=self._id,
            category="POLICY_VIOLATION",
            severity=Severity.HIGH,
            message=reason,
        )

        if self._mode == "monitor":
            logger.warning("[monitor] %s -> %s", tool_name, reason)
            return BeforeResult(findings=[finding])

        return BeforeResult(
            action=BeforeAction.DENY,
            reason=reason,
            message=f"Security policy: {reason}. Try a different approach.",
            findings=[finding],
        )
