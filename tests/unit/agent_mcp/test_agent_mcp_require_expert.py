"""Runtime precheck for Agent MCP expert access."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.infra.agent_mcp.service import AgentMcpGatewayService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User


def _user() -> User:
    return User(id=1, username="alice", role="admin", display_name="Alice")


def _service(*, row: object, get_agent_side_effect: object | None = None) -> AgentMcpGatewayService:
    manager = MagicMock()
    manager.get_row.return_value = row
    manager.list_rows.return_value = [row]
    if get_agent_side_effect is None:
        manager.get_agent.return_value = MagicMock()
    else:
        manager.get_agent.side_effect = get_agent_side_effect
    gateway = MagicMock()
    svc = AgentMcpGatewayService(agent_manager=manager, gateway=gateway)
    svc._can_access = MagicMock(return_value=True)  # type: ignore[method-assign]
    return svc


def test_require_expert_rejects_disabled_with_agent_disabled() -> None:
    row = SimpleNamespace(
        agent_id="E1",
        kind="expert",
        enabled=False,
        last_state="stopped",
        is_shared=False,
        owner_user_id=1,
    )
    svc = _service(row=row)
    with pytest.raises(OctopError) as ei:
        svc._require_expert("E1", _user())
    assert ei.value.code is ErrorCode.AGENT_DISABLED
    svc._agent_manager.get_agent.assert_not_called()


def test_require_expert_rejects_stopped_runtime() -> None:
    row = SimpleNamespace(
        agent_id="FMC7EM",
        kind="expert",
        enabled=True,
        last_state="stopped",
        is_shared=False,
        owner_user_id=1,
    )
    svc = _service(
        row=row,
        get_agent_side_effect=OctopError(ErrorCode.AGENT_NOT_RUNNING, "agent 'FMC7EM' not running"),
    )
    with pytest.raises(OctopError) as ei:
        svc._require_expert("FMC7EM", _user())
    assert ei.value.code is ErrorCode.AGENT_NOT_RUNNING
    assert "start it in the Octop console" in ei.value.message
    assert ei.value.details.get("last_state") == "stopped"


def test_require_expert_rejects_failed_runtime() -> None:
    row = SimpleNamespace(
        agent_id="E2",
        kind="expert",
        enabled=True,
        last_state="failed",
        is_shared=False,
        owner_user_id=1,
    )
    svc = _service(
        row=row,
        get_agent_side_effect=OctopError(ErrorCode.AGENT_FAILED, "agent 'E2' failed to start"),
    )
    with pytest.raises(OctopError) as ei:
        svc._require_expert("E2", _user())
    assert ei.value.code is ErrorCode.AGENT_FAILED


def test_require_expert_allows_running() -> None:
    row = SimpleNamespace(
        agent_id="E3",
        kind="expert",
        enabled=True,
        last_state="running",
        is_shared=False,
        owner_user_id=1,
    )
    svc = _service(row=row)
    assert svc._require_expert("E3", _user()) is row
