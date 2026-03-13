"""Result types for security evaluation — Python thin client edition.

These types mirror the JSON response structure from the backend WebSocket
security endpoint. No plugin/pipeline types; those live in the backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
class BeforeResult:
    action: BeforeAction = BeforeAction.ALLOW
    reason: str | None = None
    message: str | None = None
    modified_params: dict[str, Any] | None = None
    findings: list[Finding] | None = None


@dataclass
class AfterResult:
    action: AfterAction = AfterAction.PASS
    reason: str | None = None
    message: str | None = None
    modified_result: str | None = None
    findings: list[Finding] | None = None
