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
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.get_row = MagicMock(return_value=None)

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

    await gateway.push_text_from_session("a1", sk, "proactive group message", task_type="text")

    args = gateway._channel_manager.push_text.await_args
    assert args.args[0] == "ch-1"
    subject = args.args[1]
    assert subject.subject_id == "group-openid-1"
    assert subject.chat_type == "group"
    assert subject.metadata["msg_type"] == "group"
    assert subject.metadata["group_openid"] == "group-openid-1"
    assert args.args[2] == "proactive group message"


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
async def test_push_text_from_session_cron_agent_strips_orphan_thinking_prefix(
    gateway: Gateway,
) -> None:
    sk = ThreadRegistry.make_key(
        agent_id="a1",
        channel_type="weixin",
        channel_subject_id="wx_1",
    )
    gateway.thread_registry._threads.insert(
        thread_id="thr_weixin_cron",
        agent_id="a1",
        user_id=1,
        channel_type="weixin",
        session_key=sk,
    )
    gateway.thread_registry._sessions.upsert(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="weixin",
        chat_type="dm",
        thread_id="thr_weixin_cron",
        channel_subject_id="wx_1",
        channel_chat_type="dm",
        channel_metadata={"channel_type": "weixin"},
        channel_id="ch-1",
    )

    async def stream_with_thinking_leak(_agent_id, _request):
        yield {"type": "token", "content": "internal reasoning"}
        yield {"type": "token", "content": "</think>"}
        yield {"type": "token", "content": "最终学习内容"}

    gateway._agent_manager.stream = stream_with_thinking_leak

    await gateway.push_text_from_session("a1", sk, "run agent", task_type="agent")

    gateway._channel_manager.push_text.assert_awaited_once()
    assert gateway._channel_manager.push_text.await_args.args[2] == "最终学习内容"


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
async def test_push_text_from_session_dashboard_text_notifies_user(gateway: Gateway) -> None:
    sk = _insert_dashboard_session(gateway)
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("n1", capture, user_id=1)
    gateway._agent_manager.get_row.return_value = SimpleNamespace(name="Agent 1")

    await gateway.push_text_from_session("a1", sk, "记得喝水", task_type="text")

    assert len(frames) == 1
    frame = frames[0]
    assert frame["type"] == "dashboard_push"
    assert frame["agent_id"] == "a1"
    assert frame["thread_id"] == "thr_dash"
    assert frame["text"] == "记得喝水"
    assert frame["agent_name"] == "Agent 1"


@pytest.mark.asyncio
async def test_push_text_from_session_dashboard_agent_does_not_notify(
    gateway: Gateway,
) -> None:
    sk = _insert_dashboard_session(gateway, thread_id="thr_agent")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("n1", capture, user_id=1)

    async def stream_with_token(_agent_id, _request):
        yield {"type": "token", "content": "cron reply"}

    gateway._agent_manager.stream = stream_with_token

    await gateway.push_text_from_session("a1", sk, "run", task_type="agent")
    assert frames == []
