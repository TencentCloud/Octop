"""Tests for octop_gateway.channel (BaseChannel contract)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.group_context import GroupContextConfig
from octop_gateway.models import (
    ChannelSubject,
    ContentPart,
    InboundMessage,
    MessageEvent,
    TextContent,
)

# --- Test implementation ---


class EchoChannel(BaseChannel):
    """Minimal channel implementation for testing."""

    channel_type = "echo"

    def __init__(self, processor: MessageProcessor, config: ChannelConfig | None = None) -> None:
        super().__init__(processor, config=config)
        self.sent_messages: list[tuple[str, str]] = []
        self.sent_content_list: list[tuple[str, list[ContentPart]]] = []
        self._started = False
        self._stopped = False

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._stopped = True
        await self._close_http()

    async def _send_text(self, user: ChannelSubject, text: str) -> None:
        self.sent_messages.append((user.subject_id, text))

    async def _send_content(self, user: ChannelSubject, parts: list[ContentPart]) -> None:
        self.sent_content_list.append((user.subject_id, parts))

    async def _send_media(self, user: ChannelSubject, media: ContentPart) -> None:
        self.sent_content_list.append((user.subject_id, [media]))

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload
        if isinstance(raw_payload, str):
            return InboundMessage(
                channel_id=self.channel_id,
                channel_type=self.channel_type,
                content=[TextContent(text=raw_payload)],
                channel_subject=ChannelSubject(subject_id="user1"),
            )
        raise ValueError(f"Unsupported payload: {type(raw_payload)}")


class PreprocessingEchoChannel(EchoChannel):
    """Test channel that enriches platform facts before shared policy runs."""

    async def _preprocess_inbound(self, message: InboundMessage) -> None:
        message.metadata["bot_mentioned"] = True


# --- Tests ---


async def make_echo_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    """Test processor that echoes text."""
    yield MessageEvent.text(f"Echo: {msg.text}")
    yield MessageEvent.completed()


class TestBaseChannel:
    """Test BaseChannel contract via EchoChannel."""

    def test_channel_id(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        assert ch.channel_type == "echo"
        assert len(ch.channel_id) == 32  # UUID hex

    @pytest.mark.asyncio
    async def test_lifecycle(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        await ch.start()
        assert ch._started
        await ch.stop()
        assert ch._stopped

    @pytest.mark.asyncio
    async def test_reply_text(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        user = ChannelSubject(subject_id="user1", first_seen=0, last_seen=0)
        await ch.reply_text(user, "hello")
        assert ch.sent_messages == [("user1", "hello")]

    @pytest.mark.asyncio
    async def test_parse_inbound_string(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        msg = ch.parse_inbound("hello world")
        assert msg.channel_id == ch.channel_id
        assert msg.channel_type == "echo"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "user1"
        assert msg.text == "hello world"

    @pytest.mark.asyncio
    async def test_parse_inbound_message_passthrough(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        original = InboundMessage(
            channel_id=ch.channel_id,
            channel_type="echo",
            content=[TextContent(text="test")],
            channel_subject=ChannelSubject(subject_id="u2"),
        )
        result = ch.parse_inbound(original)
        assert result is original

    @pytest.mark.asyncio
    async def test_handle_inbound(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        await ch.handle_inbound("hi there")
        # Should have sent the echo reply as text
        assert len(ch.sent_messages) == 1
        assert "Echo: hi there" in ch.sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_platform_preprocessing_runs_before_shared_group_policy(self) -> None:
        seen: list[InboundMessage] = []

        async def processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            seen.append(msg)
            yield MessageEvent.completed()

        config = ChannelConfig(
            group_context=GroupContextConfig(enabled=True, visibility="mention_only", activation="mention")
        )
        ch = PreprocessingEchoChannel(processor=processor, config=config)
        message = InboundMessage(
            channel_id=ch.channel_id,
            channel_type=ch.channel_type,
            channel_subject=ChannelSubject(subject_id="group-1", chat_type="group"),
            content=[TextContent(text="hello")],
            metadata={"conversation_id": "group-1", "sender_id": "alice"},
        )

        await ch.handle_inbound(message)

        assert len(seen) == 1
        assert seen[0].group_context is not None

    @pytest.mark.asyncio
    async def test_push_text(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        user = ChannelSubject(subject_id="dest", first_seen=0, last_seen=0)
        await ch.push_text(user, "notification")
        # push_text now routes through _send_text (one acquire, no content list).
        assert ch.sent_messages == [("dest", "notification")]

    def test_resolve_push_subject_merges_known_and_strips_ephemeral(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        ch._known_subjects["u1"] = ChannelSubject(
            subject_id="u1",
            metadata={"user_openid": "u1", "msg_id": "stale"},
        )
        sparse = ChannelSubject(subject_id="u1", metadata={"channel_type": "qq"})
        resolved = ch.resolve_push_subject(sparse)
        assert resolved.metadata["user_openid"] == "u1"
        assert "msg_id" not in resolved.metadata

    def test_enqueue_without_callback_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        ch.enqueue("test_payload")
        assert "No enqueue callback" in caplog.text

    def test_set_enqueue_callback(self) -> None:
        ch = EchoChannel(processor=make_echo_processor)
        received: list[Any] = []
        ch.set_enqueue_callback(lambda x: received.append(x))
        ch.enqueue("payload1")
        assert received == ["payload1"]

    @pytest.mark.asyncio
    async def test_clean_output_strips_think_tags(self) -> None:
        """<think>...</think> blocks should be stripped from output."""
        ch = EchoChannel(processor=make_echo_processor)
        result = ch._clean_output("<think>reasoning here</think>Hello!")
        assert "think" not in result
        assert "reasoning" not in result
        assert "Hello!" in result

    @pytest.mark.asyncio
    async def test_clean_output_unclosed_think(self) -> None:
        """Unclosed <think> should also be stripped."""
        ch = EchoChannel(processor=make_echo_processor)
        result = ch._clean_output("<think>partial reasoning without close")
        assert "think" not in result
        assert "partial" not in result

    @pytest.mark.asyncio
    async def test_handle_inbound_delta_accumulation(self) -> None:
        """DELTA events should be accumulated and sent as one message on COMPLETED."""

        async def streaming_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.delta("Hello ")
            yield MessageEvent.delta("World")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=streaming_processor)
        await ch.handle_inbound("test")
        # Should have accumulated "Hello World" into one send
        assert len(ch.sent_messages) == 1
        assert ch.sent_messages[0][1] == "Hello World"

    @pytest.mark.asyncio
    async def test_handle_inbound_media_download(self, tmp_path) -> None:
        """With media_backend set, images should be downloaded and local_path set."""
        from unittest.mock import AsyncMock

        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        async def simple_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            # Verify local_path is set on the image (it's a MediaBackend key)
            for part in msg.content:
                if isinstance(part, ImageContent) and part.local_path:
                    yield MessageEvent.text(f"saved:{part.local_path}")
                    yield MessageEvent.completed()
                    return
            yield MessageEvent.text("no image saved")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=simple_processor)
        ch._media_backend = FileSystemMediaBackend(tmp_path)

        # Mock fetch_remote_media to return fake data
        ch.fetch_remote_media = AsyncMock(return_value=(b"fake image data", "image/png"))

        # Create an InboundMessage with image
        msg = InboundMessage(
            channel_id=ch.channel_id,
            channel_type="echo",
            content=[ImageContent(url="https://example.com/img.png")],
            channel_subject=ChannelSubject(subject_id="user1"),
        )
        await ch.handle_inbound(msg)
        assert len(ch.sent_messages) == 1
        assert "saved:" in ch.sent_messages[0][1]

    # --- THINKING Event Tests ---

    @pytest.mark.asyncio
    async def test_thinking_event_with_show_thinking_true(self) -> None:
        """THINKING event should be formatted and sent when show_thinking=True."""
        from octop_gateway.constraints import ChannelConstraints

        async def thinking_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.thinking("Let me think about this...")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=thinking_processor)
        ch._constraints = ChannelConstraints(show_thinking=True)
        await ch.handle_inbound("question")

        # Should have sent a message containing the thinking block
        assert len(ch.sent_messages) == 1
        # Should be formatted with thinking template
        assert "thinking" in ch.sent_messages[0][1].lower() or "Let me think" in ch.sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_thinking_event_with_show_thinking_false(self) -> None:
        """THINKING event should be discarded when show_thinking=False."""
        from octop_gateway.constraints import ChannelConstraints

        async def thinking_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.thinking("Let me think about this...")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=thinking_processor)
        ch._constraints = ChannelConstraints(show_thinking=False)
        await ch.handle_inbound("question")

        # Should have sent no messages (thinking was discarded)
        assert len(ch.sent_messages) == 0

    # --- THINKING_DELTA Event Tests ---

    @pytest.mark.asyncio
    async def test_thinking_delta_accumulation_with_show_thinking_true(self) -> None:
        """THINKING_DELTA events should be accumulated when show_thinking=True."""
        from octop_gateway.constraints import ChannelConstraints

        async def thinking_delta_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.thinking_delta("Step 1: ")
            yield MessageEvent.thinking_delta("analyze the problem")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=thinking_delta_processor)
        ch._constraints = ChannelConstraints(show_thinking=True)
        await ch.handle_inbound("test")

        # Should have accumulated and sent the thinking
        assert len(ch.sent_messages) == 1
        assert "Step 1:" in ch.sent_messages[0][1]
        assert "analyze" in ch.sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_thinking_delta_discarded_with_show_thinking_false(self) -> None:
        """THINKING_DELTA events should be discarded when show_thinking=False."""
        from octop_gateway.constraints import ChannelConstraints

        async def thinking_delta_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.thinking_delta("Step 1: ")
            yield MessageEvent.thinking_delta("analyze the problem")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=thinking_delta_processor)
        ch._constraints = ChannelConstraints(show_thinking=False)
        await ch.handle_inbound("test")

        # Should have sent no messages (thinking_deltas were discarded)
        assert len(ch.sent_messages) == 0

    # --- FLUSH Event Tests ---

    @pytest.mark.asyncio
    async def test_flush_sends_accumulated_delta(self) -> None:
        """FLUSH event should immediately send accumulated DELTA content."""

        async def flush_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.delta("First ")
            yield MessageEvent.delta("part")
            yield MessageEvent.flush()
            yield MessageEvent.delta("Second ")
            yield MessageEvent.delta("part")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=flush_processor)
        await ch.handle_inbound("test")

        # Should have sent two separate messages
        assert len(ch.sent_messages) == 2
        assert ch.sent_messages[0][1] == "First part"
        assert ch.sent_messages[1][1] == "Second part"

    @pytest.mark.asyncio
    async def test_flush_sends_accumulated_thinking_and_delta(self) -> None:
        """FLUSH should send both accumulated thinking and delta in correct order."""
        from octop_gateway.constraints import ChannelConstraints

        async def flush_thinking_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.thinking_delta("Reasoning: ")
            yield MessageEvent.thinking_delta("step by step")
            yield MessageEvent.flush()
            yield MessageEvent.delta("Answer: ")
            yield MessageEvent.delta("complete")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=flush_thinking_processor)
        ch._constraints = ChannelConstraints(show_thinking=True)
        await ch.handle_inbound("test")

        # Should have sent two messages: thinking first, then answer
        assert len(ch.sent_messages) == 2
        assert "Reasoning" in ch.sent_messages[0][1]
        assert "Answer" in ch.sent_messages[1][1]

    @pytest.mark.asyncio
    async def test_flush_on_empty_buffer(self) -> None:
        """FLUSH on empty buffer should not produce extra messages."""

        async def flush_empty_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.flush()
            yield MessageEvent.delta("Content")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=flush_empty_processor)
        await ch.handle_inbound("test")

        # Should have one message with just the content
        assert len(ch.sent_messages) == 1
        assert ch.sent_messages[0][1] == "Content"

    # --- Combined Event Type Tests ---

    @pytest.mark.asyncio
    async def test_thinking_delta_and_delta_separate_buffers(self) -> None:
        """THINKING_DELTA and DELTA should be accumulated in separate buffers."""
        from octop_gateway.constraints import ChannelConstraints

        async def combined_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            # Interleave thinking and regular deltas
            yield MessageEvent.thinking_delta("Think1")
            yield MessageEvent.delta("Content1")
            yield MessageEvent.thinking_delta("Think2")
            yield MessageEvent.delta("Content2")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=combined_processor)
        ch._constraints = ChannelConstraints(show_thinking=True)
        await ch.handle_inbound("test")

        # Should have sent two messages: one with thinking, one with content
        assert len(ch.sent_messages) == 2
        # First message contains thinking (formatted with template)
        assert "Think1" in ch.sent_messages[0][1] and "Think2" in ch.sent_messages[0][1]
        # Second message contains content
        assert "Content1" in ch.sent_messages[1][1] and "Content2" in ch.sent_messages[1][1]

    @pytest.mark.asyncio
    async def test_message_event_respects_rate_limiting(self) -> None:
        """MESSAGE events should go through rate limiting."""
        from unittest.mock import patch

        from octop_gateway.constraints import ChannelConstraints

        async def message_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.text("Direct message")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=message_processor)
        # Create rate limiter that we can verify was called
        ch._constraints = ChannelConstraints(send_rate_limit=(1, 0.1))

        with patch.object(ch, "_rate_limited_send", wraps=ch._rate_limited_send) as mock_rate_limit:
            await ch.handle_inbound("test")
            # Verify _rate_limited_send was called for the MESSAGE event
            assert mock_rate_limit.called

    @pytest.mark.asyncio
    async def test_error_event_respects_rate_limiting(self) -> None:
        """ERROR events should go through rate limiting."""
        from unittest.mock import patch

        from octop_gateway.constraints import ChannelConstraints

        async def error_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.error_event("Something went wrong")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=error_processor)
        ch._constraints = ChannelConstraints(send_rate_limit=(1, 0.1))

        with patch.object(ch, "_rate_limited_send", wraps=ch._rate_limited_send) as mock_rate_limit:
            await ch.handle_inbound("test")
            # Verify _rate_limited_send was called for the ERROR event
            assert mock_rate_limit.called

    @pytest.mark.asyncio
    async def test_clean_output_called_for_raw_think_tags(self) -> None:
        """_clean_output should handle raw <think> tags in DELTA for legacy backends."""
        from unittest.mock import patch

        async def raw_think_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            # Simulate a backend that includes raw <think> tags in DELTA
            yield MessageEvent.delta("<think>internal reasoning</think>Final answer")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=raw_think_processor)

        with patch.object(ch, "_clean_output", wraps=ch._clean_output) as mock_clean:
            await ch.handle_inbound("test")
            # Verify _clean_output was called to strip the raw tags
            assert mock_clean.called

        # Verify the thinking tags were actually removed
        assert len(ch.sent_messages) == 1
        assert "think" not in ch.sent_messages[0][1]
        assert "internal reasoning" not in ch.sent_messages[0][1]
        assert "Final answer" in ch.sent_messages[0][1]

    @pytest.mark.asyncio
    async def test_wecom_forced_show_thinking_false(self) -> None:
        """WeComChannel should force show_thinking=False in default constraints."""
        from octop_gateway.channels.wecom import WeComChannel, WeComConfig

        async def dummy_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.completed()

        # Create WeComChannel with default constraints
        config = WeComConfig(bot_id="test_bot", secret="test_secret")
        ch = WeComChannel(processor=dummy_processor, config=config)
        assert ch._constraints.show_thinking is False

    @pytest.mark.asyncio
    async def test_weixin_forced_show_thinking_false(self) -> None:
        """WeixinChannel should force show_thinking=False in default constraints."""
        from octop_gateway.channels.weixin import WeixinAccountConfig, WeixinChannel, WeixinConfig

        async def dummy_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            yield MessageEvent.completed()

        # Create WeixinChannel with default constraints
        account = WeixinAccountConfig(account_id="test_acc", token="test_token")
        config = WeixinConfig(accounts=[account])
        ch = WeixinChannel(processor=dummy_processor, config=config)
        assert ch._constraints.show_thinking is False

    @pytest.mark.asyncio
    async def test_constraint_respected_across_event_sequence(self) -> None:
        """Constraints should be respected consistently throughout event sequence."""
        from octop_gateway.constraints import ChannelConstraints

        async def complex_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
            # Complex sequence with thinking, deltas, and tool hints
            yield MessageEvent.thinking("Analyzing...")
            yield MessageEvent.thinking_delta("Step 1...")
            yield MessageEvent.flush()
            yield MessageEvent.delta("Response: ")
            yield MessageEvent.tool_start("search")
            yield MessageEvent.tool_end("search", result="found")
            yield MessageEvent.delta("Done")
            yield MessageEvent.completed()

        ch = EchoChannel(processor=complex_processor)
        ch._constraints = ChannelConstraints(show_thinking=False)
        await ch.handle_inbound("test")

        # With show_thinking=False, should not have any thinking in output
        all_output = " ".join(msg[1] for msg in ch.sent_messages)
        assert "Analyzing" not in all_output
        assert "Step 1" not in all_output
        # But should have the response
        assert "Response" in all_output or "Done" in all_output


# ---------------------------------------------------------------------------
# load_media_bytes priority and configuration contracts
# ---------------------------------------------------------------------------


class TestLoadMediaBytes:
    """Verify the data > local_path > url priority and required-backend rule."""

    @pytest.mark.asyncio
    async def test_data_field_wins_over_local_path_and_url(self, tmp_path) -> None:
        """When part.data is set, it is decoded and returned without I/O,
        even if local_path and url are also set.
        """
        import base64 as _b64
        from unittest.mock import AsyncMock as _AsyncMock

        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        # Pre-populate the backend with *different* bytes so we can detect
        # accidental fall-through.
        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"WRONG_FROM_BACKEND", "img/from_backend.png")

        ch = EchoChannel(processor=make_echo_processor)
        ch.set_media_backend(backend)
        # fetch_remote_media must NOT be called.
        ch.fetch_remote_media = _AsyncMock(side_effect=AssertionError("URL path must not be hit"))

        part = ImageContent(
            data=_b64.b64encode(b"INLINE").decode(),
            local_path="img/from_backend.png",
            url="https://example.com/x.png",
            mime_type="image/png",
        )

        raw, mime = await ch.load_media_bytes(part)
        assert raw == b"INLINE"
        assert mime == "image/png"
        ch.fetch_remote_media.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_path_without_backend_raises(self) -> None:
        """A part with local_path but no MediaBackend configured is a
        misconfiguration — raise rather than silently falling back to URL.
        """
        from octop_gateway.models import ImageContent

        ch = EchoChannel(processor=make_echo_processor)
        # No backend configured.
        part = ImageContent(local_path="should/exist.png", url="https://x/y")

        with pytest.raises(RuntimeError, match="local_path"):
            await ch.load_media_bytes(part)

    @pytest.mark.asyncio
    async def test_invalid_base64_raises_value_error(self) -> None:
        """Malformed base64 in part.data should produce a clear error."""
        from octop_gateway.models import ImageContent

        ch = EchoChannel(processor=make_echo_processor)
        part = ImageContent(data="!!!not-valid-base64!!!", mime_type="image/png")

        with pytest.raises(ValueError):
            await ch.load_media_bytes(part)

    @pytest.mark.asyncio
    async def test_local_path_falls_through_when_no_data(self, tmp_path) -> None:
        """With data unset, local_path is read from the backend."""
        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"BACKEND_BYTES", "x/y.png")

        ch = EchoChannel(processor=make_echo_processor)
        ch.set_media_backend(backend)
        part = ImageContent(local_path="x/y.png", mime_type="image/png")

        raw, mime = await ch.load_media_bytes(part)
        assert raw == b"BACKEND_BYTES"
        assert mime == "image/png"

    @pytest.mark.asyncio
    async def test_url_only_caches_to_backend(self, tmp_path) -> None:
        """URL-only fallback fetches and caches into the backend."""
        from unittest.mock import AsyncMock as _AsyncMock

        from octop_gateway.media import FileSystemMediaBackend
        from octop_gateway.models import ImageContent

        backend = FileSystemMediaBackend(tmp_path)
        ch = EchoChannel(processor=make_echo_processor)
        ch.set_media_backend(backend)
        ch.fetch_remote_media = _AsyncMock(return_value=(b"FETCHED", "image/png"))

        part = ImageContent(url="https://cdn.example.com/x.png")
        raw, mime = await ch.load_media_bytes(part)
        assert raw == b"FETCHED"
        assert mime == "image/png"
        assert part.local_path is not None
        assert await backend.read(part.local_path) == b"FETCHED"


# ---------------------------------------------------------------------------
# Rate-limit acquisition semantics
# ---------------------------------------------------------------------------


class TestRateLimitAcquisition:
    """One public call → one acquire. No double-throttling from internal
    cross-method calls in subclasses.
    """

    def _channel_with_counting_limiter(self) -> tuple[EchoChannel, list[int]]:
        """Build a channel whose rate-limiter counts acquire() calls."""
        from octop_gateway.constraints import ChannelConstraints, RateLimiter

        ch = EchoChannel(processor=make_echo_processor)
        # Configure constraints AFTER construction so we override the no-op
        # default with an instrumented limiter.
        ch._constraints = ChannelConstraints(send_rate_limit=(1000, 1.0))
        counter = [0]

        class _CountingLimiter(RateLimiter):
            async def acquire(self) -> None:
                counter[0] += 1
                # Skip the real timestamp logic — we care about call count.

        ch._rate_limiter = _CountingLimiter(max_calls=1000, window_seconds=1.0)
        return ch, counter

    @pytest.mark.asyncio
    async def test_reply_text_acquires_once(self) -> None:
        ch, counter = self._channel_with_counting_limiter()
        user = ChannelSubject(subject_id="u1", first_seen=0, last_seen=0)
        await ch.reply_text(user, "hello")
        assert counter[0] == 1

    @pytest.mark.asyncio
    async def test_push_text_acquires_once(self) -> None:
        ch, counter = self._channel_with_counting_limiter()
        user = ChannelSubject(subject_id="u1", first_seen=0, last_seen=0)
        await ch.push_text(user, "hello")
        assert counter[0] == 1

    @pytest.mark.asyncio
    async def test_reply_content_acquires_once_for_multi_part(self) -> None:
        """A single reply_content with multiple parts is one user-visible
        message → one acquire, regardless of how many parts the subclass
        internally fans out to ``_send_text`` / ``_send_media``.
        """
        from octop_gateway.models import ImageContent, TextContent

        ch, counter = self._channel_with_counting_limiter()
        # EchoChannel._send_content is an abstract stub — give it a fan-out
        # implementation that exercises the no-double-throttle rule.
        original_send_content = ch._send_content

        async def _fanout(user, parts):
            # Subclass-style internal fan-out: call _send_text per text part,
            # _send_media per media part. Must NOT re-acquire.
            for p in parts:
                if isinstance(p, TextContent):
                    await ch._send_text(user, p.text)
                else:
                    await ch._send_media(user, p)
            await original_send_content(user, parts)

        ch._send_content = _fanout  # type: ignore[method-assign]

        parts = [
            TextContent(text="hello"),
            TextContent(text="world"),
            ImageContent(url="https://cdn/x.png"),
        ]
        user = ChannelSubject(subject_id="u1", first_seen=0, last_seen=0)
        await ch.reply_content(user, parts)
        assert counter[0] == 1

    @pytest.mark.asyncio
    async def test_send_media_internal_text_fallback_no_double_acquire(self) -> None:
        """When ``_send_media`` falls back to calling ``_send_text``
        internally (the typical pattern for URL-only platforms), the
        public ``reply_media`` still acquires exactly once.
        """
        from octop_gateway.models import FileContent

        ch, counter = self._channel_with_counting_limiter()

        async def _fallback_send_media(user, media):
            # Subclass-style fallback: emit a text marker for unsupported
            # media. This MUST NOT re-acquire.
            await ch._send_text(user, "[fallback]")

        ch._send_media = _fallback_send_media  # type: ignore[method-assign]

        user = ChannelSubject(subject_id="u1", first_seen=0, last_seen=0)
        await ch.reply_media(user, FileContent(filename="x.bin", local_path="x.bin"))
        assert counter[0] == 1

    @pytest.mark.asyncio
    async def test_no_limiter_no_acquire(self) -> None:
        """A channel with no ``send_rate_limit`` configured never blocks
        on ``_acquire_rate_slot``.
        """
        ch = EchoChannel(processor=make_echo_processor)
        # No limiter installed.
        assert ch._rate_limiter is None
        user = ChannelSubject(subject_id="u1", first_seen=0, last_seen=0)
        await ch.reply_text(user, "hello")
        await ch.push_text(user, "hello")
        # If we got here without hanging, no-op confirmed.
