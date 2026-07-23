"""Tests for /compact summarization slash command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_agent.compaction import CompactResult

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.slash import BufferSink, SlashCommand, build_default_dispatcher
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.handlers.composite import cmd_compact
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout


def _agent_manager(tmp_path: Path, db: DBPool) -> AgentManager:
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths)
    manager._harness_manager = MagicMock()
    return manager


@pytest.fixture
def ctx(tmp_path: Path) -> SlashCtx:
    db = DBPool(tmp_path / "x.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    agent_repo = AgentRepo(db)
    agent_repo.create(agent_id="a1", user_id=1, name="bot")
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="ui", channel_subject_id="1")
    return SlashCtx(
        agent_id="a1",
        user_id=1,
        channel_type="ui",
        session_key=sk,
        thread_registry=registry,
        agent_repo=agent_repo,
        agent_manager=_agent_manager(tmp_path, db),
    )


@pytest.fixture
def dispatcher():
    return build_default_dispatcher()


@pytest.mark.asyncio
async def test_cmd_compact_calls_harness_without_reset(ctx, dispatcher) -> None:
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    assert tid

    harness = MagicMock()
    harness.acompact_conversation = AsyncMock(
        return_value=CompactResult(
            ok=True,
            summarized_count=12,
            preserved_count=4,
            file_path=f"/ws/conversation_history/{tid}.md",
            reason="ok",
        )
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)
    before = len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id))

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)

    harness.acompact_conversation.assert_awaited_once()
    assert harness.acompact_conversation.await_args.args[0] == tid
    assert len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id)) == before
    assert ctx.thread_registry.get_bound_thread_id(ctx.session_key) == tid
    text = "\n".join(sink.lines)
    assert "12" in text
    assert "conversation_history" in text
    assert "/home/" not in text


@pytest.mark.asyncio
async def test_cmd_compact_nothing_to_compact(ctx, dispatcher) -> None:
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    harness = MagicMock()
    harness.acompact_conversation = AsyncMock(
        return_value=CompactResult(ok=False, reason="nothing_to_compact")
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)
    text = "\n".join(sink.lines)
    assert "无可压缩" in text or "Nothing to compact" in text


@pytest.mark.asyncio
async def test_cmd_compact_unavailable_reason(ctx, dispatcher) -> None:
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    harness = MagicMock()
    harness.acompact_conversation = AsyncMock(
        return_value=CompactResult(ok=False, reason="unavailable", error="graph not ready")
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)
    text = "\n".join(sink.lines)
    assert "不可用" in text or "unavailable" in text.lower()
    assert "graph not ready" not in text
