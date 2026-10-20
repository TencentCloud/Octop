"""Unit tests for the octop-harness backend processor.

Tests event mapping from HarnessAgent.stream() events to MessageEvent types
without requiring network or a real agent instance.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Ensure examples/backends is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from octop_gateway import InboundMessage, MessageEvent
from octop_gateway.models import ChannelSubject, MessageEventType, TextContent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(text: str = "hello") -> InboundMessage:
    """Create a simple InboundMessage for testing."""
    return InboundMessage(
        channel_id="test",
        content=[TextContent(text=text)],
        channel_subject=ChannelSubject(subject_id="user1"),
    )


async def _fake_stream(events: list[dict[str, Any]]):
    """Async generator that yields pre-defined event dicts."""
    for e in events:
        yield e


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessorEventMapping:
    """Test that stream events are correctly mapped to MessageEvents."""

    @pytest.mark.asyncio
    async def test_token_events_produce_deltas(self) -> None:
        """token events → MessageEvent.delta()"""
        events = [
            {"type": "token", "content": "Hello", "node": "agent"},
            {"type": "token", "content": " world", "node": "agent"},
        ]

        results = await self._run_processor(events)

        deltas = [e for e in results if e.type == MessageEventType.DELTA]
        assert len(deltas) == 2
        assert deltas[0].content[0].text == "Hello"
        assert deltas[1].content[0].text == " world"

    @pytest.mark.asyncio
    async def test_reasoning_events_produce_thinking_deltas(self) -> None:
        """reasoning events → MessageEvent.thinking_delta()"""
        events = [
            {"type": "reasoning", "content": "Let me think...", "node": "agent"},
            {"type": "reasoning", "content": " about this.", "node": "agent"},
        ]

        results = await self._run_processor(events)

        thinking = [e for e in results if e.type == MessageEventType.THINKING_DELTA]
        assert len(thinking) == 2
        assert thinking[0].content[0].text == "Let me think..."

    @pytest.mark.asyncio
    async def test_node_change_triggers_flush(self) -> None:
        """Tokens from different nodes should be split by a flush."""
        events = [
            {"type": "token", "content": "From agent", "node": "agent"},
            {"type": "token", "content": "From summarizer", "node": "summarizer"},
        ]

        results = await self._run_processor(events)

        types = [e.type for e in results]
        # Expect: TYPING, DELTA("From agent"), FLUSH, DELTA("From summarizer"), COMPLETED
        assert MessageEventType.FLUSH in types
        flush_idx = types.index(MessageEventType.FLUSH)
        # First delta before flush, second after
        deltas = [i for i, t in enumerate(types) if t == MessageEventType.DELTA]
        assert deltas[0] < flush_idx < deltas[1]

    @pytest.mark.asyncio
    async def test_tool_call_chunk_emits_tool_start(self) -> None:
        """First tool_call_chunk with a name → tool_start.

        Realistic LangChain shape: ``id`` and ``name`` are only set on the
        first chunk; subsequent chunks merge by ``index``. See
        ``langchain_core.messages.tool.ToolCallChunk`` docs.
        """
        events = [
            {"type": "tool_call_chunk", "id": "tc1", "name": "web_search", "args": "", "index": 0, "node": "agent"},
            {"type": "tool_call_chunk", "id": None, "name": None, "args": '{"q":', "index": 0, "node": "agent"},
            {"type": "tool_call_chunk", "id": None, "name": None, "args": '"hello"}', "index": 0, "node": "agent"},
        ]

        results = await self._run_processor(events)

        tool_starts = [e for e in results if e.type == MessageEventType.TOOL_START]
        assert len(tool_starts) == 1
        assert tool_starts[0].metadata["tool_name"] == "web_search"

    @pytest.mark.asyncio
    async def test_tool_call_chunk_name_fragments_concatenate(self) -> None:
        """Some providers split the tool ``name`` itself across chunks
        (e.g. ``send_file_t`` then ``o_user``). ``tool_start`` must surface
        the fully-assembled name, not the first fragment.

        Realistic shape: ``id`` only present on the first chunk.
        """
        events = [
            {"type": "tool_call_chunk", "id": "tc1", "name": "send_file_t", "args": "", "index": 0, "node": "agent"},
            {"type": "tool_call_chunk", "id": None, "name": "o_user", "args": "", "index": 0, "node": "agent"},
            {
                "type": "tool_call_chunk",
                "id": None,
                "name": None,
                "args": '{"file_path":"/x"}',
                "index": 0,
                "node": "agent",
            },
            {"type": "tool_result", "node": "tools", "messages": [{"role": "tool", "content": "ok"}]},
        ]

        results = await self._run_processor(events)

        tool_starts = [e for e in results if e.type == MessageEventType.TOOL_START]
        tool_ends = [e for e in results if e.type == MessageEventType.TOOL_END]
        assert len(tool_starts) == 1
        assert tool_starts[0].metadata["tool_name"] == "send_file_to_user"
        assert len(tool_ends) == 1
        assert tool_ends[0].metadata["tool_name"] == "send_file_to_user"

    @pytest.mark.asyncio
    async def test_tool_call_chunk_keys_state_by_index_not_id(self) -> None:
        """Regression test: real LangChain streams set ``id`` only on the
        first ``ToolCallChunk``; subsequent chunks have ``id=None`` and are
        merged by ``index``. The processor must therefore key its per-call
        state on ``index``, otherwise the buffered tool name is split across
        two keys ("call_xxx" vs "_idx_0") and ``tool_result`` falls back to
        the literal string "tool".
        """
        events = [
            {
                "type": "tool_call_chunk",
                "id": "call_abc123",
                "name": "send_file_to_user",
                "args": "",
                "index": 0,
                "node": "agent",
            },
            # Subsequent chunks: id and name are None; only args grows.
            {"type": "tool_call_chunk", "id": None, "name": None, "args": '{"file_pa', "index": 0, "node": "agent"},
            {"type": "tool_call_chunk", "id": None, "name": None, "args": 'th":"/x"}', "index": 0, "node": "agent"},
            {"type": "tool_result", "node": "tools", "messages": [{"role": "tool", "content": "ok"}]},
        ]

        results = await self._run_processor(events)

        tool_starts = [e for e in results if e.type == MessageEventType.TOOL_START]
        tool_ends = [e for e in results if e.type == MessageEventType.TOOL_END]
        assert len(tool_starts) == 1
        assert tool_starts[0].metadata["tool_name"] == "send_file_to_user"
        assert len(tool_ends) == 1
        assert tool_ends[0].metadata["tool_name"] == "send_file_to_user"

    @pytest.mark.asyncio
    async def test_tool_call_with_no_args_still_emits_start_and_end(self) -> None:
        """A tool that takes no arguments never emits an ``args`` chunk;
        ``tool_start`` must therefore be synthesised when ``tool_result``
        arrives so the user still sees the call.
        """
        events = [
            {"type": "tool_call_chunk", "id": "tc1", "name": "current_time", "args": "", "index": 0, "node": "agent"},
            # No subsequent chunk with args.
            {"type": "tool_result", "node": "tools", "messages": [{"role": "tool", "content": "12:00"}]},
        ]

        results = await self._run_processor(events)

        tool_starts = [e for e in results if e.type == MessageEventType.TOOL_START]
        tool_ends = [e for e in results if e.type == MessageEventType.TOOL_END]
        assert len(tool_starts) == 1
        assert tool_starts[0].metadata["tool_name"] == "current_time"
        assert len(tool_ends) == 1
        assert tool_ends[0].metadata["tool_name"] == "current_time"

    @pytest.mark.asyncio
    async def test_tool_result_emits_tool_end(self) -> None:
        """tool_result → tool_end for the active tool."""
        events = [
            {"type": "tool_call_chunk", "id": "tc1", "name": "calculator", "args": "", "index": 0, "node": "agent"},
            {"type": "tool_result", "node": "tools", "messages": [{"role": "tool", "content": "42"}]},
        ]

        results = await self._run_processor(events)

        tool_ends = [e for e in results if e.type == MessageEventType.TOOL_END]
        assert len(tool_ends) == 1
        assert tool_ends[0].metadata["tool_name"] == "calculator"

    @pytest.mark.asyncio
    async def test_state_update_triggers_flush_on_node_change(self) -> None:
        """state_update from a different node flushes accumulated content."""
        events = [
            {"type": "token", "content": "thinking...", "node": "agent"},
            {"type": "state_update", "node": "tools", "data": {"messages": []}},
            {"type": "token", "content": "result", "node": "tools"},
        ]

        results = await self._run_processor(events)

        types = [e.type for e in results]
        # Should have at least one flush from node change
        assert types.count(MessageEventType.FLUSH) >= 1

    @pytest.mark.asyncio
    async def test_state_snapshot_and_custom_ignored(self) -> None:
        """state_snapshot and custom events produce no MessageEvents."""
        events = [
            {"type": "state_snapshot", "data": {"messages": []}},
            {"type": "custom", "data": {"progress": 50}},
            {"type": "token", "content": "hi", "node": "agent"},
        ]

        results = await self._run_processor(events)

        # Only TYPING + DELTA("hi") + COMPLETED
        types = [e.type for e in results]
        assert MessageEventType.TYPING in types
        assert MessageEventType.DELTA in types
        assert MessageEventType.COMPLETED in types
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_content_token_ignored(self) -> None:
        """token with empty content string should not produce a delta."""
        events = [
            {"type": "token", "content": "", "node": "agent"},
            {"type": "token", "content": "real content", "node": "agent"},
        ]

        results = await self._run_processor(events)

        deltas = [e for e in results if e.type == MessageEventType.DELTA]
        assert len(deltas) == 1
        assert deltas[0].content[0].text == "real content"

    @pytest.mark.asyncio
    async def test_stream_error_produces_error_event(self) -> None:
        """Exception during streaming → error event + completed."""

        async def _exploding_stream(*args, **kwargs):
            yield {"type": "token", "content": "start", "node": "agent"}
            raise RuntimeError("LLM connection lost")

        results = await self._run_processor_with_generator(_exploding_stream)

        types = [e.type for e in results]
        assert MessageEventType.ERROR in types
        assert MessageEventType.COMPLETED in types
        error_event = next(e for e in results if e.type == MessageEventType.ERROR)
        assert "LLM connection lost" in error_event.error

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_sequential(self) -> None:
        """Multiple sequential tool calls each get start/end."""
        events = [
            {"type": "tool_call_chunk", "id": "tc1", "name": "search", "args": "", "index": 0, "node": "agent"},
            {"type": "tool_result", "node": "tools", "messages": []},
            {"type": "tool_call_chunk", "id": "tc2", "name": "calculator", "args": "", "index": 0, "node": "agent"},
            {"type": "tool_result", "node": "tools", "messages": []},
        ]

        results = await self._run_processor(events)

        tool_starts = [e for e in results if e.type == MessageEventType.TOOL_START]
        tool_ends = [e for e in results if e.type == MessageEventType.TOOL_END]
        assert len(tool_starts) == 2
        assert len(tool_ends) == 2
        assert tool_starts[0].metadata["tool_name"] == "search"
        assert tool_starts[1].metadata["tool_name"] == "calculator"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_processor(self, events: list[dict[str, Any]]) -> list[MessageEvent]:
        """Run the processor with mocked agent.stream() returning given events."""
        return await self._run_processor_with_generator(lambda *a, **kw: _fake_stream(events))

    async def _run_processor_with_generator(self, generator_fn) -> list[MessageEvent]:
        """Run the processor with a custom stream generator function."""
        with patch.dict(
            "sys.modules",
            {
                "octop_harness": _FakeModule(),
                "octop_harness.config": _FakeConfigModule(),
            },
        ):
            from backends.octop_harness import AgentBackend

            backend = AgentBackend.__new__(AgentBackend)
            backend._agent = AsyncMock()
            backend._agent.stream = generator_fn

            msg = _make_msg("test input")
            results: list[MessageEvent] = []
            async for event in backend.processor(msg):
                results.append(event)

        return results


# ---------------------------------------------------------------------------
# Fake modules to avoid importing real octop_harness
# ---------------------------------------------------------------------------


class _FakeModule:
    """Fake octop_harness module."""

    class HarnessAgent:
        def __init__(self, *args, **kwargs):
            pass


class _FakeConfigModule:
    """Fake octop_harness.config module."""

    class HarnessAgentConfig:
        def __init__(self, *args, **kwargs):
            pass

    class ModelConfig:
        def __init__(self, *args, **kwargs):
            pass

    class ProviderConfig:
        def __init__(self, *args, **kwargs):
            pass


# ---------------------------------------------------------------------------
# Tool-result media block extraction
# ---------------------------------------------------------------------------


def _make_backend_only_agent(backend) -> Any:
    """Construct an AgentBackend without invoking its real ``__init__``.

    Tests only need the media-block helpers; bypassing ``__init__`` avoids
    pulling in the full HarnessAgent stack.
    """
    with patch.dict(
        "sys.modules",
        {"octop_harness": _FakeModule(), "octop_harness.config": _FakeConfigModule()},
    ):
        from backends.octop_harness import AgentBackend

        backend_instance = AgentBackend.__new__(AgentBackend)
        backend_instance._media_backend = backend
        backend_instance._agent = AsyncMock()
        return backend_instance


class TestBlockToContentPart:
    """Verify _block_to_content_part resolves all expected source forms."""

    @pytest.mark.asyncio
    async def test_file_url_inside_backend_root_reuses_key(self, tmp_path: Path) -> None:
        """A file:// URL pointing inside the backend root reuses the
        existing relative key — no copy is performed.
        """
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        # File already lives under tmp_path/preview/cat.png
        target = tmp_path / "preview" / "cat.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PNG-INSIDE")

        agent = _make_backend_only_agent(backend)
        block = {
            "type": "image",
            "source": {
                "type": "url",
                "url": target.as_uri(),
                "media_type": "image/png",
            },
            "filename": "cat.png",
        }

        part = await agent._block_to_content_part(block)
        from octop_gateway.models import ImageContent

        assert isinstance(part, ImageContent)
        assert part.local_path == "preview/cat.png"
        assert part.url == ""
        # No new file should have appeared anywhere else
        assert sorted(p.name for p in tmp_path.rglob("*.png")) == ["cat.png"]

    @pytest.mark.asyncio
    async def test_file_url_outside_backend_root_is_copied(self, tmp_path: Path) -> None:
        """File outside backend root is copied in under agent_outbound/<ts>_<name>."""
        from octop_gateway.media import FileSystemMediaBackend

        backend_root = tmp_path / "backend"
        backend_root.mkdir()
        backend = FileSystemMediaBackend(backend_root)

        outside = tmp_path / "elsewhere" / "report.pdf"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b"PDFBYTES")

        agent = _make_backend_only_agent(backend)
        block = {
            "type": "file",
            "source": {
                "type": "url",
                "url": outside.as_uri(),
                "media_type": "application/pdf",
            },
            "filename": "report.pdf",
        }

        part = await agent._block_to_content_part(block)
        from octop_gateway.models import FileContent

        assert isinstance(part, FileContent)
        assert part.local_path is not None
        assert part.local_path.startswith("agent_outbound/")
        assert part.local_path.endswith("_report.pdf")
        assert (backend_root / part.local_path).read_bytes() == b"PDFBYTES"
        assert part.filename == "report.pdf"

    @pytest.mark.asyncio
    async def test_base64_source_binds_to_data_field(self, tmp_path: Path) -> None:
        """A base64 source binds the payload directly to ContentPart.data;
        url and local_path remain empty (no extra encode/decode trip).
        """
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        agent = _make_backend_only_agent(backend)
        import base64 as _b64

        payload = _b64.b64encode(b"AUDIOBYTES").decode()
        block = {
            "type": "audio",
            "source": {"type": "base64", "data": payload, "media_type": "audio/mpeg"},
            "filename": "tone.mp3",
        }

        part = await agent._block_to_content_part(block)
        from octop_gateway.models import AudioContent

        assert isinstance(part, AudioContent)
        assert part.data == payload
        assert part.url == ""
        assert part.local_path is None
        assert part.mime_type == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_http_url_passes_through(self, tmp_path: Path) -> None:
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        agent = _make_backend_only_agent(backend)
        block = {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://cdn.example.com/x.png",
                "media_type": "image/png",
            },
            "filename": "x.png",
        }

        part = await agent._block_to_content_part(block)
        from octop_gateway.models import ImageContent

        assert isinstance(part, ImageContent)
        assert part.url == "https://cdn.example.com/x.png"
        assert part.local_path is None

    @pytest.mark.asyncio
    async def test_missing_file_url_raises(self, tmp_path: Path) -> None:
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        agent = _make_backend_only_agent(backend)
        block = {
            "type": "image",
            "source": {
                "type": "url",
                "url": (tmp_path / "missing.png").as_uri(),
                "media_type": "image/png",
            },
        }
        with pytest.raises(FileNotFoundError):
            await agent._block_to_content_part(block)


class TestBuildContentReadsBackend:
    """Inbound images with local_path must be resolved via MediaBackend.read."""

    @pytest.mark.asyncio
    async def test_local_path_resolved_through_backend_read(self, tmp_path: Path) -> None:
        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"PNG-BYTES", "inbound/photo.png")

        agent = _make_backend_only_agent(backend)
        msg = InboundMessage(
            channel_id="test",
            content=[
                TextContent(text="look"),
                ImageContent(local_path="inbound/photo.png", mime_type="image/png"),
            ],
            channel_subject=ChannelSubject(subject_id="user1"),
        )

        blocks = await agent._build_content(msg)
        assert isinstance(blocks, list)
        img = next(b for b in blocks if b.get("type") == "image")
        import base64 as _b64

        assert _b64.b64decode(img["base64"]) == b"PNG-BYTES"
        assert img["mime_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_missing_backend_key_falls_back_to_url(self, tmp_path: Path) -> None:
        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        agent = _make_backend_only_agent(FileSystemMediaBackend(tmp_path))
        msg = InboundMessage(
            channel_id="test",
            content=[
                ImageContent(
                    local_path="missing/key.png",
                    url="https://cdn.example.com/fallback.png",
                    mime_type="image/png",
                ),
            ],
            channel_subject=ChannelSubject(subject_id="user1"),
        )

        blocks = await agent._build_content(msg)
        assert isinstance(blocks, list)
        img = next(b for b in blocks if b.get("type") == "image")
        assert img["url"] == "https://cdn.example.com/fallback.png"
        assert "base64" not in img


class TestToolResultEmitsMediaEvents:
    """Integration: tool_result events with attachment blocks produce
    MESSAGE events carrying ContentParts.
    """

    @pytest.mark.asyncio
    async def test_image_block_in_tool_result_yields_message_event(self, tmp_path: Path) -> None:
        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        backend_root = tmp_path / "media"
        backend_root.mkdir()
        # Place an image already inside the backend so the helper reuses its key.
        img_path = backend_root / "send_file_to_user" / "out.png"
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_bytes(b"PNGDATA")

        events = [
            {
                "type": "tool_call_chunk",
                "id": "tc1",
                "name": "send_file_to_user",
                "args": "",
                "index": 0,
                "node": "agent",
            },
            {
                "type": "tool_result",
                "node": "tools",
                "messages": [
                    {
                        "role": "tool",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": img_path.as_uri(),
                                    "media_type": "image/png",
                                },
                                "filename": "out.png",
                            }
                        ],
                    }
                ],
            },
        ]

        results: list[MessageEvent] = []
        with patch.dict(
            "sys.modules",
            {"octop_harness": _FakeModule(), "octop_harness.config": _FakeConfigModule()},
        ):
            from backends.octop_harness import AgentBackend

            backend_instance = AgentBackend.__new__(AgentBackend)
            backend_instance._media_backend = FileSystemMediaBackend(backend_root)
            backend_instance._agent = AsyncMock()
            backend_instance._agent.stream = lambda *a, **kw: _fake_stream(events)

            async for event in backend_instance.processor(_make_msg("show me the file")):
                results.append(event)

        media_events = [e for e in results if e.type == MessageEventType.MESSAGE]
        assert len(media_events) == 1
        part = media_events[0].content[0]
        assert isinstance(part, ImageContent)
        assert part.local_path == "send_file_to_user/out.png"
        # Tool lifecycle still observed
        assert any(e.type == MessageEventType.TOOL_START for e in results)
        assert any(e.type == MessageEventType.TOOL_END for e in results)

    @pytest.mark.asyncio
    async def test_missing_file_in_tool_result_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        from octop_gateway.media import FileSystemMediaBackend

        events = [
            {
                "type": "tool_call_chunk",
                "id": "tc1",
                "name": "send_file_to_user",
                "args": "",
                "index": 0,
                "node": "agent",
            },
            {
                "type": "tool_result",
                "node": "tools",
                "messages": [
                    {
                        "role": "tool",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": (tmp_path / "ghost.png").as_uri(),
                                    "media_type": "image/png",
                                },
                            }
                        ],
                    }
                ],
            },
            {"type": "token", "content": "done", "node": "agent"},
        ]

        results: list[MessageEvent] = []
        with patch.dict(
            "sys.modules",
            {"octop_harness": _FakeModule(), "octop_harness.config": _FakeConfigModule()},
        ):
            from backends.octop_harness import AgentBackend

            backend_instance = AgentBackend.__new__(AgentBackend)
            backend_instance._media_backend = FileSystemMediaBackend(tmp_path)
            backend_instance._agent = AsyncMock()
            backend_instance._agent.stream = lambda *a, **kw: _fake_stream(events)

            async for event in backend_instance.processor(_make_msg("anything")):
                results.append(event)

        # No MESSAGE event for the missing file, but the stream survived and
        # the subsequent token still produced a delta.
        assert not any(e.type == MessageEventType.MESSAGE for e in results)
        assert any(e.type == MessageEventType.DELTA for e in results)
        assert any(e.type == MessageEventType.COMPLETED for e in results)

    @pytest.mark.asyncio
    async def test_json_string_tool_content_unwraps_to_media_event(self, tmp_path: Path) -> None:
        """Regression: LangChain's ``@tool`` decorator JSON-stringifies dict
        returns into ``ToolMessage.content``. AgentBackend must re-parse
        the string and surface the embedded media block; otherwise the
        send_file_to_user flow silently no-ops (the agent reports the tool
        ran but nothing is delivered to the user).
        """
        import json as _json

        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        backend_root = tmp_path / "media"
        backend_root.mkdir()
        # Place a real file so file:// resolution succeeds.
        img_path = tmp_path / "test_image.jpg"
        img_path.write_bytes(b"FAKEJPEG")

        block = {
            "type": "image",
            "source": {
                "type": "url",
                "url": img_path.as_uri(),
                "media_type": "image/jpeg",
            },
            "filename": "test_image.jpg",
        }

        events = [
            {
                "type": "tool_call_chunk",
                "id": "tc1",
                "name": "send_file_to_user",
                "args": "",
                "index": 0,
                "node": "agent",
            },
            {
                "type": "tool_result",
                "node": "tools",
                # This shape mirrors a ToolMessage produced by LangChain
                # when @tool sees a dict return: content is a JSON string.
                "messages": [
                    {
                        "role": "tool",
                        "content": _json.dumps(block),
                        "name": "send_file_to_user",
                        "tool_call_id": "tc1",
                    }
                ],
            },
        ]

        results: list[MessageEvent] = []
        with patch.dict(
            "sys.modules",
            {"octop_harness": _FakeModule(), "octop_harness.config": _FakeConfigModule()},
        ):
            from backends.octop_harness import AgentBackend

            backend_instance = AgentBackend.__new__(AgentBackend)
            backend_instance._media_backend = FileSystemMediaBackend(backend_root)
            backend_instance._agent = AsyncMock()
            backend_instance._agent.stream = lambda *a, **kw: _fake_stream(events)

            async for event in backend_instance.processor(_make_msg("send the image")):
                results.append(event)

        media_events = [e for e in results if e.type == MessageEventType.MESSAGE]
        assert len(media_events) == 1, "expected one media MESSAGE despite stringified content"
        part = media_events[0].content[0]
        assert isinstance(part, ImageContent)
        # File lives outside backend root → was copied under agent_outbound.
        assert part.local_path is not None
        assert part.local_path.endswith("_test_image.jpg")
        assert part.mime_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_invalid_json_tool_content_is_skipped(self, tmp_path: Path) -> None:
        """Non-JSON ``ToolMessage.content`` (e.g. an error string) must
        not produce a MESSAGE event and must not crash the stream.
        """
        from octop_gateway.media import FileSystemMediaBackend

        events = [
            {
                "type": "tool_result",
                "node": "tools",
                "messages": [{"role": "tool", "content": "not a JSON payload"}],
            },
            {"type": "token", "content": "ok", "node": "agent"},
        ]

        results: list[MessageEvent] = []
        with patch.dict(
            "sys.modules",
            {"octop_harness": _FakeModule(), "octop_harness.config": _FakeConfigModule()},
        ):
            from backends.octop_harness import AgentBackend

            backend_instance = AgentBackend.__new__(AgentBackend)
            backend_instance._media_backend = FileSystemMediaBackend(tmp_path)
            backend_instance._agent = AsyncMock()
            backend_instance._agent.stream = lambda *a, **kw: _fake_stream(events)

            async for event in backend_instance.processor(_make_msg("anything")):
                results.append(event)

        assert not any(e.type == MessageEventType.MESSAGE for e in results)
        assert any(e.type == MessageEventType.DELTA for e in results)
        assert any(e.type == MessageEventType.COMPLETED for e in results)
