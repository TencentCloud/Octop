"""Lazy-start helpers for AgentManager.ensure_loaded."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.agents.manager import AgentManager
from octop.infra.errors import ErrorCode, OctopError


def _manager(*, row: object | None, harness_agent: object | None = None) -> AgentManager:
    mgr = AgentManager.__new__(AgentManager)
    mgr._harness_manager = MagicMock()
    mgr._repos = MagicMock()
    mgr._repos.agent_repo.get.return_value = row
    mgr._octop_harness_or_none = MagicMock(return_value=harness_agent)  # type: ignore[method-assign]
    mgr._start_agent = AsyncMock(return_value=MagicMock(name="started"))  # type: ignore[method-assign]
    mgr._unavailable_error = AgentManager._unavailable_error.__get__(mgr, AgentManager)
    mgr.get_row = MagicMock(side_effect=lambda aid: row if row and row.agent_id == aid else None)  # type: ignore[method-assign]
    return mgr


@pytest.mark.asyncio
async def test_ensure_loaded_noop_when_already_running() -> None:
    live = MagicMock(name="live")
    row = SimpleNamespace(agent_id="E1", enabled=True, last_state="running")
    mgr = _manager(row=row, harness_agent=live)
    assert await mgr.ensure_loaded("E1") is live
    mgr._start_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_loaded_starts_stopped_agent() -> None:
    row = SimpleNamespace(agent_id="E2", enabled=True, last_state="stopped")
    mgr = _manager(row=row, harness_agent=None)
    started = await mgr.ensure_loaded("E2")
    assert started is mgr._start_agent.return_value
    mgr._start_agent.assert_awaited_once()
    assert mgr._start_agent.await_args.kwargs.get("init_workspace") is False


@pytest.mark.asyncio
async def test_ensure_loaded_does_not_retry_failed() -> None:
    row = SimpleNamespace(agent_id="E3", enabled=True, last_state="failed")
    mgr = _manager(row=row, harness_agent=None)
    with pytest.raises(OctopError) as ei:
        await mgr.ensure_loaded("E3")
    assert ei.value.code is ErrorCode.AGENT_FAILED
    mgr._start_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_loaded_rejects_disabled() -> None:
    row = SimpleNamespace(agent_id="E4", enabled=False, last_state="stopped")
    mgr = _manager(row=row, harness_agent=None)
    with pytest.raises(OctopError) as ei:
        await mgr.ensure_loaded("E4")
    assert ei.value.code is ErrorCode.AGENT_DISABLED
    mgr._start_agent.assert_not_awaited()
