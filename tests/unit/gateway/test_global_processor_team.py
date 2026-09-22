"""tests/unit/test_global_processor_team.py"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_agent.teams.inbox import InboxMessage
from harness_agent.teams.processor import ReplyEvent

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def processor_env(tmp_path: Path) -> dict[str, object]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="parent", user_id=1, name="Parent")
    AgentRepo(db).create(agent_id="child", user_id=1, name="Researcher")

    repos = MagicMock()
    repos.session_repo = SessionRepo(db)
    repos.thread_repo = ThreadRepo(db)
    repos.channel_repo = MagicMock()
    repos.audit_repo = MagicMock()
    repos.agent_repo = AgentRepo(db)
    repos.user_repo = UserRepo(db)
    repos.connector_repo = MagicMock()

    agent_manager = MagicMock()
    agent_manager.get_row.side_effect = lambda aid: AgentRepo(db).get(aid)

    from octop.infra.gateway.gateway import Gateway

    gw = Gateway(agent_manager=agent_manager, repos=repos)
    gw._channel_manager = MagicMock()

    parent_sk = ThreadRegistry.dashboard_key(agent_id="parent", user_id=1)
    gw.thread_registry._threads.insert(
        thread_id="thr_parent",
        agent_id="parent",
        user_id=1,
        channel_type="dashboard",
        session_key=parent_sk,
    )
    gw.thread_registry._sessions.upsert(
        session_key=parent_sk,
        agent_id="parent",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_parent",
    )

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=gw.thread_registry,
        audit_repo=repos.audit_repo,
        agent_repo=repos.agent_repo,
        user_repo=repos.user_repo,
        connector_repo=repos.connector_repo,
        dispatcher=SlashDispatcher(),
        gateway=gw,
    )
    return {"processor": processor, "gateway": gw, "parent_sk": parent_sk}


def test_compose_followup_uses_peer_display_name(processor_env: dict) -> None:
    processor = processor_env["processor"]
    msg = InboxMessage(
        id="job-1",
        target_agent_id="child",
        source_agent_id="parent",
        source_thread_id="thr_parent",
        message="survey market",
        user_id=1,
        original_user_prompt="market size?",
    )
    text = processor.compose_followup(msg, result_text="findings", error_text=None)
    assert "Researcher" in text
    assert "findings" not in text
    assert "do not repeat" in text.lower() or "不要复述" in text


def test_compose_followup_team_host_asks_for_wrapup(processor_env: dict) -> None:
    processor = processor_env["processor"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    msg = InboxMessage(
        id="job-2",
        target_agent_id="child",
        source_agent_id="host",
        source_thread_id="thr_parent",
        message="survey market",
        user_id=1,
    )
    text = processor.compose_followup(msg, result_text="findings", error_text=None)
    assert "Researcher" in text
    assert "findings" not in text
    assert "do not repeat" in text.lower() or "不要复述" in text


@pytest.mark.asyncio
async def test_on_reply_increments_unread_on_dashboard(processor_env: dict) -> None:
    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]

    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-1",
            status="done",
            source_agent_id="parent",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            reply_text="final synthesized reply",
            metadata={"session_key": parent_sk},
        )
    )

    session = processor_env["gateway"].thread_registry.get_session(parent_sk)  # type: ignore[attr-defined]
    assert session is not None
    assert session.unread_count == 1


@pytest.mark.asyncio
async def test_on_reply_pushes_watched_dashboard_thread(processor_env: dict) -> None:
    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    parent_sk = processor_env["parent_sk"]
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-1", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-1")

    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-watch",
            status="done",
            source_agent_id="parent",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            reply_text="team wrap-up in the open room",
            metadata={"session_key": parent_sk},
        )
    )

    session = gateway.thread_registry.get_session(parent_sk)  # type: ignore[attr-defined]
    assert session is not None
    assert session.unread_count == 0
    assert any(
        frame.get("type") == "token" and frame.get("content") == "team wrap-up in the open room"
        for frame in frames
    )
    assert any(frame.get("type") == "done" for frame in frames)


@pytest.mark.asyncio
async def test_on_reply_team_host_pushes_wrapup_live(processor_env: dict) -> None:
    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-team-wrap", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-team-wrap")

    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-team-wrap",
            status="done",
            source_agent_id="host",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            reply_text="睡眠建议已经给出，可以收工。",
            metadata={"session_key": parent_sk},
        )
    )

    tokens = [frame for frame in frames if frame.get("type") == "token"]
    assert tokens
    assert tokens[0].get("content") == "睡眠建议已经给出，可以收工。"
    assert tokens[0].get("team_wrapup") is True
    assert tokens[0].get("team_snapshot") is not True


@pytest.mark.asyncio
async def test_on_reply_publishes_wrapup_without_session_key(processor_env: dict) -> None:
    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-no-sk", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-no-sk")

    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-no-sk",
            status="done",
            source_agent_id="host",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            reply_text="没有 session_key 也要进群聊",
            metadata={},
        )
    )

    tokens = [frame for frame in frames if frame.get("type") == "token"]
    assert tokens
    assert tokens[0].get("content") == "没有 session_key 也要进群聊"


@pytest.mark.asyncio
async def test_on_reply_skips_snapshot_after_live_host_wrapup(
    processor_env: dict,
) -> None:
    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor.teams._live_host_replies.add("thr_parent")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-live-wrap", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-live-wrap")

    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-live-wrap",
            status="done",
            source_agent_id="host",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            reply_text="可以收工。",
            metadata={"session_key": parent_sk},
        )
    )

    assert [frame for frame in frames if frame.get("type") == "token"] == []
    assert "thr_parent" not in processor.teams._live_host_replies


@pytest.mark.asyncio
async def test_stream_host_followup_marks_live_and_persists(
    processor_env: dict,
) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-host-followup", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-host-followup")

    seen_threads: list[str] = []

    async def fake_stream(_agent_id: str, request: dict[str, object]) -> object:
        seen_threads.append(str(request.get("thread_id") or ""))
        yield {"type": "token", "content": "可以"}
        yield {"type": "token", "content": "收工。"}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(return_value=[AIMessage(content="可以收工。")])
    processor._agent_manager.get_agent.return_value = harness
    repo = MagicMock()
    repo.projection_status.return_value = "ready"
    repo.append_if_ready = MagicMock(return_value=1)
    processor.replace_thread_message_repo(repo)

    result = await processor.teams.stream_host_followup_to_room(
        ChatRequest(messages="wrap up", thread_id="thr_parent", agent_id="host"),
        room_thread_id="thr_parent",
        speaker_id="host",
    )
    assert result["team_live_streamed"] is True
    assert "thr_parent" in processor.teams._live_host_replies
    tokens = [frame for frame in frames if frame.get("type") == "token"]
    assert [frame.get("content") for frame in tokens] == ["可以", "收工。"]
    assert all(frame.get("team_wrapup") is True for frame in tokens)
    assert all(frame.get("team_snapshot") is not True for frame in frames)
    assert seen_threads == ["thr_parent"]
    done = [frame for frame in frames if frame.get("type") == "done"]
    assert done
    assert all(frame.get("team_wrapup") is True for frame in done)
    repo.append_if_ready.assert_called()


@pytest.mark.asyncio
async def test_stream_host_followup_waits_for_dispatch_turn(
    processor_env: dict,
) -> None:
    import asyncio

    from harness_agent.request import ChatRequest

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_manager.is_agent_active = MagicMock(return_value=False)
    started = asyncio.Event()

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        started.set()
        yield {"type": "token", "content": "可以收工。"}

    processor._agent_manager.stream = fake_stream
    gateway.ws_hub.mark_turn_active("thr_parent")
    task = asyncio.create_task(
        processor.teams.stream_host_followup_to_room(
            ChatRequest(messages="wrap up", thread_id="thr_parent", agent_id="host"),
            room_thread_id="thr_parent",
            speaker_id="host",
        )
    )
    await asyncio.sleep(0.08)
    assert not started.is_set()
    gateway.ws_hub.mark_turn_idle("thr_parent")
    await asyncio.wait_for(task, timeout=2)
    assert started.is_set()


@pytest.mark.asyncio
async def test_stream_host_followup_unwatched_does_not_skip_snapshot(
    processor_env: dict,
) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        yield {"type": "token", "content": "可以收工。"}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(return_value=[AIMessage(content="可以收工。")])
    processor._agent_manager.get_agent.return_value = harness
    repo = MagicMock()
    repo.projection_status.return_value = "ready"
    repo.append_if_ready = MagicMock(return_value=1)
    processor.replace_thread_message_repo(repo)

    result = await processor.teams.stream_host_followup_to_room(
        ChatRequest(messages="wrap up", thread_id="thr_parent", agent_id="host"),
        room_thread_id="thr_parent",
        speaker_id="host",
    )
    assert result["team_live_streamed"] is False
    assert "thr_parent" not in processor.teams._live_host_replies


@pytest.mark.asyncio
async def test_stream_host_followup_pushes_wrapup_when_no_tokens(
    processor_env: dict,
) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-silent-wrap", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-silent-wrap")

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        yield {"type": "state_snapshot", "data": {}}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(return_value=[AIMessage(content="可以收工。")])
    processor._agent_manager.get_agent.return_value = harness
    repo = MagicMock()
    repo.projection_status.return_value = "ready"
    repo.append_if_ready = MagicMock(return_value=1)
    processor.replace_thread_message_repo(repo)

    result = await processor.teams.stream_host_followup_to_room(
        ChatRequest(messages="wrap up", thread_id="thr_parent", agent_id="host"),
        room_thread_id="thr_parent",
        speaker_id="host",
    )
    assert result["team_live_streamed"] is False
    assert "thr_parent" in processor.teams._live_host_replies
    tokens = [frame for frame in frames if frame.get("type") == "token"]
    assert tokens
    assert tokens[0].get("content") == "可以收工。"
    assert tokens[0].get("team_wrapup") is True
    assert tokens[0].get("agent_id") == "host"


@pytest.mark.asyncio
async def test_record_peer_turn_persists_room_user_question(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage, HumanMessage

    processor = processor_env["processor"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    repo.projection_status = MagicMock(return_value="pending")
    repo.mark_projection = MagicMock()
    repo.page = MagicMock(return_value=([], False))
    processor.replace_thread_message_repo(repo)
    processor._agent_manager.get_agent.return_value = SimpleNamespace(
        aget_history=AsyncMock(return_value=[HumanMessage(content="我最近总失眠")])
    )

    await processor.record_peer_turn(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="请根据用户问题给出睡眠建议",
            source_thread_id="thr_parent",
            source_session_key=None,
        ),
        "thr_parent~child",
        {"messages": [AIMessage(content="建议早睡")]},
    )

    member_calls = [
        call for call in repo.append_if_ready.call_args_list if call.args[0] == "thr_parent~child"
    ]
    assert member_calls
    inputs = member_calls[0].args[1]
    roles = [item.role for item in inputs]
    assert any(role in {"human", "user"} for role in roles)
    assert any("我最近总失眠" in item.message_json for item in inputs)
    room_calls = [
        call for call in repo.append_if_ready.call_args_list if call.args[0] == "thr_parent"
    ]
    assert room_calls
    room_inputs = room_calls[0].args[1]
    assert any(
        item.role in {"ai", "assistant"} and "建议早睡" in item.message_json for item in room_inputs
    )
    repo.mark_projection.assert_called_with("thr_parent~child", "ready")


@pytest.mark.asyncio
async def test_record_peer_turn_keeps_sync_ask_agent_message(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage, HumanMessage

    processor = processor_env["processor"]
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    repo.projection_status = MagicMock(return_value="pending")
    repo.mark_projection = MagicMock()
    repo.page = MagicMock(return_value=([], False))
    processor.replace_thread_message_repo(repo)
    processor._agent_manager.get_agent.return_value = SimpleNamespace(
        aget_history=AsyncMock(return_value=[HumanMessage(content="用户对 A 说的话")])
    )

    await processor.record_peer_turn(
        PeerCall(
            from_agent_id="parent",
            to_agent_id="child",
            user_id=1,
            message="请根据任务给 B 的指令",
            source_thread_id="thr_parent",
            source_session_key=None,
        ),
        "thr_parent~child",
        {"messages": [AIMessage(content="工具结果")]},
    )

    member_calls = [
        call for call in repo.append_if_ready.call_args_list if call.args[0] == "thr_parent~child"
    ]
    assert member_calls
    payload = member_calls[0].args[1]
    joined = " ".join(item.message_json for item in payload)
    assert "请根据任务给 B 的指令" in joined
    assert "用户对 A 说的话" not in joined


@pytest.mark.asyncio
async def test_ensure_projection_leaves_pending_threads_with_history(
    processor_env: dict,
) -> None:
    processor = processor_env["processor"]
    repo = MagicMock()
    repo.projection_status = MagicMock(return_value="pending")
    repo.mark_projection = MagicMock()
    repo.page = MagicMock(return_value=([object()], False))
    processor.replace_thread_message_repo(repo)
    processor.teams._ensure_projection("thr_legacy")
    repo.mark_projection.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_peer_session_creates_callee_thread_without_rebind(
    processor_env: dict,
) -> None:
    from harness_agent.teams.util import PeerCall

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    prepared = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="parent",
            to_agent_id="child",
            user_id=1,
            message="hello",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
        )
    )
    assert prepared is not None
    assert prepared.thread_id == "thr_parent~child"
    assert prepared.session_key == "child:dashboard:1:peer:thr_parent"
    registry = processor_env["gateway"].thread_registry
    row = registry.get_thread("thr_parent~child")
    assert row is not None
    assert row.agent_id == "child"
    assert registry.get_bound_thread_id(str(parent_sk)) == "thr_parent"


@pytest.mark.asyncio
async def test_prepare_team_peer_seeds_user_question(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import HumanMessage

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_manager.teams.member_ids.return_value = ["child"]
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    repo.projection_status = MagicMock(return_value="pending")
    repo.mark_projection = MagicMock()
    repo.page = MagicMock(return_value=([], False))
    processor.replace_thread_message_repo(repo)
    processor._agent_manager.get_agent.return_value = SimpleNamespace(
        aget_history=AsyncMock(return_value=[HumanMessage(content="我最近总失眠")])
    )

    await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="请给出睡眠建议",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
        )
    )

    repo.mark_projection.assert_called_with("thr_parent~child", "ready")
    seeded = repo.append_if_ready.call_args.args[1]
    assert seeded[0].role in {"human", "user"}
    assert "我最近总失眠" in seeded[0].message_json
    assert seeded[0].message_id.startswith("team-peer:thr_parent~child:")
    assert seeded[0].message_id.endswith(":human")


@pytest.mark.asyncio
async def test_prepare_team_peer_uses_isolated_session_key(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_manager.teams.member_ids.return_value = ["child"]
    prepared = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="hello",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
            job_id="job-1",
        )
    )
    assert prepared is not None
    assert prepared.session_key == "child:dashboard:1:team:thr_parent"
    registry = processor_env["gateway"].thread_registry
    child_dm = registry.dashboard_key(agent_id="child", user_id=1)
    assert registry.get_bound_thread_id(child_dm) is None
    assert registry.get_bound_thread_id(str(parent_sk)) == "thr_parent"


@pytest.mark.asyncio
async def test_prepare_followup_seeds_new_user_question(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import HumanMessage

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_manager.teams.member_ids.return_value = ["child"]
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    repo.projection_status = MagicMock(return_value="ready")
    repo.page = MagicMock(
        return_value=(
            [SimpleNamespace(role="human", message_json='{"content": "上一轮的问题"}')],
            False,
        )
    )
    processor.replace_thread_message_repo(repo)
    processor._agent_manager.get_agent.return_value = SimpleNamespace(
        aget_history=AsyncMock(return_value=[HumanMessage(content="请改成早睡建议")])
    )

    first = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="继续睡眠建议",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
            job_id="job-1",
        )
    )
    second = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="继续睡眠建议",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
            job_id="job-2",
        )
    )
    assert first is not None and second is not None
    seeded = [call.args[1][0] for call in repo.append_if_ready.call_args_list]
    assert [item.message_id for item in seeded] == [
        "team-peer:thr_parent~child:job-1:human",
        "team-peer:thr_parent~child:job-2:human",
    ]
    assert all("请改成早睡建议" in item.message_json for item in seeded)
    assert all("上一轮的问题" not in item.message_json for item in seeded)


@pytest.mark.asyncio
async def test_prepare_team_dispatch_tracks_job_and_forces_sync(
    processor_env: dict,
) -> None:
    from harness_agent.teams.util import PeerCall

    from octop.infra.agents.teams import TeamJobTracker

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    jobs = TeamJobTracker()
    processor._agent_manager._team_jobs = jobs
    processor._agent_manager.teams.member_ids.return_value = ["child", "other"]
    prepared = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="hello",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
        )
    )
    assert jobs.is_busy("host", "child")
    assert prepared is not None
    extra = getattr(prepared, "configurable", None)
    if extra is not None:
        assert extra == {
            "peer_invoke_mode": "sync",
            "team_peers": ["other"],
        }


@pytest.mark.asyncio
async def test_prepare_team_dispatch_includes_room_history(
    processor_env: dict,
) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage, HumanMessage

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_manager.teams.member_ids.return_value = ["child", "other"]
    harness = MagicMock()
    harness.aget_history = AsyncMock(
        return_value=[
            HumanMessage(content="what is the market?"),
            AIMessage(content="I will ask Researcher"),
        ]
    )
    processor._agent_manager.get_agent.return_value = harness
    prepared = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="survey market",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
        )
    )
    assert prepared is not None
    assert getattr(prepared, "message", None) in {None, "what is the market?"}
    pair = processor.teams.peek_peer_prompt("child", "thr_parent~child")
    assert pair is not None
    question, dispatch = pair
    assert question == "what is the market?"
    assert "what is the market?" in dispatch
    assert "I will ask Researcher" in dispatch
    assert "survey market" in dispatch
    taken = processor.teams.take_peer_prompt("child", "thr_parent~child")
    assert taken == pair
    assert harness.aget_history.await_count >= 1


@pytest.mark.asyncio
async def test_prepare_team_dispatch_uses_projected_member_speech(
    processor_env: dict,
) -> None:
    import json

    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage, HumanMessage

    processor = processor_env["processor"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_repo.create(agent_id="other", user_id=1, name="Analyst")
    processor._agent_manager.teams.member_ids.return_value = ["child", "other"]
    harness = MagicMock()
    harness.aget_history = AsyncMock(
        return_value=[
            HumanMessage(content="what is the market?"),
            AIMessage(content="I will ask Researcher"),
        ]
    )
    processor._agent_manager.get_agent.return_value = harness
    repo = MagicMock()
    repo.projection_status.return_value = "ready"
    repo.page.return_value = (
        [
            SimpleNamespace(
                role="human",
                message_json=json.dumps({"content": "what is the market?"}),
            ),
            SimpleNamespace(
                role="ai",
                message_json=json.dumps(
                    {
                        "content": "TAM is 12B",
                        "additional_kwargs": {"speaker_agent_id": "child"},
                    }
                ),
            ),
        ],
        False,
    )
    processor.replace_thread_message_repo(repo)

    prepared = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="host",
            to_agent_id="other",
            user_id=1,
            message="size the TAM",
            source_thread_id="thr_parent",
            source_session_key=str(processor_env["parent_sk"]),
        )
    )
    assert prepared is not None
    pair = processor.teams.peek_peer_prompt("other", "thr_parent~other")
    assert pair is not None
    question, dispatch = pair
    assert question == "what is the market?"
    assert "TAM is 12B" in dispatch
    assert "Researcher" in dispatch
    assert "size the TAM" in dispatch
    assert harness.aget_history.await_count >= 1


def test_stamp_team_host_runtime_forces_async(processor_env: dict) -> None:
    processor = processor_env["processor"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    processor._agent_manager.strip_team_host_runtime_tools = MagicMock()
    request: dict[str, object] = {
        "configurable": {"session_key": "sk", "mcp_use_default": True},
        "mcp_servers": ["tencent-news__1"],
        "mcp_use_default": True,
    }
    processor.teams.stamp_host_runtime(request, "host")
    assert request["configurable"] == {
        "session_key": "sk",
        "peer_invoke_mode": "async",
    }
    assert "mcp_servers" not in request
    assert "mcp_use_default" not in request
    processor._agent_manager.strip_team_host_runtime_tools.assert_called_once_with("host")
    expert_req: dict[str, object] = {}
    processor.teams.stamp_host_runtime(expert_req, "parent")
    assert "configurable" not in expert_req


@pytest.mark.asyncio
async def test_stream_team_peer_relays_tokens_to_room(processor_env: dict) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-room", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-room")

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        yield {"type": "token", "content": "hello "}
        yield {"type": "token", "content": "doc"}
        yield {"type": "usage", "usage": {}}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(return_value=[AIMessage(content="hello doc")])
    processor._agent_manager.get_agent.return_value = harness

    result = await processor.teams.stream_peer_to_room(
        ChatRequest(messages="task", thread_id="thr_parent~child", agent_id="child"),
        room_thread_id="thr_parent",
        speaker_id="child",
    )
    assert result["team_live_streamed"] is True
    tokens = [frame.get("content") for frame in frames if frame.get("type") == "token"]
    assert tokens == ["hello ", "doc"]
    assert all(
        frame.get("agent_id") == "child" and frame.get("agent") == "child"
        for frame in frames
        if frame.get("type") in {"token", "done"}
    )
    assert frames[-1].get("type") == "done"
    harness.aget_history.assert_awaited()


@pytest.mark.asyncio
async def test_stream_team_peer_relays_tokens_to_member_and_room(
    processor_env: dict,
) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    room_frames: list[dict[str, object]] = []
    member_frames: list[dict[str, object]] = []

    async def capture_room(frame: dict[str, object]) -> None:
        room_frames.append(frame)

    async def capture_member(frame: dict[str, object]) -> None:
        member_frames.append(frame)

    gateway.ws_hub.register("conn-room", capture_room)
    gateway.ws_hub.subscribe("thr_parent", "conn-room")
    gateway.ws_hub.register("conn-member", capture_member)
    gateway.ws_hub.subscribe("thr_parent~child", "conn-member")

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        yield {"type": "token", "content": "please rest"}
        yield {"type": "done"}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(return_value=[AIMessage(content="please rest")])
    processor._agent_manager.get_agent.return_value = harness

    await processor.teams.stream_peer_to_room(
        ChatRequest(messages="task", thread_id="thr_parent~child", agent_id="child"),
        room_thread_id="thr_parent",
        speaker_id="child",
    )
    room_tokens = [frame for frame in room_frames if frame.get("type") == "token"]
    member_tokens = [frame for frame in member_frames if frame.get("type") == "token"]
    assert room_tokens[0].get("content") == "please rest"
    assert room_tokens[0].get("agent_id") == "child"
    assert member_tokens[0].get("content") == "please rest"
    assert member_tokens[0].get("thread_id") == "thr_parent~child"


@pytest.mark.asyncio
async def test_stream_team_peer_unwatched_is_not_live_streamed(
    processor_env: dict,
) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        yield {"type": "token", "content": "late"}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(return_value=[AIMessage(content="late")])
    processor._agent_manager.get_agent.return_value = harness

    result = await processor.teams.stream_peer_to_room(
        ChatRequest(messages="task", thread_id="thr_parent~child", agent_id="child"),
        room_thread_id="thr_parent",
        speaker_id="child",
    )
    assert result["team_live_streamed"] is False


@pytest.mark.asyncio
async def test_stream_team_peer_relays_reasoning_and_tools(processor_env: dict) -> None:
    from harness_agent.request import ChatRequest
    from langchain_core.messages import AIMessage, HumanMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-room", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-room")

    async def fake_stream(_agent_id: str, _request: dict[str, object]) -> object:
        yield {"type": "reasoning", "content": "check labs"}
        yield {"type": "tool_call_chunk", "id": "c1", "name": "read_file", "args": "{}"}
        yield {"type": "tool_result", "messages": [{"tool_call_id": "c1", "content": "ok"}]}
        yield {"type": "token", "content": "rest"}

    processor._agent_manager.stream = fake_stream
    harness = MagicMock()
    harness.aget_history = AsyncMock(
        return_value=[
            HumanMessage(content="please advise"),
            AIMessage(content="rest"),
        ]
    )
    processor._agent_manager.get_agent.return_value = harness

    result = await processor.teams.stream_peer_to_room(
        ChatRequest(messages="task", thread_id="thr_parent~child", agent_id="child"),
        room_thread_id="thr_parent",
        speaker_id="child",
    )
    kinds = [frame.get("type") for frame in frames]
    assert "reasoning" in kinds
    assert "tool_call_chunk" in kinds
    assert "tool_result" in kinds
    assert all(
        frame.get("agent_id") == "child" and frame.get("agent") == "child"
        for frame in frames
        if frame.get("type") in {"reasoning", "tool_call_chunk", "tool_result", "token", "done"}
    )
    messages = result["messages"]
    assert messages
    assert all(getattr(msg, "type", None) != "human" for msg in messages)
    last = messages[-1]
    assert getattr(last, "additional_kwargs", {}).get("speaker_agent_id") == "child"
    assert getattr(last, "additional_kwargs", {}).get("reasoning_content") == "check labs"


@pytest.mark.asyncio
async def test_fan_in_persists_member_turn_without_dispatch_prompt(
    processor_env: dict,
) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage, HumanMessage

    processor = processor_env["processor"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    processor.replace_thread_message_repo(repo)

    await processor.teams.fan_in_peer_turn(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="ask",
            source_thread_id="thr_parent",
            source_session_key=None,
        ),
        [
            HumanMessage(content="internal dispatch"),
            AIMessage(content="", tool_calls=[{"name": "read_file", "id": "c1", "args": {}}]),
            AIMessage(content="please rest"),
        ],
        live_streamed=True,
    )
    repo.append_if_ready.assert_called_once()
    thread_id, inputs = repo.append_if_ready.call_args.args
    assert thread_id == "thr_parent"
    assert len(inputs) == 1
    assert inputs[0].role in {"ai", "assistant"}


@pytest.mark.asyncio
async def test_fan_in_skips_snapshot_after_live_stream(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-room", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-room")

    await processor.teams.fan_in_peer_turn(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="ask",
            source_thread_id="thr_parent",
            source_session_key=None,
        ),
        [AIMessage(content="already streamed")],
        live_streamed=True,
    )
    tokens = [frame for frame in frames if frame.get("type") == "token"]
    assert tokens == []


@pytest.mark.asyncio
async def test_fan_in_pushes_snapshot_when_not_live(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    processor._agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    frames: list[dict[str, object]] = []

    async def capture(frame: dict[str, object]) -> None:
        frames.append(frame)

    gateway.ws_hub.register("conn-gap", capture)
    gateway.ws_hub.subscribe("thr_parent", "conn-gap")

    await processor.teams.fan_in_peer_turn(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="ask",
            source_thread_id="thr_parent",
            source_session_key=None,
        ),
        [AIMessage(content="late join")],
        live_streamed=False,
    )
    tokens = [frame for frame in frames if frame.get("type") == "token"]
    assert tokens[0].get("content") == "late join"
    assert tokens[0].get("agent_id") == "child"
    assert tokens[0].get("agent") == "child"
    assert tokens[0].get("team_snapshot") is True


@pytest.mark.asyncio
async def test_fan_in_async_non_team_writes_caller_room(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    processor.replace_thread_message_repo(repo)

    await processor.teams.fan_in_peer_turn(
        PeerCall(
            from_agent_id="parent",
            to_agent_id="child",
            user_id=1,
            message="ask",
            source_thread_id="thr_parent",
            source_session_key=None,
            job_id="job-async",
        ),
        [AIMessage(content="from the wall")],
        live_streamed=True,
    )
    repo.append_if_ready.assert_called_once()
    thread_id, inputs = repo.append_if_ready.call_args.args
    assert thread_id == "thr_parent"
    assert any("from the wall" in item.message_json for item in inputs)


@pytest.mark.asyncio
async def test_fan_in_sync_non_team_skips_caller_room(processor_env: dict) -> None:
    from harness_agent.teams.util import PeerCall
    from langchain_core.messages import AIMessage

    processor = processor_env["processor"]
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    processor.replace_thread_message_repo(repo)

    await processor.teams.fan_in_peer_turn(
        PeerCall(
            from_agent_id="parent",
            to_agent_id="child",
            user_id=1,
            message="ask",
            source_thread_id="thr_parent",
            source_session_key=None,
        ),
        [AIMessage(content="tool result only")],
        live_streamed=True,
    )
    repo.append_if_ready.assert_not_called()


@pytest.mark.asyncio
async def test_on_reply_failed_releases_job(processor_env: dict) -> None:
    from octop.infra.agents.teams import TeamJobTracker

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    jobs = TeamJobTracker()
    processor._agent_manager._team_jobs = jobs
    jobs.begin("host", "child", job_id="job-9")
    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-9",
            status="failed",
            source_agent_id="host",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            error_text="offline",
            metadata={"session_key": parent_sk},
        )
    )
    assert not jobs.is_busy("host", "child")


def test_resolve_harness_model_auto_expert_omits_model() -> None:
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model=None)
    processor._agent_manager.get_config.return_value = {}
    processor._agent_manager.providers.resolve_explicit_default_model.return_value = None

    assert (
        processor._resolve_harness_model(
            "a1",
            "t1",
            None,
            needs_multimodal=True,
        )
        is None
    )


def test_resolve_harness_model_uses_agent_default_and_upgrades_vision() -> None:
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model="p/text-only")
    processor._agent_manager.get_config.return_value = {}
    processor._agent_manager.providers.resolve_explicit_default_model.return_value = "p/text-only"
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.return_value = "p/vision"

    resolved = processor._resolve_harness_model(
        "a1",
        "t1",
        None,
        needs_multimodal=True,
    )
    assert resolved == "p/vision"
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.assert_called_once_with(
        "p/text-only",
        needs_multimodal=True,
    )


def test_resolve_harness_model_dashboard_override_wins() -> None:
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model="p/default")
    processor._agent_manager.providers.is_model_ref_usable.return_value = True
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.return_value = "p/picked"

    resolved = processor._resolve_harness_model(
        "a1",
        "t1",
        {"model": "p/picked"},
        needs_multimodal=False,
    )
    assert resolved == "p/picked"
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.assert_called_once_with(
        "p/picked",
        needs_multimodal=False,
    )


def test_resolve_harness_model_drops_unusable_dashboard_override() -> None:
    """Stale composer/expert refs must not bypass catalog usability checks."""
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model="p/deleted")
    processor._agent_manager.get_config.return_value = {}
    processor._agent_manager.providers.is_model_ref_usable.return_value = False
    processor._agent_manager.providers.resolve_explicit_default_model.return_value = None

    assert (
        processor._resolve_harness_model(
            "a1",
            "t1",
            {"model": "p/deleted"},
            needs_multimodal=False,
        )
        is None
    )
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.assert_not_called()


def test_composer_model_precedes_sticky_and_legacy_slash_model() -> None:
    assert (
        GlobalProcessor._model_ref_from_meta(
            "p/slash",
            {"model": "p/composer"},
            "p/sticky",
        )
        == "p/composer"
    )
    assert GlobalProcessor._model_ref_from_meta("p/slash", None, "p/sticky") == "p/sticky"


def test_stamp_stream_speaker_sets_agent_alias() -> None:
    from octop.infra.agents.teams.team_manager import (
        stamp_stream_speaker as _stamp_stream_speaker,
    )
    from octop.infra.agents.teams.team_manager import (
        stamp_team_host_chunk as _maybe_stamp_team_host,
    )

    token = _stamp_stream_speaker({"type": "token", "content": "hi"}, "host")
    assert token == {
        "type": "token",
        "content": "hi",
        "agent_id": "host",
        "agent": "host",
    }
    host_done = _stamp_stream_speaker({"type": "done"}, "host")
    assert host_done == {"type": "done"}
    member_done = _stamp_stream_speaker({"type": "done"}, "child", include_done=True)
    assert member_done["agent"] == "child"
    assert member_done["agent_id"] == "child"
    usage = _stamp_stream_speaker({"type": "usage", "usage": {}}, "host")
    assert "agent_id" not in usage
    solo = _maybe_stamp_team_host({"type": "token", "content": "hi"}, "host", False)
    assert solo == {"type": "token", "content": "hi"}
    team = _maybe_stamp_team_host({"type": "token", "content": "hi"}, "host", True)
    assert team["agent"] == "host"
    team_done = _maybe_stamp_team_host({"type": "done"}, "host", True)
    assert team_done["agent_id"] == "host"
    assert team_done["agent"] == "host"
    member = _maybe_stamp_team_host(
        {"type": "token", "content": "hi", "agent_id": "doctor", "agent": "doctor"},
        "host",
        True,
    )
    assert member["agent_id"] == "doctor"
    assert member["agent"] == "doctor"
