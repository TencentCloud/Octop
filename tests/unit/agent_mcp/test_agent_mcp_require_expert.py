"""Expert access checks for Agent MCP (lazy-start handles runtime separately)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.infra.agent_mcp.service import AgentMcpGatewayService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User


def _user() -> User:
    return User(id=1, username="alice", role="admin", display_name="Alice")


def _service(*, row: object) -> AgentMcpGatewayService:
    manager = MagicMock()
    manager.get_row.return_value = row
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


def test_require_expert_allows_stopped_for_lazy_start() -> None:
    row = SimpleNamespace(
        agent_id="FMC7EM",
        kind="expert",
        enabled=True,
        last_state="stopped",
        is_shared=False,
        owner_user_id=1,
    )
    svc = _service(row=row)
    assert svc._require_expert("FMC7EM", _user()) is row
