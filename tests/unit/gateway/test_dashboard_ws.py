"""tests/unit/test_dashboard_ws.py"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from harness_gateway.models import ChannelSubject, ImageContent, InboundMessage, TextContent

from octop.infra.gateway.media.tool_media import enrich_media_block_preview
from octop.infra.gateway.ws import WS_CHANNEL_ID, WebSocketChannel, WebSocketHub


@pytest.mark.asyncio
async def test_ws_hub_push() -> None:
    hub = WebSocketHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    hub.register("c1", capture)
    await hub.push("c1", {"type": "token", "content": "hi"})
    hub.unregister("c1")
    await hub.push("c1", {"type": "token", "content": "miss"})
    assert frames == [{"type": "token", "content": "hi"}]


@pytest.mark.asyncio
async def test_ws_hub_subscribe_push_to_thread_replaces_subscriber() -> None:
    hub = WebSocketHub()
    a_frames: list[dict[str, Any]] = []
    b_frames: list[dict[str, Any]] = []

    async def capture_a(frame: dict[str, Any]) -> None:
        a_frames.append(frame)

    async def capture_b(frame: dict[str, Any]) -> None:
        b_frames.append(frame)

    hub.register("a", capture_a)
    hub.register("b", capture_b)
    hub.subscribe("thread-1", "a")
    await hub.push_to_thread("thread-1", {"type": "token", "content": "one"})
    hub.subscribe("thread-1", "b")
    await hub.push_to_thread("thread-1", {"type": "token", "content": "two"})
    hub.unregister("b")
    await hub.push_to_thread("thread-1", {"type": "token", "content": "three"})

    assert a_frames == [{"type": "token", "content": "one"}]
    assert b_frames == [{"type": "token", "content": "two"}]


def test_ws_hub_turn_active_flags() -> None:
    hub = WebSocketHub()
    assert hub.is_turn_active("t1") is False
    hub.mark_turn_active("t1")
    assert hub.is_turn_active("t1") is True
    hub.mark_turn_idle("t1")
    assert hub.is_turn_active("t1") is False


@pytest.mark.asyncio
async def test_ws_channel_streams_chunks() -> None:
    hub = WebSocketHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    class _FakeProcessor:
        async def iter_turn_chunks(self, msg: InboundMessage) -> AsyncIterator[dict[str, Any]]:
            assert msg.tenant_id == "agent-1"
            yield {"type": "token", "content": "hello"}
            yield {"type": "done"}

    channel = WebSocketChannel(_FakeProcessor(), hub=hub)  # type: ignore[arg-type]
    hub.register("conn-1", capture)

    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="7"),
        content=[TextContent(text="hi")],
        metadata={
            "ws_connection_id": "conn-1",
            "session_key": "sk",
            "thread_id": "thread-1",
        },
    )
    await channel.handle_inbound(msg)

    assert {"type": "token", "content": "hello"} in frames
    assert frames[-1] == {"type": "done"}
    assert hub.is_turn_active("thread-1") is False


@pytest.mark.asyncio
async def test_ws_channel_rebinds_mid_turn_to_new_subscriber() -> None:
    import asyncio

    hub = WebSocketHub()
    a_frames: list[dict[str, Any]] = []
    b_frames: list[dict[str, Any]] = []
    gate = asyncio.Event()

    async def capture_a(frame: dict[str, Any]) -> None:
        a_frames.append(frame)

    async def capture_b(frame: dict[str, Any]) -> None:
        b_frames.append(frame)

    class _FakeProcessor:
        async def iter_turn_chunks(self, msg: InboundMessage) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "token", "content": "first"}
            await gate.wait()
            yield {"type": "token", "content": "second"}
            yield {"type": "done"}

    channel = WebSocketChannel(_FakeProcessor(), hub=hub)  # type: ignore[arg-type]
    hub.register("a", capture_a)
    hub.register("b", capture_b)

    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="7"),
        content=[TextContent(text="hi")],
        metadata={
            "ws_connection_id": "a",
            "session_key": "sk",
            "thread_id": "thread-1",
        },
    )
    task = asyncio.create_task(channel.handle_inbound(msg))

    for _ in range(50):
        if a_frames:
            break
        await asyncio.sleep(0.01)
    assert a_frames == [{"type": "token", "content": "first"}]
    assert hub.is_turn_active("thread-1") is True

    hub.unsubscribe_connection("a")
    hub.subscribe("thread-1", "b")
    gate.set()
    await task

    assert b_frames == [
        {"type": "token", "content": "second"},
        {"type": "done"},
    ]
    assert hub.is_turn_active("thread-1") is False


@pytest.mark.asyncio
async def test_ws_channel_send_media_base64() -> None:
    hub = WebSocketHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    class _FakeProcessor:
        async def iter_turn_chunks(self, msg: InboundMessage) -> AsyncIterator[dict[str, Any]]:
            yield {"type": "done"}

    channel = WebSocketChannel(_FakeProcessor(), hub=hub)  # type: ignore[arg-type]
    hub.register("conn-2", capture)

    raw = b"\x89PNG\r\n\x1a\n"
    media = ImageContent(
        data=base64.b64encode(raw).decode("ascii"),
        mime_type="image/png",
        alt_text="chart",
    )
    subject = ChannelSubject(
        subject_id="u1",
        metadata={"ws_connection_id": "conn-2"},
    )
    await channel._send_media(subject, media)

    assert len(frames) == 1
    frame = frames[0]
    assert frame["type"] == "attachment"
    assert frame["kind"] == "image"
    assert frame["mime_type"] == "image/png"
    assert frame["alt_text"] == "chart"
    assert base64.b64decode(frame["data"]) == raw


def test_enrich_media_block_preview_file_url() -> None:
    block = {
        "type": "image",
        "source": {
            "type": "url",
            "url": "file:///tmp/workspace/outbound/chart.png",
            "media_type": "image/png",
        },
    }
    enriched = enrich_media_block_preview(block, agent_id="agent-x")
    assert enriched["preview_url"].startswith("/api/agents/agent-x/media/preview?")


@pytest.mark.asyncio
async def test_global_processor_iter_turn_chunks_registers_hitl() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator
    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    async def _stream(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [{"name": "execute", "args": {"command": "ls"}}],
            },
        }

    agent_manager = MagicMock()
    agent_manager.stream = _stream
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thread-hitl")

    hitl = HitlChannelCoordinator()
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
        hitl=hitl,
    )

    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="run ls")],
        metadata={"session_key": "sk", "thread_id": "thread-hitl"},
    )

    chunks = [c async for c in processor.iter_turn_chunks(msg)]
    assert any(c.get("type") == "hitl_required" for c in chunks)
    pending = hitl.store.resolve_pending_for_thread(
        "thread-hitl",
        agent_id="agent-1",
        user_id=1,
    )
    assert pending is not None
    assert pending.action_requests[0]["name"] == "execute"


@pytest.mark.asyncio
async def test_global_processor_persists_and_enriches_user_question(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import SqlitePool
    from octop.infra.db.repos.user_questions import PendingUserQuestionRepo
    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.questions import UserQuestionCoordinator
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    async def _stream(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "kind": "ask_user_question",
                "questions": [{"id": "name", "question": "What name?", "options": []}],
            },
        }

    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    questions = UserQuestionCoordinator(PendingUserQuestionRepo(pool))
    agent_manager = MagicMock()
    agent_manager.stream = _stream
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thread-question")
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        questions=questions,
    )
    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="start")],
        metadata={"session_key": "sk", "thread_id": "thread-question"},
    )

    chunks = [chunk async for chunk in processor.iter_turn_chunks(msg)]
    request = next(chunk["request"] for chunk in chunks if chunk.get("type") == "hitl_required")
    assert request["pending_id"]
    pending = questions.pending_payload(thread_id="thread-question", agent_id="agent-1", user_id=1)
    assert pending is not None
    assert pending["pending_id"] == request["pending_id"]


@pytest.mark.asyncio
async def test_global_processor_iter_turn_chunks_slash() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thread-1")

    dispatcher = SlashDispatcher()
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=dispatcher,
        usage_repo=None,
        gateway=None,
    )

    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="/help")],
        metadata={"session_key": "sk"},
    )

    chunks = [c async for c in processor.iter_turn_chunks(msg)]
    assert chunks[0]["type"] == "token"
    assert chunks[-1]["type"] == "done"
