"""CronDeliveryService: canonical checkpoint, channel push, and best-effort extras."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

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

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="interaction"):
        await service.deliver(_command(task_type="agent", prompt="run"))
    gateway.push_session_text.assert_not_awaited()


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

    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=agent_manager,
        repos=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="no visible response"):
        await service.deliver(_command(task_type="agent", prompt="run"))
    gateway.push_session_text.assert_not_awaited()


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
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    thread_id = "thr_hist"
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
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()

    repos = MagicMock()
    repos.user_repo = UserRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)

    service = CronDeliveryService(gateway=gateway, agent_manager=agent_manager, repos=repos)
    await service.deliver(_command(session_key=session_key))

    page, _has_more = ThreadMessageRepo(db).page(thread_id, limit=10)
    assert [row.role for row in page] == ["human", "ai"]
    assert page[0].message_id == human.id
    assert page[1].message_id == ai.id
    assert "j1" in page[0].message_json
    assert "记得喝水" in page[1].message_json
    gateway.push_session_text.assert_awaited_once()
