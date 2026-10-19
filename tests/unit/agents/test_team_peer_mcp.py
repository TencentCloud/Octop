"""tests/unit/agents/test_team_peer_mcp.py

Expert-to-expert ``ask_agent`` must hand the callee its own bound MCP servers.

The injection rides on ``PeerSession.configurable`` (no octop-harness change),
so these tests pin the branch behaviour of ``TeamManager.prepare_peer_session``
and the harness-side hand-off into ``ChatRequest.configurable``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_harness.teams.util import PeerCall, build_one_shot_request

from octop.infra.agents.teams.team_manager import TeamManager

EXPERT = SimpleNamespace(kind="expert")
TEAM = SimpleNamespace(kind="team")

CALLEE_SESSION_KEY = "expert_b:dashboard:1:peer"


def _manager(
    *,
    callee: Any = EXPERT,
    caller: Any = EXPERT,
    servers: list[str] | None = None,
    prepare: Any = None,
) -> tuple[TeamManager, MagicMock]:
    """Build a TeamManager whose agent manager is fully mocked."""
    agent_manager = MagicMock()
    agent_manager.get_row.side_effect = lambda aid: callee if aid == "expert_b" else caller
    agent_manager.default_mcp_servers.return_value = list(servers or [])
    agent_manager.validate_mcp_servers.side_effect = lambda uid, names: list(names)
    agent_manager.prepare_chat_mcp = prepare or AsyncMock(return_value=[])
    thread_registry = MagicMock()
    thread_registry.peer_session_key.return_value = CALLEE_SESSION_KEY
    thread_registry.peer_room_session_key.return_value = CALLEE_SESSION_KEY
    manager = TeamManager(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        user_repo=MagicMock(),
    )
    return manager, agent_manager


def _call(**overrides: Any) -> PeerCall:
    fields: dict[str, Any] = {
        "from_agent_id": "expert_a",
        "to_agent_id": "expert_b",
        "user_id": 1,
        "message": "对一下库存",
        "source_thread_id": None,
        "source_session_key": None,
    }
    fields.update(overrides)
    return PeerCall(**fields)


async def test_sync_peer_injects_callee_bound_mcp() -> None:
    manager, agent_manager = _manager(servers=["erp", "wms"])

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable == {"mcp_servers": ["erp", "wms"]}
    agent_manager.prepare_chat_mcp.assert_awaited_once_with(
        "expert_b", ["erp", "wms"], connector_user_id=1
    )


async def test_sync_peer_without_binding_skips_prepare() -> None:
    manager, agent_manager = _manager(servers=[])

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable is None
    agent_manager.prepare_chat_mcp.assert_not_awaited()


async def test_sync_peer_failed_load_does_not_inject(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    manager, agent_manager = _manager(servers=["erp"], prepare=AsyncMock(return_value=["erp"]))

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable is None
    agent_manager.prepare_chat_mcp.assert_awaited_once()
    assert any("peer mcp load failed" in record.getMessage() for record in caplog.records)


async def test_partial_load_failure_discards_all() -> None:
    # All-or-nothing on purpose: same contract as the turn/cron/IM chains.
    manager, agent_manager = _manager(
        servers=["erp", "wms"], prepare=AsyncMock(return_value=["erp"])
    )

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable is None
    agent_manager.prepare_chat_mcp.assert_awaited_once()


async def test_initiator_unavailable_server_is_not_injected() -> None:
    # Shared expert: the callee's owner bound a server the initiator cannot
    # see. Validation must fail closed — owner-private data sources must not
    # leak into another user's ask.
    manager, agent_manager = _manager(servers=["private_erp"])
    agent_manager.validate_mcp_servers.side_effect = ValueError(
        "mcp_servers not available for user: ['private_erp']"
    )

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable is None
    agent_manager.prepare_chat_mcp.assert_not_awaited()


async def test_non_octop_user_id_skips_injection() -> None:
    manager, agent_manager = _manager(servers=["erp"])

    prepared = await manager.prepare_peer_session(_call(user_id="wx_abc"))

    assert prepared is not None
    assert prepared.configurable is None
    agent_manager.prepare_chat_mcp.assert_not_awaited()
    called_ids = [c.args[0] for c in agent_manager.get_row.call_args_list]
    assert "expert_b" not in called_ids


async def test_sync_peer_prepare_raises_keeps_peer_session() -> None:
    manager, _ = _manager(
        servers=["erp"], prepare=AsyncMock(side_effect=RuntimeError("connector down"))
    )

    prepared = await manager.prepare_peer_session(
        _call(source_thread_id="thr_a", source_session_key="expert_a:dashboard:1:dm")
    )

    # Failure must not bubble: the harness turns a raising prepare into
    # ``prepared=None`` and the callee thread/session would be lost too.
    assert prepared is not None
    assert prepared.thread_id == "thr_a~expert_b"
    assert prepared.session_key == CALLEE_SESSION_KEY
    assert prepared.configurable is None


async def test_team_host_callee_is_not_injected() -> None:
    manager, agent_manager = _manager(callee=TEAM, servers=["erp"])

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable is None
    agent_manager.prepare_chat_mcp.assert_not_awaited()


async def test_group_dispatch_is_not_injected(monkeypatch: pytest.MonkeyPatch) -> None:
    manager, agent_manager = _manager(servers=["erp"])
    monkeypatch.setattr(manager, "_is_group_dispatch", lambda call: True)
    monkeypatch.setattr(manager, "_assignment_text", AsyncMock(return_value="task"))
    monkeypatch.setattr(manager, "_dispatch_message", AsyncMock(return_value=None))

    prepared = await manager.prepare_peer_session(_call())

    assert prepared is not None
    assert prepared.configurable == {"peer_invoke_mode": "sync"}
    agent_manager.prepare_chat_mcp.assert_not_awaited()


async def test_injected_servers_survive_runnable_config() -> None:
    manager, _ = _manager(servers=["erp"])

    prepared = await manager.prepare_peer_session(_call())
    assert prepared is not None and prepared.configurable is not None

    request = build_one_shot_request(
        user_id=1,
        agent_id="expert_b",
        text="对一下库存",
        source="dashboard",
        configurable=prepared.configurable,
    )
    configurable = request.to_runnable_config()["configurable"]

    assert configurable["mcp_servers"] == ["erp"]
    # ask/plan would wipe mcp_servers in _restrict_ask_plan_config.
    assert "conversation_mode" not in configurable
