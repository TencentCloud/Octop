"""Tests for /history conversation stats."""

from __future__ import annotations

from dataclasses import replace
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
from octop.infra.gateway.slash.formatting import format_unix_datetime
from octop.infra.gateway.slash.handlers.composite import cmd_history
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout


def test_format_unix_datetime_uses_server_timezone() -> None:
    assert format_unix_datetime(1_700_000_000, "Asia/Shanghai") == "2023-11-15 06:13:20"
    assert format_unix_datetime(1_700_000_000, "UTC") == "2023-11-14 22:13:20"
    assert format_unix_datetime(1_700_000_000, "not-a-zone") == "2023-11-14 22:13:20"


def _agent_manager(tmp_path: Path, db: SqlitePool) -> AgentManager:
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths, config=services.config)
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


@pytest.mark.asyncio
async def test_cmd_history_formats_last_active(ctx: SlashCtx) -> None:
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    assert tid
    row = ctx.thread_registry.get_thread(tid)
    assert row is not None
    ctx.thread_registry.get_thread = MagicMock(  # type: ignore[method-assign]
        return_value=replace(row, last_active=1_700_000_000)
    )
    ctx.agent_manager.get_agent = MagicMock(side_effect=KeyError("offline"))  # type: ignore[method-assign]

    sink = BufferSink()
    await cmd_history(build_default_dispatcher(), SlashCommand("history", ""), ctx, sink)
    text = "\n".join(sink.lines)
    assert "2023-11-15 06:13:20" in text
    assert "1700000000" not in text


@pytest.mark.asyncio
async def test_cmd_history_uses_ctx_timezone(ctx: SlashCtx) -> None:
    ctx.default_timezone = "UTC"
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    assert tid
    row = ctx.thread_registry.get_thread(tid)
    assert row is not None
    ctx.thread_registry.get_thread = MagicMock(  # type: ignore[method-assign]
        return_value=replace(row, last_active=1_700_000_000)
    )
    ctx.agent_manager.get_agent = MagicMock(side_effect=KeyError("offline"))  # type: ignore[method-assign]

    sink = BufferSink()
    await cmd_history(build_default_dispatcher(), SlashCommand("history", ""), ctx, sink)
    text = "\n".join(sink.lines)
    assert "2023-11-14 22:13:20" in text
    assert "2023-11-15 06:13:20" not in text
