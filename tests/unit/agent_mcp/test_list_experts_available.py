"""list_octop_experts exposes callable availability."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from octop.infra.agent_mcp.service import AgentMcpGatewayService
from octop.infra.users.identity import User


def test_list_experts_marks_running_as_available() -> None:
    rows = [
        SimpleNamespace(
            agent_id="run",
            name="Run",
            description="",
            kind="expert",
            last_state="running",
            default_model=None,
            template_name=None,
            is_shared=False,
            enabled=True,
            owner_user_id=1,
        ),
        SimpleNamespace(
            agent_id="stop",
            name="Stop",
            description="",
            kind="expert",
            last_state="stopped",
            default_model=None,
            template_name=None,
            is_shared=False,
            enabled=True,
            owner_user_id=1,
        ),
    ]
    manager = MagicMock()
    manager.list_rows.return_value = rows
    svc = AgentMcpGatewayService(agent_manager=manager, gateway=MagicMock())
    svc._can_access = MagicMock(return_value=True)  # type: ignore[method-assign]
    payload = svc.list_experts(User(id=1, username="a", role="admin", display_name="A"))
    by_id = {item["expert_id"]: item for item in payload["experts"]}
    assert by_id["run"]["available"] is True
    assert by_id["stop"]["available"] is False
    assert by_id["stop"]["state"] == "stopped"
