"""tests/unit/test_gateway_push.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_gateway.models import ChannelSubject

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def gateway(tmp_path: Path) -> Gateway:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    AgentRepo(db).create(agent_id="other", user_id=1, name="Other")
    repos = MagicMock()
    repos.session_repo = SessionRepo(db)
    repos.thread_repo = ThreadRepo(db)
    repos.channel_repo = MagicMock()
    agent_manager = MagicMock()
    harness = MagicMock()

    async def stream(_agent_id, _request):
        yield {"type": "chunk"}

    agent_manager.stream = stream
    agent_manager.get_agent.return_value = harness

    gw = Gateway(agent_manager=agent_manager, repos=repos)
    gw._channel_manager = MagicMock()
    gw._channel_manager.channel_ids = ["ch-1"]
    gw._channel_manager.push_text = AsyncMock()
    return gw


@pytest.mark.asyncio
async def test_push_to_session_im_delegates_to_channel_manager(gateway: Gateway) -> None:
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_1")
    gateway.thread_registry._threads.insert(
        thread_id="thr_im",
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        session_key=sk,
    )
    gateway.thread_registry._sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        chat_type="dm",
        thread_id="thr_im",
        channel_subject_id="ou_1",
        channel_chat_type="dm",
        channel_metadata={"channel_type": "feishu", "user_id": 1},
        channel_id="ch-1",
    )

    await gateway.push_text_from_session("a1", sk, "hello", task_type="text")
    gateway._channel_manager.push_text.assert_awaited_once()
    args = gateway._channel_manager.push_text.await_args
    assert args.args[0] == "ch-1"
    assert args.args[2] == "hello"


@pytest.mark.asyncio
async def test_rebind_repairs_stale_session_agent_id(gateway: Gateway) -> None:
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    gateway.thread_registry._threads.insert(
        thread_id="thr_stale",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
    )
    gateway.thread_registry._sessions.upsert(
        session_key=sk,
        agent_id="other",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_stale",
    )

    await gateway.thread_registry.rebind(session_key=sk, thread_id="thr_stale", agent_id="a1")
    row = gateway.thread_registry.get_session(sk)
    assert row is not None
    assert row.agent_id == "a1"


@pytest.mark.asyncio
async def test_push_text_delegates_to_channel_manager(gateway: Gateway) -> None:
    subject = ChannelSubject(subject_id="ou_1", chat_type="dm", metadata={})

    await gateway.push_text("feishu", "ch-1", subject, "ping")

    gateway._channel_manager.push_text.assert_awaited_once_with("ch-1", subject, "ping")


@pytest.mark.asyncio
async def test_push_text_from_session_cron_text_pushes_prompt(gateway: Gateway) -> None:
    sk = ThreadRegistry.make_key(
        agent_id="a1",
        channel_type="qq",
        channel_subject_id="openid_1",
        channel_chat_type="dm",
    )
    gateway.thread_registry._threads.insert(
        thread_id="thr_qq",
        agent_id="a1",
        user_id=1,
        channel_type="qq",
        session_key=sk,
    )
    gateway.thread_registry._sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="qq",
        chat_type="dm",
        thread_id="thr_qq",
        channel_subject_id="openid_1",
        channel_chat_type="dm",
        channel_metadata={"channel_type": "qq"},
        channel_id="ch-1",
    )

    await gateway.push_text_from_session("a1", sk, "cron ping", task_type="text")
    gateway._channel_manager.push_text.assert_awaited_once()
    args = gateway._channel_manager.push_text.await_args
    subject = args.args[1]
    assert subject.subject_id == "openid_1"
    assert subject.chat_type == "dm"
    assert args.args[2] == "cron ping"


@pytest.mark.asyncio
async def test_push_text_from_session_cron_agent_im_pushes_reply(gateway: Gateway) -> None:
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_1")
    gateway.thread_registry._threads.insert(
        thread_id="thr_im2",
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        session_key=sk,
    )
    gateway.thread_registry._sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        chat_type="dm",
        thread_id="thr_im2",
        channel_subject_id="ou_1",
        channel_chat_type="dm",
        channel_metadata={"channel_type": "feishu"},
        channel_id="ch-1",
    )

    async def stream_with_token(_agent_id, _request):
        yield {"type": "token", "content": "AI reply"}

    gateway._agent_manager.stream = stream_with_token

    await gateway.push_text_from_session("a1", sk, "run agent", task_type="agent")
    gateway._channel_manager.push_text.assert_awaited_once()
    assert gateway._channel_manager.push_text.await_args.args[2] == "AI reply"


@pytest.mark.asyncio
async def test_push_text_from_session_dashboard_agent_pushes_ws(gateway: Gateway) -> None:
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    gateway.thread_registry._threads.insert(
        thread_id="thr_dash",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=sk,
    )
    gateway.thread_registry._sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_dash",
        channel_metadata={"ws_connection_id": "conn-1"},
    )

    async def stream_with_token(_agent_id, _request):
        yield {"type": "token", "content": "cron reply"}

    gateway._agent_manager.stream = stream_with_token

    await gateway.push_text_from_session("a1", sk, "run", task_type="agent")
    row = gateway.thread_registry.get_session(sk)
    assert row is not None
    assert row.unread_count == 1
    gateway._channel_manager.push_text.assert_awaited_once()
    assert gateway._channel_manager.push_text.await_args.args[0] == "octop-dashboard"
    assert gateway._channel_manager.push_text.await_args.args[2] == "cron reply"
