"""Tests for octop_gateway.utils."""

from __future__ import annotations

import asyncio

import pytest

from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)
from octop_gateway.utils import (
    Debouncer,
    close_event_stream,
    extract_media,
    extract_text,
    has_media,
    has_text,
    merge_messages,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "hang", "raise"])
async def test_close_event_stream_runs_and_bounds_finalizers(mode, monkeypatch, caplog):
    closed = asyncio.Event()

    async def events():
        try:
            yield "error"
        finally:
            try:
                if mode == "hang":
                    await asyncio.Event().wait()
                if mode == "raise":
                    raise RuntimeError("simulated cleanup failure")
            finally:
                closed.set()

    monkeypatch.setattr("octop_gateway.utils.STREAM_CLOSE_TIMEOUT", 0.01)
    stream = events()
    assert await anext(stream) == "error"
    await asyncio.wait_for(close_event_stream(stream), timeout=0.5)
    assert closed.is_set()
    if mode != "ok":
        assert "cleanup timed out" in caplog.text if mode == "hang" else "cleanup failed" in caplog.text


class TestContentHelpers:
    """Test content inspection utilities."""

    def test_has_text_true(self) -> None:
        parts = [TextContent(text="hello"), ImageContent(url="http://x.png")]
        assert has_text(parts) is True

    def test_has_text_false_empty(self) -> None:
        parts = [TextContent(text=""), TextContent(text="   ")]
        assert has_text(parts) is False

    def test_has_text_false_no_text(self) -> None:
        parts = [ImageContent(url="http://x.png")]
        assert has_text(parts) is False

    def test_has_media_true(self) -> None:
        parts = [TextContent(text="hi"), ImageContent(url="http://x.png")]
        assert has_media(parts) is True

    def test_has_media_false(self) -> None:
        parts = [TextContent(text="hi")]
        assert has_media(parts) is False

    def test_has_media_all_types(self) -> None:
        assert has_media([VideoContent(url="http://v.mp4")])
        assert has_media([AudioContent(url="http://a.mp3")])
        assert has_media([FileContent(url="http://f.pdf", filename="f.pdf")])

    def test_extract_text(self) -> None:
        parts = [
            TextContent(text="line 1"),
            ImageContent(url="http://x.png"),
            TextContent(text="line 2"),
        ]
        assert extract_text(parts) == "line 1\nline 2"

    def test_extract_text_empty(self) -> None:
        parts = [ImageContent(url="http://x.png")]
        assert extract_text(parts) == ""

    def test_extract_media(self) -> None:
        parts = [
            TextContent(text="hi"),
            ImageContent(url="http://img.png"),
            FileContent(url="http://f.pdf", filename="f.pdf"),
        ]
        media = extract_media(parts)
        assert len(media) == 2
        assert all(not isinstance(m, TextContent) for m in media)


class TestMergeMessages:
    """Test message merging."""

    def test_merge_single(self) -> None:
        msg = InboundMessage(
            channel_id="test",
            content=[TextContent(text="hi")],
            channel_subject=ChannelSubject(subject_id="u1"),
        )
        result = merge_messages([msg])
        assert result is msg

    def test_merge_multiple(self) -> None:
        msg1 = InboundMessage(
            channel_id="test",
            channel_type="weixin",
            tenant_id="agent-1",
            channel_session_id="session-1",
            content=[TextContent(text="hello")],
            channel_subject=ChannelSubject(subject_id="u1"),
            metadata={"first": True},
            timestamp=100.0,
        )
        msg2 = InboundMessage(
            channel_id="test",
            channel_type="weixin",
            tenant_id="agent-1",
            channel_session_id="session-1",
            content=[ImageContent(url="http://img.png")],
            channel_subject=ChannelSubject(subject_id="u1"),
            metadata={"second": True},
            timestamp=101.0,
        )
        result = merge_messages([msg1, msg2])
        assert len(result.content) == 2
        assert result.timestamp == 100.0
        assert result.channel_subject is not None
        assert result.channel_subject.subject_id == "u1"
        assert result.channel_type == "weixin"
        assert result.tenant_id == "agent-1"
        assert result.channel_session_id == "session-1"
        assert result.metadata == {"first": True, "second": True}

    def test_merge_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            merge_messages([])


class TestDebouncer:
    """Test async debouncer."""

    @pytest.mark.asyncio
    async def test_basic_debounce(self) -> None:
        results: list[tuple[str, list[str]]] = []

        async def callback(key: str, items: list[str]) -> None:
            results.append((key, items))

        debouncer = Debouncer(delay=0.05, callback=callback)
        await debouncer.add("k1", "a")
        await debouncer.add("k1", "b")
        await debouncer.add("k1", "c")

        # Wait for debounce to flush
        await asyncio.sleep(0.1)

        assert len(results) == 1
        assert results[0] == ("k1", ["a", "b", "c"])

    @pytest.mark.asyncio
    async def test_different_keys(self) -> None:
        results: list[tuple[str, list[str]]] = []

        async def callback(key: str, items: list[str]) -> None:
            results.append((key, items))

        debouncer = Debouncer(delay=0.05, callback=callback)
        await debouncer.add("k1", "a")
        await debouncer.add("k2", "b")

        await asyncio.sleep(0.1)

        assert len(results) == 2
        keys = [r[0] for r in results]
        assert "k1" in keys
        assert "k2" in keys

    @pytest.mark.asyncio
    async def test_flush_immediate(self) -> None:
        results: list[tuple[str, list[str]]] = []

        async def callback(key: str, items: list[str]) -> None:
            results.append((key, items))

        debouncer = Debouncer(delay=1.0, callback=callback)
        await debouncer.add("k1", "item")
        await debouncer.flush("k1")

        assert len(results) == 1
        assert results[0] == ("k1", ["item"])

    @pytest.mark.asyncio
    async def test_flush_all(self) -> None:
        results: list[tuple[str, list[str]]] = []

        async def callback(key: str, items: list[str]) -> None:
            results.append((key, items))

        debouncer = Debouncer(delay=1.0, callback=callback)
        await debouncer.add("k1", "a")
        await debouncer.add("k2", "b")
        await debouncer.flush_all()

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_pending_keys(self) -> None:
        async def callback(key: str, items: list[str]) -> None:
            pass

        debouncer = Debouncer(delay=1.0, callback=callback)
        await debouncer.add("k1", "a")
        await debouncer.add("k2", "b")

        assert set(debouncer.pending_keys) == {"k1", "k2"}
