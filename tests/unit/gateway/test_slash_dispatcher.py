"""tests/unit/test_slash_dispatcher.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.slash import BufferSink, SlashCommand, build_default_dispatcher
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout


def _agent_manager(tmp_path: Path, db: SqlitePool) -> AgentManager:
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths)
    manager._harness_manager = MagicMock()
    return manager


@pytest.fixture
def ctx(tmp_path: Path):
    db = SqlitePool(tmp_path / "x.db")
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
def dispatcher() -> SlashDispatcher:
    return build_default_dispatcher()


async def test_unknown_returns_error_message(dispatcher, ctx):
    sink = BufferSink()
    handled = await dispatcher.handle(SlashCommand("zzz", ""), ctx, sink)
    assert handled is True
    text = "\n".join(sink.lines)
    assert "/zzz" in text
    assert "未知指令" in text


async def test_help_lists_commands(dispatcher, ctx):
    sink = BufferSink()
    handled = await dispatcher.handle(SlashCommand("help", ""), ctx, sink)
    assert handled is True
    text = "\n".join(sink.lines).lower()
    for name in ["/new", "/list", "/switch", "/title", "/model", "/compact", "/token"]:
        assert name in text


async def test_new_creates_thread(dispatcher, ctx):
    sink = BufferSink()
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    await dispatcher.handle(SlashCommand("new", ""), ctx, sink)
    assert len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id)) >= 2


async def test_clear_is_alias_of_new(dispatcher, ctx):
    sink = BufferSink()
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    before = len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id))
    await dispatcher.handle(SlashCommand("clear", ""), ctx, sink)
    assert len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id)) == before + 1


async def test_list_returns_threads(dispatcher, ctx):
    sink = BufferSink()
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    await ctx.thread_registry.reset(
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
        channel_subject_id="1",
    )
    await dispatcher.handle(SlashCommand("list", ""), ctx, sink)
    assert sink.lines


async def test_title_sets_title(dispatcher, ctx):
    sink = BufferSink()
    tid = await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    await dispatcher.handle(SlashCommand("title", "hello world"), ctx, sink)
    row = ctx.thread_registry.get_thread(tid)
    assert row is not None
    assert row.title == "hello world"


async def test_switch_rebinds(dispatcher, ctx):
    sink = BufferSink()
    tid_a = await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    await ctx.thread_registry.reset(
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
        channel_subject_id="1",
    )
    short = tid_a[-6:]
    await dispatcher.handle(SlashCommand("switch", short), ctx, sink)
    assert ctx.thread_registry.get_bound_thread_id(ctx.session_key) == tid_a


async def test_resume_picks_previous(dispatcher, ctx):
    sink = BufferSink()
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    await ctx.thread_registry.reset(
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
        channel_subject_id="1",
    )
    await ctx.thread_registry.reset(
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
        channel_subject_id="1",
    )
    await dispatcher.handle(SlashCommand("resume", ""), ctx, sink)
    rows = ctx.thread_registry.list_threads_for_session(session_key=ctx.session_key, limit=10)
    assert ctx.thread_registry.get_bound_thread_id(ctx.session_key) == rows[1].thread_id


async def test_agent_list_shows_owned_agents(dispatcher, ctx):
    assert ctx.agent_repo is not None
    ctx.agent_repo.create(agent_id="a2", user_id=1, name="Researcher")
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("agent", "list"), ctx, sink)
    text = "\n".join(sink.lines)
    assert "bot" in text
    assert "Researcher" in text


async def test_agent_switch_emits_client_action(dispatcher, ctx):
    assert ctx.agent_repo is not None
    ctx.agent_repo.create(agent_id="a2", user_id=1, name="Researcher")
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("agent", "switch Researcher"), ctx, sink)
    assert any(
        a.get("action") == "switch_agent" and a.get("agent_id") == "a2" for a in sink.actions
    )
    assert "Researcher" in "\n".join(sink.lines)


async def test_model_set_emits_client_action(dispatcher, ctx):
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("model", "openai:gpt-4o"), ctx, sink)
    assert any(
        a.get("action") == "set_model" and a.get("model") == "openai:gpt-4o" for a in sink.actions
    )


async def test_new_emits_new_chat_action(dispatcher, ctx):
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("new", ""), ctx, sink)
    assert any(a.get("action") == "new_chat" for a in sink.actions)
