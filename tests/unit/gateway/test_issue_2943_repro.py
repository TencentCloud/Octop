"""Tests for peer session MCP server loading."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_harness.teams.util import PeerCall

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def env(tmp_path: Path) -> dict[str, object]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="coordinator", user_id=1, name="Coordinator")
    AgentRepo(db).create(agent_id="expert_b", user_id=1, name="ExpertB")

    repos = MagicMock()
    repos.session_repo = SessionRepo(db)
    repos.thread_repo = ThreadRepo(db)
    repos.channel_repo = MagicMock()
    repos.audit_repo = MagicMock()
    repos.agent_repo = AgentRepo(db)
    repos.user_repo = UserRepo(db)
    repos.connector_repo = MagicMock()

    agent_manager = MagicMock()
    agent_manager.get_row.side_effect = lambda aid: AgentRepo(db).get(aid)
    agent_manager.default_mcp_servers.side_effect = lambda aid: (
        ["streamable_http_mcp"] if aid == "expert_b" else []
    )
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])

    gw = Gateway(agent_manager=agent_manager, repos=repos)
    gw._channel_manager = MagicMock()

    parent_sk = ThreadRegistry.dashboard_key(agent_id="coordinator", user_id=1)
    gw.thread_registry._threads.insert(
        thread_id="thr_parent",
        agent_id="coordinator",
        user_id=1,
        channel_type="dashboard",
        session_key=parent_sk,
    )
    gw.thread_registry._sessions.upsert(
        session_key=parent_sk,
        agent_id="coordinator",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_parent",
    )

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=gw.thread_registry,
        audit_repo=repos.audit_repo,
        agent_repo=repos.agent_repo,
        user_repo=repos.user_repo,
        connector_repo=repos.connector_repo,
        dispatcher=SlashDispatcher(),
        gateway=gw,
    )

    return {
        "processor": processor,
        "agent_manager": agent_manager,
        "parent_sk": parent_sk,
    }


@pytest.mark.asyncio
async def test_peer_session_loads_callee_mcp(env: dict) -> None:
    processor: GlobalProcessor = env["processor"]
    agent_manager: MagicMock = env["agent_manager"]
    parent_sk = env["parent_sk"]

    call = PeerCall(
        from_agent_id="coordinator",
        to_agent_id="expert_b",
        user_id=1,
        message="Query data using your MCP tool",
        source_thread_id="thr_parent",
        source_session_key=str(parent_sk),
    )

    prepared = await processor.prepare_peer_session(call)
    assert prepared is not None
    assert prepared.thread_id == "thr_parent~expert_b"

    agent_manager.prepare_chat_mcp.assert_awaited_once_with(
        "expert_b", ["streamable_http_mcp"], connector_user_id=1
    )
    assert prepared.configurable is not None
    assert prepared.configurable["mcp_servers"] == ["streamable_http_mcp"]


@pytest.mark.asyncio
async def test_peer_mcp_only_uses_callee_own_servers(env: dict) -> None:
    processor: GlobalProcessor = env["processor"]
    agent_manager: MagicMock = env["agent_manager"]
    agent_manager.default_mcp_servers.side_effect = lambda aid: (
        ["caller_only_mcp"] if aid == "coordinator" else []
    )
    call = PeerCall(
        from_agent_id="coordinator",
        to_agent_id="expert_b",
        user_id=1,
        message="x",
        source_thread_id="thr_parent",
        source_session_key=str(env["parent_sk"]),
    )
    prepared = await processor.prepare_peer_session(call)
    agent_manager.prepare_chat_mcp.assert_not_awaited()
    assert not (prepared.configurable or {}).get("mcp_servers")


@pytest.mark.asyncio
async def test_peer_mcp_load_failure_is_fail_open(env: dict) -> None:
    processor: GlobalProcessor = env["processor"]
    agent_manager: MagicMock = env["agent_manager"]
    agent_manager.prepare_chat_mcp.side_effect = RuntimeError("boom")
    call = PeerCall(
        from_agent_id="coordinator",
        to_agent_id="expert_b",
        user_id=1,
        message="x",
        source_thread_id="thr_parent",
        source_session_key=str(env["parent_sk"]),
    )
    prepared = await processor.prepare_peer_session(call)
    assert prepared is not None
    assert prepared.thread_id == "thr_parent~expert_b"
