"""tests/unit/test_dashboard_ws.py"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
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
        metadata={"ws_connection_id": "conn-1", "session_key": "sk"},
    )
    await channel.handle_inbound(msg)

    assert {"type": "token", "content": "hello"} in frames
    assert frames[-1] == {"type": "done"}


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
