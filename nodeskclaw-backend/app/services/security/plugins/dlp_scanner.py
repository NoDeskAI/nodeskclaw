"""DLP Scanner plugin — sensitive data detection and redaction.

Runs in the After phase. Scans tool execution results for sensitive
patterns (API keys, tokens, PII) and optionally redacts them.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..types import (
    AfterAction,
    AfterResult,
    BeforeResult,
    ExecutionContext,
    ExecutionResult,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)

_DEFAULT_PATTERNS: list[dict[str, str]] = [
    {"name": "AWS Access Key", "pattern": r"AKIA[0-9A-Z]{16}", "severity": "critical"},
    {"name": "AWS Secret Key", "pattern": r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*\S{20,}", "severity": "critical"},
    {"name": "Generic API Key", "pattern": r"(?i)(api[_-]?key|apikey|api_secret)\s*[:=]\s*['\"]?\S{16,}['\"]?", "severity": "high"},
    {"name": "Generic Token", "pattern": r"(?i)(bearer|token|secret|password|passwd)\s*[:=]\s*['\"]?\S{8,}['\"]?", "severity": "high"},
    {"name": "Private Key", "pattern": r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", "severity": "critical"},
    {"name": "GitHub Token", "pattern": r"gh[pousr]_[0-9a-zA-Z]{36,}", "severity": "critical"},
]


class _CompiledPattern:
    __slots__ = ("name", "regex", "severity")

    def __init__(self, name: str, regex: re.Pattern[str], severity: Severity) -> None:
        self.name = name
        self.regex = regex
        self.severity = severity


class DlpScannerPlugin:
    def __init__(self, priority: int = 50) -> None:
        self._id = "dlp-scanner"
        self._priority = priority
        self._mode: str = "flag"
        self._patterns: list[_CompiledPattern] = []

    @property
    def id(self) -> str:
        return self._id

    @property
    def priority(self) -> int:
        return self._priority

    async def initialize(self, config: dict[str, Any]) -> None:
        self._mode = config.get("mode", "flag")
        raw_patterns = config.get("patterns", _DEFAULT_PATTERNS)

        for p in raw_patterns:
            try:
                regex = re.compile(p["pattern"])
                severity = Severity(p.get("severity", "high"))
                self._patterns.append(_CompiledPattern(p["name"], regex, severity))
            except (re.error, ValueError) as e:
                logger.warning("Invalid DLP pattern '%s': %s", p.get("name"), e)

    async def destroy(self) -> None:
        pass

    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult:
        return BeforeResult()

    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult:
        if not result.result:
            return AfterResult()

        text = result.result
        findings: list[Finding] = []
        redacted = text

        for p in self._patterns:
            matches = list(p.regex.finditer(text))
            if not matches:
                continue

            for m in matches:
                findings.append(Finding(
                    plugin_id=self._id,
                    category="SENSITIVE_DATA",
                    severity=p.severity,
                    message=f"Detected {p.name}",
                    detail={"pattern_name": p.name, "match_start": m.start(), "match_end": m.end()},
                ))

            if self._mode == "redact":
                redacted = p.regex.sub(f"[REDACTED:{p.name}]", redacted)

        if not findings:
            return AfterResult()

        if self._mode == "redact":
            return AfterResult(
                action=AfterAction.REDACT,
                reason=f"Redacted {len(findings)} sensitive data occurrence(s)",
                message=f"Sensitive data detected and redacted ({len(findings)} occurrence(s)).",
                modified_result=redacted,
                findings=findings,
            )

        return AfterResult(
            action=AfterAction.FLAG,
            reason=f"Found {len(findings)} sensitive data occurrence(s)",
            message=f"Warning: sensitive data detected in output ({len(findings)} occurrence(s)).",
            findings=findings,
        )
