"""Tests for /compact summarization slash command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_harness.compaction import CompactResult

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
from octop.infra.gateway.slash.handlers.compact_model import compact_route
from octop.infra.gateway.slash.handlers.composite import _short_offload_path, cmd_compact
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout


def _agent_manager(tmp_path: Path, db: SqlitePool) -> AgentManager:
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    services.provider_repo.create(
        name="Tencent Cloud HAI",
        kind="openai_compat",
        base_url="https://provider.invalid",
        api_key="test",
        models_json='[{"id":"MiniMax-M2.7","enabled":true}]',
    )
    services.provider_repo.create(
        name="DeepSeek",
        kind="openai_compat",
        base_url="https://provider.invalid",
        api_key="test",
        models_json='[{"id":"deepseek-chat","enabled":true}]',
    )
    manager = AgentManager(repos=services.repos, paths=services.paths)
    harness_mgr = MagicMock()
    harness_mgr.get_thread_model.return_value = None
    manager._harness_manager = harness_mgr
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
        user_repo=UserRepo(db),
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
    before = len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id, user_id=ctx.user_id))

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)

    harness.acompact_conversation.assert_awaited_once()
    assert harness.acompact_conversation.await_args.args[0] == tid
    assert (
        len(ctx.thread_registry.list_threads(agent_id=ctx.agent_id, user_id=ctx.user_id)) == before
    )
    assert ctx.thread_registry.get_bound_thread_id(ctx.session_key) == tid
    text = "\n".join(sink.lines)
    assert "12" in text
    assert "conversation_history" in text
    assert "/home/" not in text


@pytest.mark.asyncio
async def test_cmd_compact_shows_octop_relative_offload_path(ctx, dispatcher) -> None:
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
            summarized_count=3,
            preserved_count=4,
            file_path=f"/Users/wally/.octop/workspaces/X/.octop/conversation_history/{tid}.md",
            reason="ok",
        )
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)

    text = "\n".join(sink.lines)
    assert ".octop/conversation_history/" in text
    assert "/Users/wally" not in text
    assert "/home/" not in text


def test_short_offload_path_hides_windows_macos_and_linux_hosts() -> None:
    tid = "thr_win"
    cases = (
        rf"C:\Users\wally\.octop\workspaces\X\.octop\conversation_history\{tid}.md",
        rf"\\?\C:\Users\wally\.octop\workspaces\X\.octop\conversation_history\{tid}.md",
        f"/home/wally/.octop/workspaces/X/.octop/conversation_history/{tid}.md",
        f"/Users/wally/.octop/workspaces/X/.octop/conversation_history/{tid}.md",
        f"C:/Users/wally/.octop/conversation_history/{tid}.md",
    )
    for raw in cases:
        got = _short_offload_path(raw)
        assert got == f".octop/conversation_history/{tid}.md"
        assert "\\" not in got
        assert "C:" not in got
        assert "/Users/" not in got
        assert "/home/" not in got
    assert (
        _short_offload_path(rf"D:\data\conversation_history\{tid}.md")
        == f"conversation_history/{tid}.md"
    )


@pytest.mark.asyncio
async def test_cmd_compact_shows_windows_offload_path(ctx, dispatcher) -> None:
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
            summarized_count=3,
            preserved_count=4,
            file_path=rf"C:\Users\wally\.octop\workspaces\X\.octop\conversation_history\{tid}.md",
            reason="ok",
        )
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)

    text = "\n".join(sink.lines)
    assert ".octop/conversation_history/" in text
    assert "C:" not in text
    assert "Users\\wally" not in text
    assert "Users/wally" not in text


@pytest.mark.asyncio
async def test_cmd_compact_prefers_display_path_over_host_file_path(ctx, dispatcher) -> None:
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
            summarized_count=3,
            preserved_count=4,
            file_path=rf"C:\Users\wally\.octop\workspaces\X\.octop\conversation_history\{tid}.md",
            display_path=f".octop/conversation_history/{tid}.md",
            reason="ok",
        )
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)

    text = "\n".join(sink.lines)
    assert f".octop/conversation_history/{tid}.md" in text
    assert "C:" not in text
    assert "/Users/" not in text
    assert "/home/" not in text


@pytest.mark.asyncio
async def test_cmd_compact_uses_composer_model_ref(ctx, dispatcher) -> None:
    await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    assert tid
    ctx.model_ref = "Tencent Cloud HAI/MiniMax-M2.7"
    # Sticky /model must not beat the composer selection for this turn.
    ctx.agent_manager._harness_manager.get_thread_model.return_value = "DeepSeek/deepseek-chat"
    harness = MagicMock()
    harness.acompact_conversation = AsyncMock(
        return_value=CompactResult(ok=True, summarized_count=3, reason="ok")
    )
    ctx.agent_manager.get_agent = MagicMock(return_value=harness)

    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)

    assert harness.acompact_conversation.await_args.kwargs.get("model") == (
        "Tencent Cloud HAI/MiniMax-M2.7"
    )


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


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["composer", "thread", "expert", "preference"])
async def test_unconfigured_compaction_follows_conversation(ctx, dispatcher, source):
    tid = await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key, agent_id=ctx.agent_id, user_id=ctx.user_id, channel_type="ui"
    )
    ref = "DeepSeek/deepseek-chat"
    other = "Tencent Cloud HAI/MiniMax-M2.7"
    manager = ctx.agent_manager
    manager.resolve_fallback_model_ref = MagicMock(return_value=other)
    if source == "composer":
        ctx.model_ref = ref
    elif source == "thread":
        ctx.thread_registry.update_composer(tid, model_ref=ref)
    elif source == "expert":
        ctx.agent_repo.update_config(ctx.agent_id, default_model=ref)
    else:
        ctx.user_repo.set_preferences_json(
            ctx.user_id, '{"preferred_model":"DeepSeek/deepseek-chat"}'
        )
    harness = manager.get_agent(ctx.agent_id)
    harness.acompact_conversation = AsyncMock(return_value=CompactResult(ok=True, model_ref=ref))
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, BufferSink())
    harness.acompact_conversation.assert_awaited_once_with(tid, model=ref, fallback_model=other)


@pytest.mark.asyncio
async def test_compact_reports_actual_backup_and_reason(ctx, dispatcher):
    from octop_harness.compaction import CompactModelFailure

    tid = await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key, agent_id=ctx.agent_id, user_id=ctx.user_id, channel_type="ui"
    )
    manager = ctx.agent_manager
    primary = "DeepSeek/deepseek-chat"
    backup = "Tencent Cloud HAI/MiniMax-M2.7"
    manager.set_global_compaction_model(ctx.user_id, primary)
    ctx.thread_registry.update_composer(tid, model_ref=backup)
    harness = manager.get_agent(ctx.agent_id)
    harness.acompact_conversation = AsyncMock(
        return_value=CompactResult(
            ok=True,
            model_ref=backup,
            model_failures=(CompactModelFailure(primary, "http_402"),),
            summarized_count=4,
        )
    )
    sink = BufferSink()
    await cmd_compact(dispatcher, SlashCommand("compact", ""), ctx, sink)
    harness.acompact_conversation.assert_awaited_once_with(
        tid, model=primary, fallback_model=backup
    )
    text = "\n".join(sink.lines)
    assert f"本次摘要实际使用 {backup}" in text
    assert f"{primary} 失败" in text and "402" in text
    assert "/experts?compactModel=a1" in text


@pytest.mark.asyncio
async def test_expert_overrides_global_and_rechecks_access(ctx, monkeypatch):
    tid = await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key, agent_id=ctx.agent_id, user_id=ctx.user_id, channel_type="ui"
    )
    manager = ctx.agent_manager
    configured = "DeepSeek/deepseek-chat"
    conversation = "Tencent Cloud HAI/MiniMax-M2.7"
    ctx.model_ref = conversation
    manager.set_global_compaction_model(ctx.user_id, configured)
    assert compact_route(ctx, tid).primary == configured

    def set_expert(value):
        ctx.agent_repo.update_config(
            ctx.agent_id, config_json=json.dumps({"compaction": {"model": value}})
        )

    set_expert("session")
    assert compact_route(ctx, tid).primary == conversation
    manager.set_global_compaction_model(ctx.user_id, conversation)
    set_expert(configured)
    route = compact_route(ctx, tid)
    assert (route.primary, route.alternate, route.scope) == (configured, conversation, "expert")

    monkeypatch.setattr(
        manager, "model_ref_allowed_for_user", lambda _user, ref: ref == conversation
    )
    route = compact_route(ctx, tid)
    assert route.primary == conversation and route.alternate is None
    assert route.skipped and configured not in route.skipped
