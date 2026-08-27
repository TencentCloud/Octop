"""tests/unit/test_dashboard_ws.py"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import Any

import pytest
from harness_gateway.models import ChannelSubject, ImageContent, InboundMessage, TextContent

from octop.infra.gateway.media.tool_media import enrich_media_block_preview
from octop.infra.gateway.ws import WS_CHANNEL_ID, WebSocketChannel, WebSocketHub


def _token(content: str, thread_id: str) -> dict[str, Any]:
    return {"type": "token", "content": content, "thread_id": thread_id}


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
async def test_ws_hub_push_to_user_delivers_only_to_that_user() -> None:
    hub = WebSocketHub()
    alice: list[dict[str, Any]] = []
    bob: list[dict[str, Any]] = []
    chat: list[dict[str, Any]] = []

    async def capture_alice(frame: dict[str, Any]) -> None:
        alice.append(frame)

    async def capture_bob(frame: dict[str, Any]) -> None:
        bob.append(frame)

    async def capture_chat(frame: dict[str, Any]) -> None:
        chat.append(frame)

    hub.register("a1", capture_alice, user_id=1)
    hub.register("b1", capture_bob, user_id=2)
    hub.register("chat", capture_chat)

    await hub.push_to_user(1, {"type": "dashboard_push", "text": "hi"})

    assert alice == [{"type": "dashboard_push", "text": "hi"}]
    assert bob == []
    assert chat == []


@pytest.mark.asyncio
async def test_ws_hub_push_to_user_fans_out_to_all_connections() -> None:
    hub = WebSocketHub()
    frames_a: list[dict[str, Any]] = []
    frames_b: list[dict[str, Any]] = []

    async def capture_a(frame: dict[str, Any]) -> None:
        frames_a.append(frame)

    async def capture_b(frame: dict[str, Any]) -> None:
        frames_b.append(frame)

    hub.register("c1", capture_a, user_id=7)
    hub.register("c2", capture_b, user_id=7)

    await hub.push_to_user(7, {"type": "dashboard_push", "text": "ping"})

    assert frames_a == [{"type": "dashboard_push", "text": "ping"}]
    assert frames_b == [{"type": "dashboard_push", "text": "ping"}]


@pytest.mark.asyncio
async def test_ws_hub_unregister_stops_user_delivery() -> None:
    hub = WebSocketHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    hub.register("c1", capture, user_id=3)
    hub.unregister("c1")
    await hub.push_to_user(3, {"type": "dashboard_push", "text": "gone"})

    assert frames == []


@pytest.mark.asyncio
async def test_ws_hub_push_to_user_with_no_subscribers_is_noop() -> None:
    hub = WebSocketHub()
    await hub.push_to_user(99, {"type": "dashboard_push", "text": "nobody"})


@pytest.mark.asyncio
async def test_ws_hub_subscribe_push_to_thread_fans_out() -> None:
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

    assert a_frames == [
        _token("one", "thread-1"),
        _token("two", "thread-1"),
        _token("three", "thread-1"),
    ]
    assert b_frames == [_token("two", "thread-1")]


@pytest.mark.asyncio
async def test_ws_hub_subscribe_switches_thread_without_kicking_others() -> None:
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
    hub.subscribe("thread-1", "b")
    hub.subscribe("thread-2", "a")
    await hub.push_to_thread("thread-1", {"type": "token", "content": "t1"})
    await hub.push_to_thread("thread-2", {"type": "token", "content": "t2"})

    assert a_frames == [_token("t2", "thread-2")]
    assert b_frames == [_token("t1", "thread-1")]


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

    assert {"type": "token", "content": "hello", "thread_id": "thread-1"} in frames
    assert frames[-1] == {"type": "done", "thread_id": "thread-1"}
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
    assert a_frames == [_token("first", "thread-1")]
    assert hub.is_turn_active("thread-1") is True

    hub.unsubscribe_connection("a")
    hub.subscribe("thread-1", "b")
    gate.set()
    await task

    assert b_frames == [
        _token("second", "thread-1"),
        {"type": "done", "thread_id": "thread-1"},
    ]
    assert hub.is_turn_active("thread-1") is False


@pytest.mark.asyncio
async def test_ws_channel_fans_out_mid_turn_to_all_subscribers() -> None:
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
    assert a_frames == [_token("first", "thread-1")]

    hub.subscribe("thread-1", "b")
    gate.set()
    await task

    assert a_frames == [
        _token("first", "thread-1"),
        _token("second", "thread-1"),
        {"type": "done", "thread_id": "thread-1"},
    ]
    assert b_frames == [
        _token("second", "thread-1"),
        {"type": "done", "thread_id": "thread-1"},
    ]
    assert hub.is_turn_active("thread-1") is False


def test_ws_channel_debounce_key_is_per_thread() -> None:
    channel = WebSocketChannel(object(), hub=WebSocketHub())  # type: ignore[arg-type]
    msg_a = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="7"),
        content=[TextContent(text="hi")],
        metadata={"session_key": "shared-sk", "thread_id": "thread-a"},
    )
    msg_b = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="7"),
        content=[TextContent(text="yo")],
        metadata={"session_key": "shared-sk", "thread_id": "thread-b"},
    )
    assert channel.get_debounce_key(msg_a) == "thread:thread-a"
    assert channel.get_debounce_key(msg_b) == "thread:thread-b"
    assert channel.get_debounce_key(msg_a) != channel.get_debounce_key(msg_b)
    assert channel.should_batch_inbound(msg_a) is False


@pytest.mark.asyncio
async def test_ws_hub_three_subscribers_same_thread() -> None:
    hub = WebSocketHub()
    buckets: dict[str, list[dict[str, Any]]] = {"a": [], "b": [], "c": []}

    def _capture(name: str):
        async def capture(frame: dict[str, Any]) -> None:
            buckets[name].append(frame)

        return capture

    for name in buckets:
        hub.register(name, _capture(name))
        hub.subscribe("thread-1", name)
    await hub.push_to_thread("thread-1", {"type": "token", "content": "hi"})
    expected = [_token("hi", "thread-1")]
    assert buckets["a"] == expected
    assert buckets["b"] == expected
    assert buckets["c"] == expected


@pytest.mark.asyncio
async def test_ws_hub_push_does_not_block_other_subscribers() -> None:
    import asyncio

    hub = WebSocketHub()
    order: list[str] = []
    released = asyncio.Event()

    async def slow(frame: dict[str, Any]) -> None:
        order.append("slow-start")
        await released.wait()
        order.append("slow-end")

    async def fast(frame: dict[str, Any]) -> None:
        order.append("fast")

    hub.register("slow", slow)
    hub.register("fast", fast)
    hub.subscribe("thread-1", "slow")
    hub.subscribe("thread-1", "fast")
    task = asyncio.create_task(hub.push_to_thread("thread-1", {"type": "token", "content": "x"}))
    for _ in range(50):
        if "fast" in order:
            break
        await asyncio.sleep(0.01)
    assert "fast" in order
    assert "slow-end" not in order
    released.set()
    await task
    assert "fast" in order
    assert "slow-end" in order
    assert order.index("fast") < order.index("slow-end")


@pytest.mark.asyncio
async def test_ws_channel_concurrent_threads_do_not_cross() -> None:
    import asyncio

    hub = WebSocketHub()
    a_frames: list[dict[str, Any]] = []
    b_frames: list[dict[str, Any]] = []
    gate = asyncio.Event()
    started = asyncio.Event()
    started_count = 0

    async def capture_a(frame: dict[str, Any]) -> None:
        a_frames.append(frame)

    async def capture_b(frame: dict[str, Any]) -> None:
        b_frames.append(frame)

    class _FakeProcessor:
        async def iter_turn_chunks(self, msg: InboundMessage) -> AsyncIterator[dict[str, Any]]:
            nonlocal started_count
            tid = str((msg.metadata or {}).get("thread_id"))
            yield {"type": "token", "content": f"{tid}-1"}
            started_count += 1
            if started_count >= 2:
                started.set()
            await gate.wait()
            yield {"type": "token", "content": f"{tid}-2"}
            yield {"type": "done"}

    channel = WebSocketChannel(_FakeProcessor(), hub=hub)  # type: ignore[arg-type]
    hub.register("a", capture_a)
    hub.register("b", capture_b)

    def _msg(conn: str, thread_id: str) -> InboundMessage:
        return InboundMessage(
            channel_id=WS_CHANNEL_ID,
            channel_type="dashboard",
            tenant_id="agent-1",
            channel_subject=ChannelSubject(subject_id="7"),
            content=[TextContent(text="hi")],
            metadata={
                "ws_connection_id": conn,
                "session_key": "shared-sk",
                "thread_id": thread_id,
            },
        )

    t1 = asyncio.create_task(channel.handle_inbound(_msg("a", "thread-a")))
    t2 = asyncio.create_task(channel.handle_inbound(_msg("b", "thread-b")))
    await asyncio.wait_for(started.wait(), timeout=2)
    gate.set()
    await asyncio.gather(t1, t2)

    a_tokens = [f.get("content") for f in a_frames if f.get("type") == "token"]
    b_tokens = [f.get("content") for f in b_frames if f.get("type") == "token"]
    assert a_tokens == ["thread-a-1", "thread-a-2"]
    assert b_tokens == ["thread-b-1", "thread-b-2"]
    assert all(f.get("thread_id") == "thread-a" for f in a_frames)
    assert all(f.get("thread_id") == "thread-b" for f in b_frames)


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
