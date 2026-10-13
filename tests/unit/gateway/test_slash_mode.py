"""Slash /mode and aliases /ask /plan /craft."""

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
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout


def _agent_manager(tmp_path: Path, db: SqlitePool) -> AgentManager:
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths)
    manager._harness_manager = MagicMock()
    return manager


@pytest.fixture
def ctx(tmp_path: Path) -> SlashCtx:
    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    agent_repo = AgentRepo(db)
    agent_repo.create(agent_id="a1", user_id=1, name="bot")
    registry = ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="cli", channel_subject_id="1")
    return SlashCtx(
        agent_id="a1",
        user_id=1,
        channel_type="cli",
        session_key=sk,
        thread_registry=registry,
        agent_repo=agent_repo,
        agent_manager=_agent_manager(tmp_path, db),
    )


@pytest.mark.asyncio
async def test_mode_sets_sticky_and_alias(ctx: SlashCtx) -> None:
    dispatcher = build_default_dispatcher()
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    sink = BufferSink()
    await dispatcher.handle(SlashCommand("plan", ""), ctx, sink)
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    assert tid is not None
    row = ctx.thread_registry.get_thread(tid)
    assert row is not None
    assert row.conversation_mode == "plan"
    assert any(a.get("action") == "set_conversation_mode" for a in sink.actions)

    ctx.thread_registry.update_composer(tid, pending_plan_path="plans/foo.md")
    await dispatcher.handle(SlashCommand("mode", "ask"), ctx, BufferSink())
    row = ctx.thread_registry.get_thread(tid)
    assert row is not None
    assert row.conversation_mode == "ask"
    assert row.pending_plan_path == "plans/foo.md"
