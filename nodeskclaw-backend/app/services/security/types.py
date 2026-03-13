"""Unified types for tool execution security evaluation.

These types define the contract between the WebSocket endpoint, the
SecurityPipeline orchestrator, and individual SecurityPlugin implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class BeforeAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"


class AfterAction(str, Enum):
    PASS = "pass"
    REDACT = "redact"
    FLAG = "flag"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Finding:
    plugin_id: str
    category: str
    severity: Severity
    message: str
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "plugin_id": self.plugin_id,
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class ExecutionContext:
    tool_name: str
    params: dict[str, Any]
    agent_instance_id: str = ""
    workspace_id: str = ""
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    result: str | None = None
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class BeforeResult:
    action: BeforeAction = BeforeAction.ALLOW
    reason: str | None = None
    message: str | None = None
    modified_params: dict[str, Any] | None = None
    findings: list[Finding] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"action": self.action.value}
        if self.reason:
            d["reason"] = self.reason
        if self.message:
            d["message"] = self.message
        if self.modified_params:
            d["modified_params"] = self.modified_params
        if self.findings:
            d["findings"] = [f.to_dict() for f in self.findings]
        return d


@dataclass
class AfterResult:
    action: AfterAction = AfterAction.PASS
    reason: str | None = None
    message: str | None = None
    modified_result: str | None = None
    findings: list[Finding] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"action": self.action.value}
        if self.reason:
            d["reason"] = self.reason
        if self.message:
            d["message"] = self.message
        if self.modified_result:
            d["modified_result"] = self.modified_result
        if self.findings:
            d["findings"] = [f.to_dict() for f in self.findings]
        return d


@runtime_checkable
class SecurityPlugin(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    async def initialize(self, config: dict[str, Any]) -> None: ...
    async def destroy(self) -> None: ...
    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult: ...
    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult: ...
