"""Maintenance commands use authenticated identity, bypass LLM and SQLite history locks."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash import build_default_dispatcher, catalog
from octop.infra.gateway.slash.ctx import SlashCtx, build_slash_ctx
from octop.infra.gateway.slash.runner import try_handle_slash


@pytest.fixture
def ctx():
    coordinator = MagicMock()
    coordinator.start_chat.return_value = 2
    coordinator.preview_chat.return_value = [{"name": "助手", "agent_id": "mine"}]
    return SlashCtx(
        agent_id="mine",
        user_id=1,
        channel_type="dashboard",
        session_key="key",
        thread_registry=MagicMock(),
        user_repo=SimpleNamespace(get=lambda uid: SimpleNamespace(disabled=0)),
        agent_manager=SimpleNamespace(memory_slim=coordinator),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command,all_agents",
    [
        ("/memory slim --confirm", False),
        ("/memory slim --all --confirm", True),
        ("/memory slim --confirm --all", True),
    ],
)
async def test_registered_command_starts_owned_job_and_returns_ack(ctx, command, all_agents):
    handled, lines, actions = await try_handle_slash(
        command, dispatcher=build_default_dispatcher(), ctx=ctx
    )
    assert handled
    assert "已确认整理 2 个" in "\n".join(lines)
    assert not actions
    ctx.agent_manager.memory_slim.start_chat.assert_called_once_with(
        "mine", 1, all_agents=all_agents, locale="zh"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["feishu", "weixin", "telegram"])
async def test_im_owner_fallback_cannot_authorize_maintenance(ctx, channel):
    ctx.channel_type = channel
    handled, lines, _ = await try_handle_slash(
        "/memory slim --all", dispatcher=build_default_dispatcher(), ctx=ctx
    )
    assert handled and "IM" in "\n".join(lines)
    ctx.agent_manager.memory_slim.start_chat.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [None, SimpleNamespace(disabled=1)])
async def test_missing_or_disabled_user_cannot_start(ctx, user):
    ctx.user_repo = SimpleNamespace(get=lambda _: user)
    handled, lines, _ = await try_handle_slash(
        "/memory slim", dispatcher=build_default_dispatcher(), ctx=ctx
    )
    assert handled and "当前登录用户" in "\n".join(lines)
    ctx.agent_manager.memory_slim.start_chat.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", ["/memory", "/memory slim other-id", "/memory slim --all extra"]
)
async def test_unknown_arguments_show_usage_without_start(ctx, command):
    handled, lines, _ = await try_handle_slash(
        command, dispatcher=build_default_dispatcher(), ctx=ctx
    )
    assert handled and "用法" in "\n".join(lines)
    ctx.agent_manager.memory_slim.start_chat.assert_not_called()


@pytest.mark.asyncio
async def test_status_shows_counts_and_completion_without_restart(ctx):
    ctx.agent_manager.memory_slim.chat_status.return_value = {
        "phase": "running",
        "agents": [
            {"agent_id": "mine", "phase": "deduplicating", "scanned": 100, "total": 300},
            {
                "agent_id": "second",
                "phase": "done",
                "report": {
                    "before": {"file_bytes": 2097152},
                    "after": {"file_bytes": 1048576},
                    "backup_path": "memory.sqlite.before-slim.example.bak",
                },
            },
            {"agent_id": "third", "phase": "queued"},
        ],
    }
    handled, lines, _ = await try_handle_slash(
        "/memory status", dispatcher=build_default_dispatcher(), ctx=ctx
    )
    text = "\n".join(lines)
    assert handled and "1/3" in text and "100/300" in text
    assert "2.00 → 1.00" in text and "等待前一个" in text
    ctx.agent_manager.memory_slim.start_chat.assert_not_called()


@pytest.mark.asyncio
async def test_busy_or_permission_failure_returns_error_not_llm_fallback(ctx):
    ctx.agent_manager.memory_slim.start_chat.side_effect = ValueError("任务正在进行")
    handled, lines, _ = await try_handle_slash(
        "/memory slim --confirm", dispatcher=build_default_dispatcher(), ctx=ctx
    )
    assert handled and "任务正在进行" in "\n".join(lines)


@pytest.mark.asyncio
async def test_existing_agent_manager_context_runs_maintenance_command():
    manager = MagicMock()
    manager.memory_slim.start_chat.return_value = 1
    ctx = build_slash_ctx(
        thread_registry=MagicMock(),
        agent_manager=manager,
        user_repo=SimpleNamespace(get=lambda _: SimpleNamespace(disabled=0, locale="zh")),
        agent_id="mine",
        user_id=1,
        channel_type="dashboard",
        session_key="key",
    )
    handled, lines, _ = await try_handle_slash(
        "/memory slim --confirm", dispatcher=build_default_dispatcher(), ctx=ctx
    )
    assert handled and "已确认整理 1 个" in "\n".join(lines)
    manager.memory_slim.start_chat.assert_called_once_with("mine", 1, all_agents=False, locale="zh")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/memory status", "/memory slim --confirm", "/status"])
async def test_projection_only_reply_never_waits_on_checkpointer(command, monkeypatch):
    if command == "/status":
        # Another command can choose the same policy without changing the processor.
        monkeypatch.setitem(
            catalog._CATALOG_BY_NAME,
            "status",
            replace(catalog.spec_for("status"), persist_checkpoint=False),
        )
    processor = GlobalProcessor.__new__(GlobalProcessor)
    processor._agent_manager = MagicMock()
    harness = processor._agent_manager.get_agent.return_value
    harness.aappend_messages = AsyncMock(side_effect=AssertionError("SQLite is under maintenance"))
    processor._thread_message_repo = MagicMock()
    await processor._append_slash_checkpoint(
        agent_id="mine",
        thread_id="thread",
        command=command,
        response_lines=["working"],
    )
    harness.aappend_messages.assert_not_called()
    processor._thread_message_repo.append_if_ready.assert_called_once()
    args = processor._thread_message_repo.append_if_ready.call_args.args
    assert args[0] == "thread" and len(args[1]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/help", "/models"])
async def test_default_command_policy_keeps_checkpoint_and_display_history(command):
    processor = GlobalProcessor.__new__(GlobalProcessor)
    processor._agent_manager = MagicMock()
    harness = processor._agent_manager.get_agent.return_value
    harness.aappend_messages = AsyncMock(side_effect=lambda _, messages: messages)
    processor._thread_message_repo = MagicMock()
    await processor._append_slash_checkpoint(
        agent_id="mine", thread_id="thread", command=command, response_lines=["reply"]
    )
    harness.aappend_messages.assert_awaited_once()
    messages = harness.aappend_messages.call_args.args[1]
    assert [message.content for message in messages] == [command, "reply"]
    processor._thread_message_repo.append_if_ready.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["", " --all"])
async def test_slim_explains_impact_and_requires_confirmation(ctx, suffix):
    handled, lines, _ = await try_handle_slash(
        "/memory slim" + suffix, dispatcher=build_default_dispatcher(), ctx=ctx
    )
    text = "\n".join(lines)
    assert handled
    assert "尚未开始整理" in text and "所有会话会暂停发送" in text
    assert "助手 [mine]" in text
    assert "/memory slim" + suffix + " --confirm" in text
    ctx.agent_manager.memory_slim.start_chat.assert_not_called()
    ctx.agent_manager.memory_slim.preview_chat.assert_called_once_with(
        "mine", 1, all_agents=bool(suffix), locale="zh"
    )
