"""Tests for the CLI gateway channel."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.cli import CLI_CHANNEL_ID, CLI_CONNECTION_META, CliChannel, CliHub


@pytest.mark.asyncio
async def test_cli_hub_push() -> None:
    hub = CliHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    hub.register("c1", capture)
    await hub.push("c1", {"type": "token", "content": "hi"})
    hub.unregister("c1")
    await hub.push("c1", {"type": "token", "content": "miss"})
    assert frames == [{"type": "token", "content": "hi"}]


@pytest.mark.asyncio
async def test_cli_channel_streams_chunks() -> None:
    hub = CliHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    class _FakeProcessor:
        async def iter_turn_chunks(self, msg: InboundMessage) -> AsyncIterator[dict[str, Any]]:
            assert msg.tenant_id == "agent-1"
            assert msg.channel_type == "cli"
            yield {"type": "token", "content": "hello"}
            yield {"type": "done"}

    channel = CliChannel(_FakeProcessor(), hub=hub)  # type: ignore[arg-type]
    hub.register("conn-1", capture)

    msg = InboundMessage(
        channel_id=CLI_CHANNEL_ID,
        channel_type="cli",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="7"),
        content=[TextContent(text="hi")],
        metadata={CLI_CONNECTION_META: "conn-1", "session_key": "sk"},
    )
    await channel.handle_inbound(msg)

    assert {"type": "token", "content": "hello"} in frames
    assert frames[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_cli_channel_send_text_finalizes_with_done() -> None:
    hub = CliHub()
    frames: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        frames.append(frame)

    hub.register("conn-1", capture)
    channel = CliChannel(object(), hub=hub)  # type: ignore[arg-type]
    subject = ChannelSubject(
        subject_id="7",
        chat_type="dm",
        metadata={CLI_CONNECTION_META: "conn-1"},
    )
    await channel._send_text(subject, "hello")
    assert frames == [
        {"type": "token", "content": "hello"},
        {"type": "done"},
    ]
