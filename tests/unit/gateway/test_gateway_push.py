"""tests/unit/test_gateway_push.py"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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
from octop.infra.gateway.ws import WS_CHANNEL_ID


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
    gw = Gateway(agent_manager=agent_manager, repos=repos)
    gw._channel_manager = MagicMock()
    gw._channel_manager.channel_ids = ["ch-1"]
    gw._channel_manager.push_text = AsyncMock()

    async def run_in_session(_channel_id, _session_key, operation):
        await operation()

    gw._channel_manager.run_in_session = run_in_session
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

    await gateway.push_text_from_session("a1", sk, "hello")
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
async def test_push_text_from_session_im_preserves_subject(gateway: Gateway) -> None:
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

    await gateway.push_text_from_session("a1", sk, "cron ping")
    gateway._channel_manager.push_text.assert_awaited_once()
    args = gateway._channel_manager.push_text.await_args
    subject = args.args[1]
    assert subject.subject_id == "openid_1"
    assert subject.chat_type == "dm"
    assert args.args[2] == "cron ping"


@pytest.mark.asyncio
async def test_push_text_from_qq_group_session_preserves_proactive_routing(
    gateway: Gateway,
) -> None:
    sk = ThreadRegistry.make_key(
        agent_id="a1",
        channel_type="qq",
        channel_subject_id="group-openid-1",
        channel_chat_type="group",
    )
    gateway.thread_registry._threads.insert(
        thread_id="thr_qq_group",
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
        chat_type="group",
        thread_id="thr_qq_group",
        channel_subject_id="group-openid-1",
        channel_chat_type="group",
        channel_metadata={
            "channel_type": "qq",
            "msg_type": "group",
            "group_openid": "group-openid-1",
        },
        channel_id="ch-1",
    )

    await gateway.push_text_from_session("a1", sk, "proactive group message")

    args = gateway._channel_manager.push_text.await_args
    assert args.args[0] == "ch-1"
    subject = args.args[1]
    assert subject.subject_id == "group-openid-1"
    assert subject.chat_type == "group"
    assert subject.metadata["msg_type"] == "group"
    assert subject.metadata["group_openid"] == "group-openid-1"
    assert args.args[2] == "proactive group message"


def _insert_dashboard_session(gateway: Gateway, *, thread_id: str = "thr_dash") -> str:
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    gateway.thread_registry._threads.insert(
        thread_id=thread_id,
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
        thread_id=thread_id,
        channel_metadata={"ws_connection_id": "conn-1"},
    )
    return sk


@pytest.mark.asyncio
async def test_push_text_from_session_dashboard_injects_thread_id(gateway: Gateway) -> None:
    sk = _insert_dashboard_session(gateway)
    await gateway.push_text_from_session("a1", sk, "记得喝水")
    row = gateway.thread_registry.get_session(sk)
    assert row is not None
    assert row.unread_count == 1
    gateway._channel_manager.push_text.assert_awaited_once()
    args = gateway._channel_manager.push_text.await_args
    assert args.args[0] == WS_CHANNEL_ID
    subject = args.args[1]
    assert subject.metadata["thread_id"] == "thr_dash"
    assert args.args[2] == "记得喝水"


@pytest.mark.asyncio
async def test_push_text_from_session_dashboard_notifies_user(gateway: Gateway) -> None:
    sk = _insert_dashboard_session(gateway)
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("n1", capture, user_id=1)
    gateway._agent_manager.get_row.return_value = SimpleNamespace(name="Agent 1")

    await gateway.push_text_from_session("a1", sk, "记得喝水")

    assert len(frames) == 1
    frame = frames[0]
    assert frame["type"] == "dashboard_push"
    assert frame["agent_id"] == "a1"
    assert frame["thread_id"] == "thr_dash"
    assert frame["text"] == "记得喝水"
    assert frame["agent_name"] == "Agent 1"


@pytest.mark.asyncio
async def test_push_text_from_session_does_not_project_history(gateway: Gateway) -> None:
    sk = _insert_dashboard_session(gateway, thread_id="thr_text")
    await gateway.push_text_from_session("a1", sk, "记得喝水")
    gateway._repos.thread_message_repo.append_if_ready.assert_not_called()
