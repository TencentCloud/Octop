"""Integration test: full media download + persist pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from octop_gateway.channel import BaseChannel, MessageProcessor
from octop_gateway.manager import ChannelManager
from octop_gateway.media import FileSystemMediaBackend
from octop_gateway.models import (
    ChannelSubject,
    ContentPart,
    ImageContent,
    InboundMessage,
    MessageEvent,
    TextContent,
)


class _TestChannel(BaseChannel):
    """Minimal channel for integration testing."""

    channel_id = "test-int"

    def __init__(self, processor: MessageProcessor) -> None:
        super().__init__(processor)
        self.sent: list[str] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        self.sent.append(text)

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        pass

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        pass

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        return raw_payload


class TestMediaPipelineIntegration:
    """End-to-end: inbound message -> _persist_media -> backend.save -> local_path set."""

    @pytest.mark.asyncio
    async def test_image_downloaded_and_persisted(self, tmp_path: Path) -> None:
        """Image in inbound message is downloaded and saved to filesystem backend."""
        backend = FileSystemMediaBackend(tmp_path)

        async def check_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            img = msg.content[1]
            assert img.local_path is not None  # set to MediaBackend key
            yield MessageEvent.text(f"saved:{img.local_path}")
            yield MessageEvent.completed()

        channel = _TestChannel(check_processor)
        mgr = ChannelManager({"test-int": channel}, media_backend=backend)

        with patch.object(_TestChannel, "fetch_remote_media", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (b"fake-png", "image/png")

            await mgr.start()

            msg = InboundMessage(
                channel_id="test-int",
                content=[
                    TextContent(text="check this"),
                    ImageContent(url="https://cdn.example.com/photo.png"),
                ],
                channel_subject=ChannelSubject(subject_id="user1"),
            )

            await channel.handle_inbound(msg)

            saved_files = list(tmp_path.rglob("*.png"))
            assert len(saved_files) == 1
            assert saved_files[0].read_bytes() == b"fake-png"
            mock_fetch.assert_awaited_once_with("https://cdn.example.com/photo.png")

            await mgr.stop()

    @pytest.mark.asyncio
    async def test_no_backend_skips_persistence(self) -> None:
        """Without a backend, media is not downloaded/persisted."""

        async def check_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            img = msg.content[0]
            assert img.local_path is None
            yield MessageEvent.text("ok")
            yield MessageEvent.completed()

        channel = _TestChannel(check_processor)
        mgr = ChannelManager({"test-int": channel})  # No backend

        await mgr.start()

        msg = InboundMessage(
            channel_id="test-int",
            content=[ImageContent(url="https://cdn.example.com/photo.png")],
            channel_subject=ChannelSubject(subject_id="user1"),
        )

        await channel.handle_inbound(msg)
        await mgr.stop()

    @pytest.mark.asyncio
    async def test_load_media_bytes_reads_from_backend(self, tmp_path: Path) -> None:
        """Outbound load_media_bytes reads from MediaBackend by local_path."""
        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"image-bytes", "img/cached.png")

        async def noop(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.completed()

        channel = _TestChannel(noop)
        channel.set_media_backend(backend)

        part = ImageContent(local_path="img/cached.png", mime_type="image/png")
        data, mime = await channel.load_media_bytes(part)
        assert data == b"image-bytes"
        assert mime == "image/png"

    @pytest.mark.asyncio
    async def test_load_media_bytes_caches_url_to_backend(self, tmp_path: Path) -> None:
        """When given only a URL, load_media_bytes fetches and caches into backend."""
        backend = FileSystemMediaBackend(tmp_path)

        async def noop(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.completed()

        channel = _TestChannel(noop)
        channel.set_media_backend(backend)

        with patch.object(_TestChannel, "fetch_remote_media", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = (b"fetched", "image/png")
            part = ImageContent(url="https://cdn.example.com/x.png")
            data, mime = await channel.load_media_bytes(part)
            assert data == b"fetched"
            assert mime == "image/png"
            assert part.local_path is not None
            # Round-trip: backend now contains the bytes
            assert await backend.read(part.local_path) == b"fetched"
