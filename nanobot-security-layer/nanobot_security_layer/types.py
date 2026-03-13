"""Unified SecurityPlugin protocol — Python edition.

Field semantics and naming are identical to the TypeScript version
(openclaw-security-layer/src/types.ts) for cross-runtime consistency.
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


@dataclass
class ExecutionContext:
    tool_name: str
    params: dict[str, Any]
    session_id: str | None = None
    run_id: str | None = None
    tool_call_id: str | None = None
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeforeResult:
    action: BeforeAction = BeforeAction.ALLOW
    reason: str | None = None
    message: str | None = None
    modified_params: dict[str, Any] | None = None
    findings: list[Finding] | None = None


@dataclass
class ExecutionResult:
    result: str | None = None
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class AfterResult:
    action: AfterAction = AfterAction.PASS
    reason: str | None = None
    message: str | None = None
    modified_result: str | None = None
    findings: list[Finding] | None = None


@runtime_checkable
class SecurityPlugin(Protocol):
    id: str
    priority: int

    async def initialize(self, config: dict[str, Any]) -> None: ...
    async def destroy(self) -> None: ...
    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult: ...
    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult: ...


@dataclass
class PluginEntry:
    id: str
    enabled: bool
    priority: int
    config: dict[str, Any] | None = None


@dataclass
class SecurityConfig:
    plugins: list[PluginEntry]
