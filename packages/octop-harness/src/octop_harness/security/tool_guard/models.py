"""Data models for L1 tool-call parameter guarding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class GuardSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    SAFE = "SAFE"


class GuardThreatCategory(StrEnum):
    COMMAND_INJECTION = "command_injection"
    DATA_EXFILTRATION = "data_exfiltration"
    PATH_TRAVERSAL = "path_traversal"
    SENSITIVE_FILE_ACCESS = "sensitive_file_access"
    NETWORK_ABUSE = "network_abuse"
    CREDENTIAL_EXPOSURE = "credential_exposure"
    RESOURCE_ABUSE = "resource_abuse"
    PROMPT_INJECTION = "prompt_injection"
    CODE_EXECUTION = "code_execution"
    PRIVILEGE_ESCALATION = "privilege_escalation"


@dataclass
class GuardFinding:
    id: str
    rule_id: str
    category: GuardThreatCategory
    severity: GuardSeverity
    title: str
    description: str
    tool_name: str
    param_name: str | None = None
    matched_pattern: str | None = None
    snippet: str | None = None
    remediation: str | None = None
    guardian: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "tool_name": self.tool_name,
            "param_name": self.param_name,
            "matched_pattern": self.matched_pattern,
            "snippet": self.snippet,
            "remediation": self.remediation,
            "guardian": self.guardian,
        }


@dataclass
class ToolGuardResult:
    tool_name: str
    params: dict[str, Any]
    findings: list[GuardFinding] = field(default_factory=list)
    guard_duration_seconds: float = 0.0
    guardians_used: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_safe(self) -> bool:
        return not any(
            f.severity in (GuardSeverity.CRITICAL, GuardSeverity.HIGH, GuardSeverity.MEDIUM) for f in self.findings
        )

    @property
    def max_severity(self) -> GuardSeverity:
        if not self.findings:
            return GuardSeverity.SAFE
        order = (
            GuardSeverity.CRITICAL,
            GuardSeverity.HIGH,
            GuardSeverity.MEDIUM,
            GuardSeverity.LOW,
            GuardSeverity.INFO,
        )
        for sev in order:
            if any(f.severity == sev for f in self.findings):
                return sev
        return GuardSeverity.SAFE

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "is_safe": self.is_safe,
            "max_severity": self.max_severity.value,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "guard_duration_seconds": self.guard_duration_seconds,
            "guardians_used": self.guardians_used,
            "timestamp": self.timestamp.isoformat(),
        }


__all__ = [
    "GuardFinding",
    "GuardSeverity",
    "GuardThreatCategory",
    "ToolGuardResult",
]
