"""CronDeliveryService: canonical checkpoint, channel push, and best-effort extras."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop.infra.cron.delivery import CronDeliveryCommand, CronDeliveryService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


def _command(**overrides: object) -> CronDeliveryCommand:
    values: dict[str, object] = {
        "cron_id": "j1",
        "cron_name": "喝水提醒",
        "agent_id": "a1",
        "user_id": 1,
        "session_key": "sk",
        "prompt": "记得喝水",
        "fresh_thread": False,
        "task_type": "text",
        "model": None,
        "mcp_servers": (),
    }
    values.update(overrides)
    return CronDeliveryCommand(**values)  # type: ignore[arg-type]


async def _run_locked(_agent_id: str, _session_key: str, operation) -> None:
    await operation()


def _session(*, channel_type: str, thread_id: str = "thr1") -> MagicMock:
    session = MagicMock()
    session.channel_type = channel_type
    session.thread_id = thread_id
    session.user_id = 1
    session.agent_id = "a1"
    session.session_key = "sk"
    session.channel_id = "ch-1"
    return session


def _seed_dashboard_thread(tmp_path: Path, *, thread_id: str) -> tuple[SqlitePool, Any]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    session_key = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    ThreadRepo(db).insert(
        thread_id=thread_id,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id="a1",
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id=thread_id,
    )
    session = SessionRepo(db).get(session_key)
    assert session is not None
    return db, session


@pytest.mark.asyncio
async def test_text_dashboard_appends_checkpoint_before_push() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)
    human = HumanMessage(content="Task j1: 喝水提醒 executed.", id="cron:x:human")
    ai = AIMessage(content="记得喝水", id="cron:x:assistant")
    harness = MagicMock()
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    order: list[str] = []

    async def append(_thread_id: str, _messages):
        order.append("checkpoint")
        return [human, ai]

    harness.aappend_messages = append

    async def push(*_args, **_kwargs):
        order.append("push")

    async def notify(*_args, **_kwargs):
        order.append("toast")

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = push
    gateway.notify_dashboard_push = notify

    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="en")
    repos.thread_message_repo.append_if_ready.side_effect = lambda *_a, **_k: (
        order.append("project") or 2
    )

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command())

    assert order == ["checkpoint", "project", "push", "toast"]
    assert repos.thread_message_repo.append_if_ready.call_args.args[0] == "thr1"


@pytest.mark.asyncio
async def test_text_checkpoint_failure_skips_push() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)
    harness = MagicMock()
    harness.aappend_messages = AsyncMock(side_effect=RuntimeError("checkpoint down"))
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="checkpoint down"):
        await service.deliver(_command())
    gateway.push_session_text.assert_not_awaited()
    gateway.notify_dashboard_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_projection_and_toast_failure_still_pushes() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)
    harness = MagicMock()
    harness.aappend_messages = AsyncMock(
        return_value=[
            HumanMessage(content="h", id="cron:x:human"),
            AIMessage(content="记得喝水", id="cron:x:assistant"),
        ]
    )
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock(side_effect=RuntimeError("toast down"))

    repos = MagicMock()
    repos.user_repo.get.return_value = MagicMock(locale="zh")
    repos.thread_message_repo.append_if_ready.side_effect = RuntimeError("project down")

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command())
    gateway.push_session_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_text_im_skips_checkpoint() -> None:
    session = _session(channel_type="feishu")
    agent_manager = MagicMock()
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    await service.deliver(_command())
    agent_manager.get_agent.assert_not_called()
    gateway.push_session_text.assert_awaited_once()
    gateway.notify_dashboard_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_hitl_does_not_push() -> None:
    session = _session(channel_type=ThreadRegistry.CHANNEL_DASHBOARD)

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "partial"}
        yield {"type": "hitl_required"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    repos = MagicMock()
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    with pytest.raises(RuntimeError, match="interaction"):
        await service.deliver(_command(task_type="agent", prompt="run"))
    gateway.push_session_text.assert_not_awaited()
    projected = repos.thread_message_repo.append_if_ready.call_args.args[1]
    assert projected[0].role == "human"
    assert "run" in projected[0].message_json


@pytest.mark.asyncio
async def test_agent_empty_reply_does_not_push() -> None:
    session = _session(channel_type="feishu")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "   "}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    repos = MagicMock()
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=repos,
    )
    with pytest.raises(RuntimeError, match="no visible response"):
        await service.deliver(_command(task_type="agent", prompt="run"))
    gateway.push_session_text.assert_not_awaited()
    projected = repos.thread_message_repo.append_if_ready.call_args.args[1]
    assert projected[0].role == "human"
    assert "run" in projected[0].message_json


@pytest.mark.asyncio
async def test_agent_strips_orphan_thinking_prefix() -> None:
    session = _session(channel_type="weixin")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "internal reasoning"}
        yield {"type": "token", "content": "</think>"}
        yield {"type": "token", "content": "最终学习内容"}

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    await service.deliver(_command(task_type="agent", prompt="run"))
    assert gateway.push_session_text.await_args.args[1] == "最终学习内容"


@pytest.mark.parametrize("tool_name", ["current_time", "ask_agent"])
@pytest.mark.parametrize("token_type", ["token", "delta"])
@pytest.mark.asyncio
async def test_agent_delivers_only_final_text_except_team_dispatch(
    tool_name: str, token_type: str
) -> None:
    session = _session(channel_type="weixin")
    preamble = "I'll gather the current time. "
    final = "晚间中文摘要。"

    async def stream(_aid: str, _request: dict):
        yield {"type": token_type, "content": preamble}
        yield {"type": "tool_call_chunk", "name": tool_name, "index": 0, "id": "call-1"}
        yield {
            "type": "tool_result",
            "messages": [ToolMessage(content="ok", name=tool_name, tool_call_id="call-1")],
        }
        yield {"type": token_type, "content": final}

    manager = MagicMock()
    manager.stream = stream
    manager.get_row.return_value = None
    manager.merge_turn_mcp_servers.return_value = None
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.return_value = session
    gateway.push_session_text = AsyncMock()
    service = CronDeliveryService(gateway=gateway, agent_manager=manager, repos=MagicMock())

    await service.deliver(_command(task_type="agent"))

    gateway.push_session_text.assert_awaited_once_with(
        session, preamble + final if tool_name == "ask_agent" else final, title_source="记得喝水"
    )


@pytest.mark.asyncio
async def test_agent_filtered_history_does_not_duplicate_checkpoint_answer(tmp_path: Path) -> None:
    db, session = _seed_dashboard_thread(tmp_path, thread_id="thr_filtered")
    preamble = "I'll gather the current time. "
    final = "晚间中文摘要。"
    plan = AIMessage(
        id="plan-1",
        content=preamble,
        tool_calls=[{"name": "current_time", "id": "call-1", "args": {}}],
    )
    result = ToolMessage(id="tool-1", content="18:00", name="current_time", tool_call_id="call-1")
    answer = AIMessage(id="answer-1", content=final)

    async def stream(_aid: str, request: dict):
        human = HumanMessage(id="human-1", content=request["messages"][0]["content"])
        yield {"type": "token", "content": preamble}
        yield {"type": "tool_call_chunk", "name": "current_time", "id": "call-1", "index": 0}
        yield {"type": "tool_result", "messages": [result]}
        yield {"type": "reasoning", "content": "private reasoning"}
        yield {"type": "token", "content": final}
        yield {"type": "state_snapshot", "data": {"messages": [human, plan, result, answer]}}
        yield {"type": "usage", "usage": {"input_tokens": 10, "output_tokens": 5}}

    manager = MagicMock()
    manager.stream = stream
    manager.get_row.return_value = None
    manager.merge_turn_mcp_servers.return_value = None
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.return_value = session
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)
    service = CronDeliveryService(gateway=gateway, agent_manager=manager, repos=repos)

    try:
        await service.deliver(_command(task_type="agent", session_key=session.session_key))
        gateway.push_session_text.assert_awaited_once_with(session, final, title_source="记得喝水")
        gateway.notify_dashboard_push.assert_awaited_once_with(session, "a1", final)
        rows, _ = repos.thread_message_repo.page(session.thread_id, limit=20)
        assert [row.message_id for row in rows] == ["human-1", "plan-1", "tool-1", "answer-1"]
        assert plan.content == preamble
        assert plan.tool_calls[0]["name"] == "current_time"
        assert repos.usage_repo.record.call_args.kwargs["input_tokens"] == 10
        assert repos.usage_repo.record.call_args.kwargs["output_tokens"] == 5
    finally:
        db.close()


@pytest.mark.parametrize("terminal", ["error", "hitl_required"])
@pytest.mark.parametrize("after_dispatch", [False, True])
@pytest.mark.asyncio
async def test_agent_terminal_event_never_pushes_partial_reply(
    terminal: str, after_dispatch: bool
) -> None:
    session = _session(channel_type="weixin")
    closed = False

    async def stream(_aid: str, _request: dict):
        nonlocal closed
        try:
            if after_dispatch:
                yield {"type": "token", "content": "dispatch"}
                yield {"type": "tool_call_chunk", "name": "ask_agent", "id": "call-1"}
                yield {
                    "type": "tool_result",
                    "messages": [
                        ToolMessage(content="ok", name="ask_agent", tool_call_id="call-1")
                    ],
                }
            yield {"type": "token", "content": "unconfirmed pending text"}
            yield {"type": terminal, "message": "run failed"}
            pytest.fail("terminal event must close the producer")
        finally:
            closed = True

    manager = MagicMock()
    manager.stream = stream
    manager.get_row.return_value = None
    manager.merge_turn_mcp_servers.return_value = None
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.return_value = session
    gateway.push_session_text = AsyncMock()
    repos = MagicMock()
    service = CronDeliveryService(gateway=gateway, agent_manager=manager, repos=repos)

    with pytest.raises(RuntimeError, match="run failed" if terminal == "error" else "interaction"):
        await service.deliver(_command(task_type="agent"))

    assert closed
    gateway.push_session_text.assert_not_awaited()
    projected = repos.thread_message_repo.append_if_ready.call_args.args[1]
    assert all("unconfirmed pending text" not in item.message_json for item in projected)


@pytest.mark.asyncio
async def test_text_cron_preserves_literal_process_like_text() -> None:
    session = _session(channel_type="weixin")
    manager = MagicMock()
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.return_value = session
    gateway.push_session_text = AsyncMock()
    prompt = "I'll start by checking the time. 这是预设的提醒原文。"
    service = CronDeliveryService(gateway=gateway, agent_manager=manager, repos=MagicMock())

    await service.deliver(_command(task_type="text", prompt=prompt))

    gateway.push_session_text.assert_awaited_once_with(session, prompt, title_source=prompt)
    manager.stream.assert_not_called()


@pytest.mark.asyncio
async def test_fresh_thread_resets_before_require_session() -> None:
    session = _session(channel_type="feishu")
    order: list[str] = []

    async def reset(_key: str) -> str:
        order.append("reset")
        return "thr_new"

    def require(_agent_id: str, _key: str):
        order.append("require")
        return session

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.thread_registry.reset_by_session_key = reset
    gateway.require_session = require
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=MagicMock(),
        repos=MagicMock(),
    )
    await service.deliver(_command(fresh_thread=True, task_type="text"))
    assert order == ["reset", "require"]


@pytest.mark.asyncio
async def test_wrong_user_rejects_session() -> None:
    session = _session(channel_type="dashboard")
    session.user_id = 9
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.push_session_text = AsyncMock()

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=MagicMock(),
        repos=MagicMock(),
    )
    with pytest.raises(ValueError, match="does not belong to user"):
        await service.deliver(_command())
    gateway.push_session_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_dashboard_text_projects_into_real_sqlite(tmp_path: Path) -> None:
    db, session = _seed_dashboard_thread(tmp_path, thread_id="thr_hist")

    human = HumanMessage(
        content="Task j1: 喝水提醒 executed.",
        id="cron:01TESTHUMAN00000000000000:human",
    )
    ai = AIMessage(content="记得喝水", id="cron:01TESTHUMAN00000000000000:assistant")
    harness = MagicMock()
    harness.aappend_messages = AsyncMock(return_value=[human, ai])
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.thread_registry = ThreadRegistry(
        session_repo=SessionRepo(db), thread_repo=ThreadRepo(db)
    )
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command(session_key=session.session_key))

    page, _has_more = ThreadMessageRepo(db).page("thr_hist", limit=10)
    assert [row.role for row in page] == ["human", "ai"]
    assert page[0].message_id == human.id
    assert page[1].message_id == ai.id
    assert "j1" in page[0].message_json
    assert "记得喝水" in page[1].message_json
    titled = ThreadRepo(db).get("thr_hist")
    assert titled is not None
    assert titled.title == "喝水提醒"
    gateway.push_session_text.assert_awaited_once()
    db.close()


@pytest.mark.asyncio
async def test_agent_failure_projects_the_prompt(tmp_path: Path) -> None:
    """A run that dies mid-stream must not leave an empty conversation (#516)."""
    db, session = _seed_dashboard_thread(tmp_path, thread_id="thr_fail")

    async def _stream(_aid: str, _request: dict):
        yield {"type": "token", "content": "先查一下"}
        raise RuntimeError("tool call failed")

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.stream = _stream
    agent_manager.get_row = MagicMock(return_value=None)

    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session = MagicMock(return_value=session)
    gateway.thread_registry = ThreadRegistry(
        session_repo=SessionRepo(db), thread_repo=ThreadRepo(db)
    )
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    with pytest.raises(RuntimeError, match="tool call failed"):
        await service.deliver(
            _command(task_type="agent", prompt="记得喝水", session_key=session.session_key)
        )

    gateway.push_session_text.assert_not_awaited()
    page, _has_more = ThreadMessageRepo(db).page("thr_fail", limit=10)
    # An interrupted run still records its prompt, but unconfirmed narration
    # must not become a synthetic final answer in history.
    assert [row.role for row in page] == ["human"]
    assert "记得喝水" in page[0].message_json
    titled = ThreadRepo(db).get("thr_fail")
    assert titled is not None
    assert titled.title == "喝水提醒"
    db.close()
