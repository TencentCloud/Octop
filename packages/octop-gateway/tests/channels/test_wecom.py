"""Unit tests for WeCom (Enterprise WeChat) channel.

Tests cover:
- Config creation and field storage
- Channel initialization
- Inbound message parsing (text, passthrough)
- Session ID resolution

No network calls — all tests are pure unit tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from octop_gateway.channels.wecom import WeComChannel, WeComConfig
from octop_gateway.models import (
    ChannelSubject,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> WeComConfig:
    return WeComConfig(bot_id="bot_test_001", secret="secret_xyz_123")


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestWeComChannelUnit:
    """Unit tests for WeCom channel logic (no API calls)."""

    def test_config_creation(self) -> None:
        """WeComConfig stores bot_id, secret, and optional ws_url."""
        config = _make_config()
        assert config.bot_id == "bot_test_001"
        assert config.secret == "secret_xyz_123"
        assert config.ws_url == ""

    def test_config_with_ws_url(self) -> None:
        """WeComConfig accepts custom ws_url."""
        config = WeComConfig(bot_id="b1", secret="s1", ws_url="wss://custom.example.com")
        assert config.ws_url == "wss://custom.example.com"

    def test_channel_init(self) -> None:
        """WeComChannel accepts processor, config, constraints kwargs."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        assert ch.channel_type == "wecom"
        assert ch._config.bot_id == "bot_test_001"
        assert ch._config.secret == "secret_xyz_123"
        assert ch._connected is False
        assert ch._running is False

    def test_channel_init_with_constraints(self) -> None:
        """WeComChannel accepts optional constraints."""
        from octop_gateway.constraints import ChannelConstraints

        custom = ChannelConstraints(reply_timeout=20.0)
        ch = WeComChannel(processor=_noop_processor, config=_make_config(), constraints=custom)
        assert ch._constraints.reply_timeout == 20.0

    def test_parse_inbound_text(self) -> None:
        """Raw payload with msgtype=text parses to InboundMessage with correct fields."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "msgid": "msg_wecom_001",
            "msgtype": "text",
            "text": {"content": "hello"},
            "from": {"userid": "T48500024A"},
            "chattype": "single",
            "chatid": "",
            "response_url": "https://qyapi.weixin.qq.com/callback/reply",
        }
        msg = ch.parse_inbound(payload)

        assert isinstance(msg, InboundMessage)
        assert msg.channel_type == "wecom"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "T48500024A"
        assert msg.text == "hello"
        assert msg.metadata["msgid"] == "msg_wecom_001"
        assert msg.metadata["chat_type"] == "single"
        assert msg.metadata["response_url"] == "https://qyapi.weixin.qq.com/callback/reply"

    def test_parse_inbound_text_with_chat_id(self) -> None:
        """When chatid is present, session_id is still the connection session."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "msgid": "msg_002",
            "msgtype": "text",
            "text": {"content": "group msg"},
            "from": {"userid": "user_abc"},
            "chattype": "group",
            "chatid": "chat_room_123",
        }
        msg = ch.parse_inbound(payload)

        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "user_abc"
        assert msg.text == "group msg"

    def test_parse_inbound_returns_existing(self) -> None:
        """Passing an InboundMessage directly returns it unchanged."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        original = InboundMessage(
            channel_id="wecom",
            content=[TextContent(text="passthrough")],
            channel_subject=ChannelSubject(subject_id="user_pass"),
        )
        result = ch.parse_inbound(original)
        assert result is original
        assert result.text == "passthrough"

    def test_parse_inbound_image(self) -> None:
        """Image payload produces ImageContent."""
        from octop_gateway.models import ImageContent

        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "msgtype": "image",
            "image": {"url": "https://example.com/pic.jpg", "aeskey": "image-key"},
            "from": {"userid": "img_user"},
        }
        msg = ch.parse_inbound(payload)
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        assert len(images) == 1
        assert images[0].url == "https://example.com/pic.jpg"
        assert msg.metadata["_media_aes_keys"]["https://example.com/pic.jpg"] == "image-key"

    def test_parse_inbound_file(self) -> None:
        """File payload produces FileContent."""
        from octop_gateway.models import FileContent

        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "msgtype": "file",
            "file": {
                "url": "https://example.com/doc.pdf",
                "file_name": "report.pdf",
                "aeskey": "file-key",
            },
            "from": {"userid": "file_user"},
        }
        msg = ch.parse_inbound(payload)
        files = [p for p in msg.content if isinstance(p, FileContent)]
        assert len(files) == 1
        assert files[0].url == "https://example.com/doc.pdf"
        assert files[0].filename == "report.pdf"
        assert msg.metadata["_media_aes_keys"]["https://example.com/doc.pdf"] == "file-key"

    def test_parse_inbound_mixed_preserves_text_image_and_aeskey(self) -> None:
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        msg = ch.parse_inbound(
            {
                "msgtype": "mixed",
                "mixed": {
                    "msg_item": [
                        {"msgtype": "text", "text": {"content": "see image"}},
                        {
                            "msgtype": "image",
                            "image": {
                                "url": "https://example.com/mixed.png",
                                "aeskey": "mixed-key",
                            },
                        },
                    ]
                },
                "from": {"userid": "mixed-user"},
            }
        )

        assert msg.text == "see image"
        images = [part for part in msg.content if isinstance(part, ImageContent)]
        assert len(images) == 1
        assert msg.metadata["_media_aes_keys"][images[0].url] == "mixed-key"

    @pytest.mark.asyncio
    async def test_persist_media_downloads_and_decrypts_with_aeskey(self) -> None:
        """Inbound media must use the SDK decrypting download path."""

        class _MemoryBackend:
            def __init__(self) -> None:
                self.saved: dict[str, bytes] = {}

            async def save(self, data: bytes, key: str) -> None:
                self.saved[key] = data

            async def read(self, key: str) -> bytes:
                return self.saved[key]

            async def exists(self, key: str) -> bool:
                return key in self.saved

        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        ch._ws_client = AsyncMock()
        ch._ws_client.download_file.return_value = {
            "buffer": b"%PDF-decrypted",
            "filename": "paper.pdf",
        }
        backend = _MemoryBackend()
        ch.set_media_backend(backend)
        message = ch.parse_inbound(
            {
                "msgtype": "file",
                "file": {"url": "https://example.com/encrypted", "aeskey": "secret-key"},
                "from": {"userid": "file_user"},
            }
        )

        await ch._persist_media(message)

        ch._ws_client.download_file.assert_awaited_once_with("https://example.com/encrypted", "secret-key")
        media = next(part for part in message.content if isinstance(part, FileContent))
        assert media.filename == "paper.pdf"
        assert media.mime_type == "application/pdf"
        assert media.local_path is not None
        assert backend.saved[media.local_path] == b"%PDF-decrypted"

    def test_parse_inbound_empty_payload(self) -> None:
        """Empty dict produces InboundMessage with empty TextContent fallback."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        msg = ch.parse_inbound({})
        assert msg.channel_type == "wecom"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "unknown"
        # Should have at least one content part (empty text fallback)
        assert len(msg.content) >= 1

    def test_default_constraints(self) -> None:
        """Channel provides reasonable default constraints."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        defaults = ch._default_constraints()
        assert defaults.reply_timeout == 10.0
        assert defaults.timeout_strategy == "placeholder"
        assert defaults.show_thinking is False

    @pytest.mark.asyncio
    async def test_send_text_proactive_uses_send_message(self) -> None:
        """No frame/response_url → proactive send_message (cron path)."""
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        ch._ws_client = AsyncMock()
        subject = ChannelSubject(
            subject_id="T48500024A",
            metadata={"chat_type": "single"},
        )

        await ch._send_text(subject, "cron hello")

        ch._ws_client.send_message.assert_awaited_once_with(
            "T48500024A",
            {"msgtype": "markdown", "markdown": {"content": "cron hello"}},
        )

    @pytest.mark.asyncio
    async def test_send_media_uploads_and_replies_natively(self) -> None:
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        ws = AsyncMock()
        ws.upload_media.return_value = {"media_id": "MEDIA_123"}
        ch._ws_client = ws
        ch.load_media_bytes = AsyncMock(return_value=(b"pdf-bytes", "application/pdf"))  # type: ignore[method-assign]
        frame = {"headers": {"req_id": "request-1"}}
        subject = ChannelSubject(subject_id="user-1", metadata={"_frame": frame, "_ws_client": ws})

        await ch._send_media(subject, FileContent(filename="paper.pdf", local_path="paper.pdf"))

        ws.upload_media.assert_awaited_once_with(b"pdf-bytes", type="file", filename="paper.pdf")
        ws.reply_media.assert_awaited_once_with(frame, "file", "MEDIA_123")

    @pytest.mark.asyncio
    async def test_send_media_proactive_uses_chat_id(self) -> None:
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        ws = AsyncMock()
        ws.upload_media.return_value = {"media_id": "IMAGE_123"}
        ch._ws_client = ws
        ch.load_media_bytes = AsyncMock(return_value=(b"image-bytes", "image/png"))  # type: ignore[method-assign]
        subject = ChannelSubject(subject_id="user-1", metadata={"chat_id": "chat-1"})

        await ch._send_media(subject, ImageContent(local_path="image.png", mime_type="image/png"))

        ws.send_media_message.assert_awaited_once_with("chat-1", "image", "IMAGE_123")

    def test_resolve_push_subject_enriches_sparse_metadata(self) -> None:
        ch = WeComChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(subject_id="T48500024A", metadata={})
        resolved = ch.resolve_push_subject(subject)
        assert resolved.metadata.get("chat_id") == "T48500024A"


# ---------------------------------------------------------------------------
# Stream override: rate-limit / first-token timeout / error placeholder
# ---------------------------------------------------------------------------


class _FakeWSClient:
    """Captures every reply_stream call for assertion."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.media_replies: list[tuple[dict, str, str]] = []

    async def reply_stream(self, *, frame, stream_id, content, finish):
        self.calls.append({"content": content, "finish": finish, "stream_id": stream_id})

    async def upload_media(self, data, *, type, filename):
        return {"media_id": "MEDIA_FROM_EVENT"}

    async def reply_media(self, frame, media_type, media_id):
        self.media_replies.append((frame, media_type, media_id))


