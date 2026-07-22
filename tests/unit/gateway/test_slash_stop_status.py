"""tests/unit/test_slash_stop_status.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.slash import BufferSink, SlashCommand, build_default_dispatcher
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def ctx(tmp_path: Path):
    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot", default_model="openai/gpt-4o")
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="u1")
    manager = MagicMock()
    agent_row = AgentRepo(db).get("a1")
    manager.get_row.return_value = agent_row
    manager.get_thread_model.return_value = None
    manager.harness_manager = None
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(tmp_path)
    paths.ensure_root()
    manager.paths = paths
    return (
        SlashCtx(
            agent_id="a1",
            user_id=1,
            channel_type="feishu",
            session_key=sk,
            thread_registry=registry,
            agent_repo=AgentRepo(db),
            user_repo=UserRepo(db),
            agent_manager=manager,
            paths=paths,
            octop_version="0.1.0",
            server_started_at=1_700_000_000,
        ),
        manager,
        registry,
        sk,
    )


async def test_stop_calls_harness_cancel(ctx):
    slash_ctx, manager, registry, sk = ctx
    dispatcher = build_default_dispatcher()
    tid = await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
    )
    assert registry.get_bound_thread_id(sk) == tid

    sink = BufferSink()
    await dispatcher.handle(SlashCommand("stop", ""), slash_ctx, sink)
    manager.cancel_stream.assert_called_once_with("a1", tid)
    assert "停止" in "\n".join(sink.lines)


async def test_status_includes_version_and_model(ctx):
    slash_ctx, _manager, registry, sk = ctx
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
    )
    dispatcher = build_default_dispatcher()
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("status", ""), slash_ctx, sink)
    text = "\n".join(sink.lines)
    assert "0.1.0" in text
    assert "openai/gpt-4o" in text
    assert "会话状态" in text
    assert "a1" in text
    assert "u（id=1）" in text
    assert slash_ctx.paths is not None
    assert str(slash_ctx.paths.agent_workspace("a1")) in text


async def test_status_english_when_locale_en(ctx):
    slash_ctx, _manager, registry, sk = ctx
    slash_ctx.locale = "en"
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
    )
    dispatcher = build_default_dispatcher()
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("status", ""), slash_ctx, sink)
    assert "Session status" in "\n".join(sink.lines)
