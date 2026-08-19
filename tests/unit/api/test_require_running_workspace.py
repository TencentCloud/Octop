"""Workspace I/O should survive a harness rebuild window."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.api.common.workspace import require_running_workspace
from octop.infra.errors import ErrorCode, OctopError


def _server(
    *, row: object, get_agent: object, workspace_for_agent: object = None
) -> SimpleNamespace:
    registry = MagicMock()
    registry.get_row.return_value = row
    registry.get_agent.side_effect = get_agent
    registry.workspace_for_agent.return_value = workspace_for_agent
    return SimpleNamespace(app_runtime=SimpleNamespace(agent_registry=registry))


@pytest.mark.asyncio
async def test_require_running_workspace_uses_live_handle() -> None:
    live_ws = object()
    row = SimpleNamespace(agent_id="A1", user_id=1, is_shared=0, enabled=True, last_state="running")
    user = SimpleNamespace(id=1, is_admin=False)
    agent = SimpleNamespace(workspace=live_ws)
    server = _server(row=row, get_agent=lambda _aid: agent)

    ws = await require_running_workspace("A1", user=user, as_user=None, server=server)
    assert ws is live_ws
    server.app_runtime.agent_registry.workspace_for_agent.assert_not_called()


@pytest.mark.asyncio
async def test_require_running_workspace_falls_back_during_rebuild() -> None:
    fallback_ws = object()
    row = SimpleNamespace(agent_id="A1", user_id=1, is_shared=0, enabled=True, last_state="running")
    user = SimpleNamespace(id=1, is_admin=False)
    server = _server(
        row=row,
        get_agent=OctopError(ErrorCode.AGENT_NOT_RUNNING, "agent 'A1' not running"),
        workspace_for_agent=fallback_ws,
    )

    ws = await require_running_workspace("A1", user=user, as_user=None, server=server)
    assert ws is fallback_ws
    server.app_runtime.agent_registry.workspace_for_agent.assert_called_once_with("A1")


@pytest.mark.asyncio
async def test_require_running_workspace_still_raises_when_stopped() -> None:
    row = SimpleNamespace(agent_id="A1", user_id=1, is_shared=0, enabled=True, last_state="stopped")
    user = SimpleNamespace(id=1, is_admin=False)
    server = _server(
        row=row,
        get_agent=OctopError(ErrorCode.AGENT_NOT_RUNNING, "agent 'A1' not running"),
        workspace_for_agent=object(),
    )

    with pytest.raises(OctopError) as ei:
        await require_running_workspace("A1", user=user, as_user=None, server=server)
    assert ei.value.code is ErrorCode.AGENT_NOT_RUNNING
    server.app_runtime.agent_registry.workspace_for_agent.assert_not_called()


@pytest.mark.asyncio
async def test_require_running_workspace_reraises_when_fallback_missing() -> None:
    row = SimpleNamespace(agent_id="A1", user_id=1, is_shared=0, enabled=True, last_state="running")
    user = SimpleNamespace(id=1, is_admin=False)
    server = _server(
        row=row,
        get_agent=OctopError(ErrorCode.AGENT_NOT_RUNNING, "agent 'A1' not running"),
        workspace_for_agent=None,
    )

    with pytest.raises(OctopError) as ei:
        await require_running_workspace("A1", user=user, as_user=None, server=server)
    assert ei.value.code is ErrorCode.AGENT_NOT_RUNNING
    server.app_runtime.agent_registry.workspace_for_agent.assert_called_once_with("A1")


@pytest.mark.asyncio
async def test_require_running_workspace_does_not_mask_failed_agent() -> None:
    row = SimpleNamespace(agent_id="A1", user_id=1, is_shared=0, enabled=True, last_state="failed")
    user = SimpleNamespace(id=1, is_admin=False)
    server = _server(
        row=row,
        get_agent=OctopError(ErrorCode.AGENT_FAILED, "agent 'A1' failed to start"),
        workspace_for_agent=object(),
    )

    with pytest.raises(OctopError) as ei:
        await require_running_workspace("A1", user=user, as_user=None, server=server)
    assert ei.value.code is ErrorCode.AGENT_FAILED
    server.app_runtime.agent_registry.workspace_for_agent.assert_not_called()