def _make_stream_payload(ws: _FakeWSClient) -> dict:
    """Build the dict shape WeComChannel.parse_inbound expects.

    The channel injects ``self._ws_client`` into metadata, so callers must
    set ``ch._ws_client = ws`` before invoking ``handle_inbound``.
    """
    return {
        "msgid": "m1",
        "msgtype": "text",
        "from": {"userid": "user_001"},
        "text": {"content": "hello"},
        "_frame": {"body": {}},
    }


class TestWeComStreamConstraints:
    """Verify the WeCom stream override honours rate-limit, first-token
    timeout, and uses placeholder_text for the error path.
    """

    @pytest.mark.asyncio
    async def test_stream_acquires_one_rate_slot_for_whole_reply(self) -> None:
        """A single user message → one rate-limit acquire, regardless of
        how many partial reply_stream chunks are emitted.
        """
        from octop_gateway.constraints import ChannelConstraints

        async def chatty(msg: InboundMessage):
            for piece in ("Hello ", "world", "!"):
                yield MessageEvent.delta(piece)
            yield MessageEvent.completed()

        ch = WeComChannel(processor=chatty, config=_make_config())
        # Disable timeout for this test — we only care about rate-limit.
        ch._constraints = ChannelConstraints(
            send_rate_limit=(2, 5.0),
            reply_timeout=0,
            timeout_strategy="none",
        )

        counter = [0]

        async def _counting_acquire():
            counter[0] += 1

        ch._acquire_rate_slot = _counting_acquire  # type: ignore[method-assign]

        ws = _FakeWSClient()
        ch._ws_client = ws
        payload = _make_stream_payload(ws)
        # parse_inbound preserves _ws_client / _frame in metadata; verify.
        await ch.handle_inbound(payload)

        assert counter[0] == 1
        # And reply_stream actually streamed the chunks (more than 1 call).
        assert len(ws.calls) >= 2
        assert ws.calls[-1]["finish"] is True

    @pytest.mark.asyncio
    async def test_message_event_media_is_uploaded_instead_of_dropped(self) -> None:
        async def returns_file(msg: InboundMessage):
            yield MessageEvent(
                type=MessageEventType.MESSAGE,
                content=[FileContent(filename="paper.pdf", local_path="paper.pdf")],
            )
            yield MessageEvent.completed()

        ch = WeComChannel(processor=returns_file, config=_make_config())
        ch._constraints.reply_timeout = 0
        ch.load_media_bytes = AsyncMock(return_value=(b"pdf", "application/pdf"))  # type: ignore[method-assign]
        ws = _FakeWSClient()
        ch._ws_client = ws

        await ch.handle_inbound(_make_stream_payload(ws))

        assert ws.media_replies
        assert ws.media_replies[0][1:] == ("file", "MEDIA_FROM_EVENT")

    @pytest.mark.asyncio
    async def test_first_token_timeout_emits_placeholder(self) -> None:
        """If the first event takes longer than reply_timeout * 0.8, a
        placeholder is streamed (finish=False) before the real content.
        """
        import asyncio as _asyncio

        from octop_gateway.constraints import ChannelConstraints

        async def slow_first(msg: InboundMessage):
            # First event is delayed; placeholder should fire first.
            await _asyncio.sleep(0.3)
            yield MessageEvent.delta("late hello")
            yield MessageEvent.completed()

        ch = WeComChannel(processor=slow_first, config=_make_config())
        ch._constraints = ChannelConstraints(
            reply_timeout=0.1,  # 0.1 * 0.8 = 80 ms
            timeout_strategy="placeholder",
            placeholder_texts=["__PLACEHOLDER__"],
        )

        # Bypass rate-limit for clarity.
        async def _noop():
            return None

        ch._acquire_rate_slot = _noop  # type: ignore[method-assign]

        ws = _FakeWSClient()
        ch._ws_client = ws
        await ch.handle_inbound(_make_stream_payload(ws))

        # First call should be the placeholder (finish=False).
        assert ws.calls, "expected at least the placeholder call"
        assert ws.calls[0]["content"] == "__PLACEHOLDER__"
        assert ws.calls[0]["finish"] is False
        # Final call should still complete the stream with the real content.
        assert ws.calls[-1]["finish"] is True
        assert "late hello" in ws.calls[-1]["content"]

    @pytest.mark.asyncio
    async def test_first_token_timeout_skipped_when_strategy_none(self) -> None:
        """timeout_strategy='none' must not wrap the first token in
        wait_for, even if reply_timeout > 0.
        """
        from octop_gateway.constraints import ChannelConstraints

        async def fast(msg: InboundMessage):
            yield MessageEvent.delta("hi")
            yield MessageEvent.completed()

        ch = WeComChannel(processor=fast, config=_make_config())
        ch._constraints = ChannelConstraints(
            reply_timeout=0.1,
            timeout_strategy="none",  # ← disables placeholder wrapping
            placeholder_texts=["NEVER"],
        )

        async def _noop():
            return None

        ch._acquire_rate_slot = _noop  # type: ignore[method-assign]

        ws = _FakeWSClient()
        ch._ws_client = ws
        await ch.handle_inbound(_make_stream_payload(ws))

        # No placeholder should appear among the streamed chunks.
        for call in ws.calls:
            assert "NEVER" not in call["content"]

    @pytest.mark.asyncio
    async def test_error_path_uses_constraints_placeholder_text(self) -> None:
        """An exception inside the stream loop emits a finish=True chunk
        whose content comes from ``placeholder_text``, not a hardcoded
        Chinese string.
        """
        from octop_gateway.constraints import ChannelConstraints

        async def explodes(msg: InboundMessage):
            yield MessageEvent.delta("partial...")
            raise RuntimeError("boom")

        ch = WeComChannel(processor=explodes, config=_make_config())
        ch._constraints = ChannelConstraints(
            reply_timeout=0,
            timeout_strategy="none",
            placeholder_texts=["__ERROR_PLACEHOLDER__"],
        )

        async def _noop():
            return None

        ch._acquire_rate_slot = _noop  # type: ignore[method-assign]

        ws = _FakeWSClient()
        ch._ws_client = ws
        await ch.handle_inbound(_make_stream_payload(ws))

        # The terminating chunk must be the configured placeholder.
        assert ws.calls
        assert ws.calls[-1]["finish"] is True
        assert ws.calls[-1]["content"] == "__ERROR_PLACEHOLDER__"
