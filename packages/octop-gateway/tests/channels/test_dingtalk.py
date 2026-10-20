"""Integration tests for DingTalk channel.

Tests DingTalk API connectivity including:
- Access token retrieval via OAuth2
- Bot info query

Run with: pytest tests/channels/test_dingtalk.py -m integration
Requires: DINGTALK_APP_KEY and DINGTALK_APP_SECRET environment variables
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from octop_gateway.channels.dingtalk import (
    DingTalkChannel,
    DingTalkConfig,
    _DingTalkMessageHandler,
)
from octop_gateway.media import FileSystemMediaBackend
from octop_gateway.models import (
    ChannelSubject,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
)

# ---------------------------------------------------------------------------
# Test config
# ---------------------------------------------------------------------------

# DingTalk credentials not yet provided, leave empty for now
_DINGTALK_APP_KEY = os.environ.get("DINGTALK_APP_KEY", "")
_DINGTALK_APP_SECRET = os.environ.get("DINGTALK_APP_SECRET", "")


def _make_config() -> DingTalkConfig:
    return DingTalkConfig(
        app_key=_DINGTALK_APP_KEY,
        app_secret=_DINGTALK_APP_SECRET,
    )


def _has_dingtalk_creds() -> bool:
    return bool(_DINGTALK_APP_KEY and _DINGTALK_APP_SECRET)


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------


class TestDingTalkChannelUnit:
    """Unit tests for DingTalk channel logic."""

    def test_channel_id(self) -> None:
        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        assert ch.channel_type == "dingtalk"

    def test_parse_inbound_text(self) -> None:
        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        payload = {
            "msgtype": "text",
            "text": {"content": "hello dingtalk"},
            "sender_id": "staff_001",
            "sender_nick": "Test User",
            "conversation_id": "conv_123",
            "conversation_type": "1",
            "msg_id": "msg_dt_001",
            "webhook_url": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_type == "dingtalk"
        assert "hello dingtalk" in msg.text
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "staff_001"

    def test_parse_inbound_with_webhook(self) -> None:
        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        webhook = "https://oapi.dingtalk.com/robot/sendBySession?session=abc"
        payload = {
            "msgtype": "text",
            "text": {"content": "hi"},
            "sender_id": "staff_002",
            "conversation_id": "conv_456",
            "conversation_type": "1",
            "msg_id": "msg_dt_002",
            "webhook_url": webhook,
        }
        msg = ch.parse_inbound(payload)
        assert msg.metadata.get("webhook_url") == webhook

    def test_parse_inbound_picture(self) -> None:
        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        payload = {
            "msgtype": "picture",
            "content": {"downloadCode": "img_download_001"},
            "sender_id": "staff_003",
            "conversation_id": "conv_789",
            "conversation_type": "1",
            "msg_id": "msg_dt_003",
        }
        msg = ch.parse_inbound(payload)
        assert len(msg.content) >= 1

    @pytest.mark.asyncio
    async def test_picture_download_code_is_resolved_and_persisted(self, tmp_path: Path) -> None:
        class FakeResponse:
            def __init__(
                self,
                *,
                json_body: dict[str, Any] | None = None,
                data: bytes = b"",
                content_type: str = "application/octet-stream",
            ) -> None:
                self._json_body = json_body or {}
                self._data = data
                self.content_type = content_type

            async def __aenter__(self) -> FakeResponse:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            def raise_for_status(self) -> None:
                return None

            async def json(self) -> dict[str, Any]:
                return self._json_body

            async def read(self) -> bytes:
                return self._data

        class FakeHttp:
            def __init__(self) -> None:
                self.closed = False
                self.post_calls: list[dict[str, Any]] = []
                self.get_calls: list[str] = []

            def post(self, url: str, **kwargs: Any) -> FakeResponse:
                self.post_calls.append({"url": url, **kwargs})
                return FakeResponse(json_body={"downloadUrl": "https://download.example.test/photo.png"})

            def get(self, url: str) -> FakeResponse:
                self.get_calls.append(url)
                return FakeResponse(data=b"PNG-BYTES", content_type="image/png")

        config = DingTalkConfig(
            app_key="test_key",
            app_secret="test_secret",
            robot_code="robot_001",
        )
        ch = DingTalkChannel(
            processor=_noop_processor,
            config=config,
            channel_id="channel_001",
        )
        ch.set_media_backend(FileSystemMediaBackend(tmp_path))
        ch._access_token = "access-token"
        ch._token_expires_at = float("inf")
        http = FakeHttp()
        ch._http = http

        msg = ch.parse_inbound(
            {
                "msgtype": "picture",
                "content": {"downloadCode": "download-code-001"},
                "sender_id": "staff_003",
                "conversation_id": "conv_789",
                "conversation_type": "1",
                "msg_id": "msg_dt_003",
            }
        )
        await ch._persist_media(msg)

        image = msg.content[0]
        assert isinstance(image, ImageContent)
        assert image.local_path is not None
        assert image.mime_type == "image/png"
        assert image.size == len(b"PNG-BYTES")
        assert (tmp_path / image.local_path).read_bytes() == b"PNG-BYTES"
        assert http.post_calls == [
            {
                "url": "https://api.dingtalk.com/v1.0/robot/messageFiles/download",
                "headers": {
                    "x-acs-dingtalk-access-token": "access-token",
                    "Content-Type": "application/json",
                },
                "json": {
                    "downloadCode": "download-code-001",
                    "robotCode": "robot_001",
                },
            }
        ]
        assert http.get_calls == ["https://download.example.test/photo.png"]

    @pytest.mark.asyncio
    async def test_fetch_remote_media_uses_http_url_directly(self) -> None:
        class FakeResponse:
            content_type = "image/jpeg"

            async def __aenter__(self) -> FakeResponse:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            def raise_for_status(self) -> None:
                return None

            async def read(self) -> bytes:
                return b"JPEG-BYTES"

        class FakeHttp:
            def __init__(self) -> None:
                self.closed = False
                self.get_calls: list[str] = []

            def get(self, url: str) -> FakeResponse:
                self.get_calls.append(url)
                return FakeResponse()

            def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
                raise AssertionError("direct media URLs must not be resolved as downloadCodes")

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        http = FakeHttp()
        ch._http = http

        data, mime = await ch.fetch_remote_media("https://cdn.example.test/photo.jpg")

        assert data == b"JPEG-BYTES"
        assert mime == "image/jpeg"
        assert http.get_calls == ["https://cdn.example.test/photo.jpg"]

    @pytest.mark.asyncio
    async def test_direct_local_file_uses_openapi_even_with_session_webhook(self, tmp_path: Path) -> None:
        class FakeResponse:
            def __init__(self, body: dict[str, Any]) -> None:
                self._body = body

            async def __aenter__(self) -> FakeResponse:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

            def raise_for_status(self) -> None:
                return None

            async def json(self) -> dict[str, Any]:
                return self._body

        class FakeHttp:
            def __init__(self) -> None:
                self.closed = False
                self.post_calls: list[dict[str, Any]] = []

            def post(self, url: str, **kwargs: Any) -> FakeResponse:
                self.post_calls.append({"url": url, **kwargs})
                if "/media/upload" in url:
                    return FakeResponse({"errcode": 0, "media_id": "@media-pdf"})
                return FakeResponse({"processQueryKey": "query-001"})

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret", robot_code="robot_001")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        ch.set_media_backend(FileSystemMediaBackend(tmp_path))
        ch._access_token = "access-token"
        ch._token_expires_at = float("inf")
        http = FakeHttp()
        ch._http = http
        (tmp_path / "paper.pdf").write_bytes(b"PDF-BYTES")
        subject = ChannelSubject(
            subject_id="staff_001",
            metadata={
                "conversation_type": "1",
                "conversation_id": "cid-direct",
                "webhook_url": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
            },
        )

        await ch._send_media(
            subject,
            FileContent(local_path="paper.pdf", filename="paper.pdf", mime_type="application/pdf"),
        )

        assert [call["url"] for call in http.post_calls] == [
            "https://oapi.dingtalk.com/media/upload?access_token=access-token&type=file",
            "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
        ]
        message_payload = http.post_calls[1]["json"]
        assert message_payload["msgKey"] == "sampleFile"
        assert json.loads(message_payload["msgParam"]) == {
            "mediaId": "@media-pdf",
            "fileName": "paper.pdf",
            "fileType": "pdf",
        }

    def test_stream_handler_has_pre_start(self) -> None:
        """SDK DingTalkStreamClient.pre_start() calls handler.pre_start()."""
        import dingtalk_stream

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        handler = _DingTalkMessageHandler(ch)

        assert isinstance(handler, dingtalk_stream.ChatbotHandler)
        # Must not raise AttributeError (Octop #73)
        handler.pre_start()

    @pytest.mark.asyncio
    async def test_stream_handler_process_dispatches(self) -> None:
        import dingtalk_stream

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        received: list[dict] = []
        ch._running = True
        ch._enqueue_callback = received.append

        handler = _DingTalkMessageHandler(ch)
        callback = dingtalk_stream.CallbackMessage()
        callback.data = {
            "senderStaffId": "staff_100",
            "senderNick": "Alice",
            "conversationId": "cid_1",
            "conversationType": "1",
            "msgId": "mid_1",
            "msgtype": "text",
            "text": {"content": "ping"},
            "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=x",
            "createAt": 1_700_000_000_000,
        }

        code, message = await handler.process(callback)
        assert code == dingtalk_stream.AckMessage.STATUS_OK
        assert message == "OK"
        assert len(received) == 1
        assert received[0]["sender_id"] == "staff_100"
        assert received[0]["webhook_url"].startswith("https://oapi.dingtalk.com/")
        assert received[0]["text"]["content"] == "ping"

    def test_stream_client_pre_start_with_handler(self) -> None:
        """Registering our handler must survive DingTalkStreamClient.pre_start()."""
        import dingtalk_stream

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        client = dingtalk_stream.DingTalkStreamClient(
            dingtalk_stream.Credential("cid", "secret"),
        )
        client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            _DingTalkMessageHandler(ch),
        )
        client.pre_start()  # must not raise

    @pytest.mark.asyncio
    async def test_stream_client_stop_closes_connection_and_task(self, monkeypatch) -> None:
        """Stopping a channel must not leave a probe stream consuming messages."""
        import dingtalk_stream

        started = asyncio.Event()

        class FakeWebSocket:
            def __init__(self) -> None:
                self.closed = False

            async def close(self) -> None:
                self.closed = True

        class FakeStreamClient:
            def __init__(self, _credential) -> None:
                self.websocket = FakeWebSocket()

            def register_callback_handler(self, _topic, _handler) -> None:
                pass

            async def start(self) -> None:
                started.set()
                while True:
                    try:
                        await asyncio.Future()
                    except asyncio.CancelledError:
                        # Match dingtalk-stream 0.24.3: the first cancellation
                        # is swallowed before its reconnect sleep.
                        await asyncio.sleep(10)

            def start_forever(self) -> None:
                raise AssertionError("async channels must not call start_forever")

        monkeypatch.setattr(dingtalk_stream, "DingTalkStreamClient", FakeStreamClient)

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        await ch._start_stream_client()
        await asyncio.wait_for(started.wait(), timeout=1)

        client = ch._stream_client
        task = ch._stream_task
        await ch._stop_stream_client()

        assert client.websocket.closed
        assert task.done()
        assert ch._stream_client is None
        assert ch._stream_task is None

    @pytest.mark.asyncio
    async def test_session_webhook_sends_markdown(self) -> None:
        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _tb) -> None:
                pass

            async def json(self) -> dict[str, int]:
                return {"errcode": 0}

        class FakeHttp:
            def __init__(self) -> None:
                self.closed = False
                self.payload = None

            def post(self, _url, *, json):
                self.payload = json
                return FakeResponse()

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        http = FakeHttp()
        ch._http = http

        await ch._send_via_webhook("https://example.test/session", "**bold**\n\n- item")

        assert http.payload == {
            "msgtype": "markdown",
            "markdown": {"title": "Octop", "text": "**bold**\n\n- item"},
        }

    @pytest.mark.asyncio
    async def test_session_webhook_uses_text_for_long_messages(self) -> None:
        class FakeResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _tb) -> None:
                pass

            async def json(self) -> dict[str, int]:
                return {"errcode": 0}

        class FakeHttp:
            def __init__(self) -> None:
                self.closed = False
                self.payload = None

            def post(self, _url, *, json):
                self.payload = json
                return FakeResponse()

        config = DingTalkConfig(app_key="test_key", app_secret="test_secret")
        ch = DingTalkChannel(processor=_noop_processor, config=config)
        http = FakeHttp()
        ch._http = http
        text = "x" * 3501

        await ch._send_via_webhook("https://example.test/session", text)

        assert http.payload == {
            "msgtype": "text",
            "text": {"content": text},
        }


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not _has_dingtalk_creds(), reason="DINGTALK_APP_KEY/SECRET not set")
class TestDingTalkChannelIntegration:
    """Integration tests for DingTalk (requires valid credentials)."""

    @pytest.mark.asyncio
    async def test_get_access_token(self) -> None:
        """Verify access token retrieval from DingTalk OAuth."""
        ch = DingTalkChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            assert token is not None
            assert len(token) > 10
            print(f"  DingTalk token: {token[:20]}...")
        finally:
            await ch._close_http()
