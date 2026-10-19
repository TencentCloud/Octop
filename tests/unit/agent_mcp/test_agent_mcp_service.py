"""Service validation tests for the Octop Agent MCP Gateway."""

from __future__ import annotations

import pytest

from octop.infra.agent_mcp.service import AgentMcpGatewayService


@pytest.mark.parametrize(
    ("decision", "message"),
    [
        ({"type": "edit"}, "edited_action"),
        ({"type": "respond", "message": " "}, "non-empty"),
        ({"type": "reject", "message": 7}, "must be a string"),
    ],
)
def test_validate_decisions_rejects_malformed_payloads(
    decision: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AgentMcpGatewayService._validate_decisions([decision])


def test_validate_decisions_accepts_supported_payloads() -> None:
    decisions = [
        {"type": "approve"},
        {"type": "edit", "edited_action": {"name": "safe_tool"}},
        {"type": "reject", "message": "not allowed"},
        {"type": "respond", "message": "use the staging environment"},
    ]
    assert AgentMcpGatewayService._validate_decisions(decisions) == decisions
