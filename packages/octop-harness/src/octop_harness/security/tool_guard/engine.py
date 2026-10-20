"""Tool guard engine — scan tool parameters before execution."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Literal

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.security.tool_guard.models import GuardSeverity, ToolGuardResult
from octop_harness.security.tool_guard.rule_guardian import RuleBasedToolGuardian

logger = logging.getLogger(__name__)

ToolGuardMode = Literal["block", "warn", "require_approval"]

_BLOCKING_SEVERITIES: dict[ToolGuardMode, frozenset[GuardSeverity]] = {
    "block": frozenset({GuardSeverity.CRITICAL, GuardSeverity.HIGH}),
    "require_approval": frozenset({GuardSeverity.CRITICAL, GuardSeverity.HIGH, GuardSeverity.MEDIUM}),
    "warn": frozenset(),
}


class ToolGuardEngine:
    """Run registered guardians against tool call parameters."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        mode: ToolGuardMode = "block",
        rules_dir: Path | str | None = None,
    ) -> None:
        self._enabled = enabled
        self._mode = mode
        resolved = Path(rules_dir) if rules_dir is not None else None
        self._guardians = [RuleBasedToolGuardian(rules_dir=resolved)]

    def reload_rules(self) -> None:
        for guardian in self._guardians:
            guardian.reload()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def mode(self) -> ToolGuardMode:
        return self._mode

    def configure(self, *, enabled: bool | None = None, mode: ToolGuardMode | None = None) -> None:
        if enabled is not None:
            self._enabled = enabled
        if mode is not None:
            self._mode = mode

    def should_block(self, result: ToolGuardResult) -> bool:
        blocking = _BLOCKING_SEVERITIES.get(self._mode, frozenset())
        if not blocking:
            return False
        return any(f.severity in blocking for f in result.findings)

    def guard(self, tool_name: str, params: dict[str, Any]) -> ToolGuardResult | None:
        if not self._enabled:
            return None
        t0 = time.monotonic()
        result = ToolGuardResult(tool_name=tool_name, params=params)
        for guardian in self._guardians:
            try:
                result.findings.extend(guardian.guard(tool_name, params))
                result.guardians_used.append(guardian.name)
            except DEFENSIVE_OP_ERRORS as exc:
                logger.warning("Tool guardian %s failed on %s: %s", guardian.name, tool_name, exc)
        result.guard_duration_seconds = time.monotonic() - t0
        return result


def format_block_message(result: ToolGuardResult, *, mode: ToolGuardMode) -> str:
    """Human-readable denial message for blocked tool calls."""
    header = (
        "Tool call blocked by security policy (command guard)."
        if mode == "block"
        else "Tool call requires approval (command guard detected risky parameters)."
    )
    lines = [header, f"Tool: {result.tool_name}", ""]
    for finding in result.findings[:5]:
        lines.append(f"- [{finding.severity.value}] {finding.title}")
        if finding.snippet:
            lines.append(f"  snippet: {finding.snippet!r}")
        if finding.remediation:
            lines.append(f"  remediation: {finding.remediation}")
    if len(result.findings) > 5:
        lines.append(f"... and {len(result.findings) - 5} more finding(s)")
    return "\n".join(lines)


def build_tool_guard_hitl_request(result: ToolGuardResult) -> dict[str, Any]:
    """Build a ``HITLRequest`` payload for :func:`langgraph.types.interrupt`."""
    tool_name = result.tool_name
    return {
        "action_requests": [
            {
                "name": tool_name,
                "args": dict(result.params),
                "description": format_block_message(result, mode="require_approval"),
            }
        ],
        "review_configs": [
            {
                "action_name": tool_name,
                "allowed_decisions": ["approve", "reject"],
            }
        ],
    }


__all__ = [
    "ToolGuardEngine",
    "ToolGuardMode",
    "ToolGuardResult",
    "build_tool_guard_hitl_request",
    "format_block_message",
]
