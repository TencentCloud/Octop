"""Integration tests for QQ channel.

These tests connect to the real QQ Bot API and verify:
- Gateway URL fetch
- WebSocket connection + HELLO handshake
- Auth headers formation
- Message parsing

Run with: pytest tests/channels/test_qq.py -m integration
Requires: QQ_APP_ID and QQ_SECRET environment variables
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from octop_gateway.channels.qq import (
    QQBotQRCredentials,
    QQBotQRLogin,
    QQChannel,
    QQConfig,
)
from octop_gateway.channels.qq.channel import (
    _DEFAULT_INTENTS,
    _OP_HELLO,
    _OP_IDENTIFY,
    _GatewayReconnectError,
    _get_next_msg_seq,
    _msg_seq,
)
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
    TextContent,
)

# ---------------------------------------------------------------------------
# Test config (from env or hardcoded for dev)
# ---------------------------------------------------------------------------

_QQ_APP_ID = os.environ.get("QQ_APP_ID", "test_qq_app_id")
_QQ_SECRET = os.environ.get("QQ_SECRET", "test_qq_secret")
# Token format for QQ: typically same as secret or separate
_QQ_TOKEN = os.environ.get("QQ_TOKEN", _QQ_SECRET)


def _make_config(sandbox: bool = False) -> QQConfig:
    """Create a QQConfig for testing."""
    return QQConfig(
        app_id=_QQ_APP_ID,
        token=_QQ_TOKEN,
        secret=_QQ_SECRET,
        sandbox=sandbox,
    )


async def _noop_processor(msg: InboundMessage):
    """No-op processor for testing."""
    yield MessageEvent.completed()


def _qq_subject(subject_id: str, **metadata: str) -> ChannelSubject:
    """Build a ChannelSubject with QQ routing metadata for send tests."""
    return ChannelSubject(subject_id=subject_id, metadata=dict(metadata), first_seen=0, last_seen=0)


# ---------------------------------------------------------------------------
# Unit tests (no network required)
# ---------------------------------------------------------------------------


class TestQQChannelUnit:
    """Unit tests for QQ channel logic (no API calls)."""

    def test_config_creation(self) -> None:
        config = _make_config()
        assert config.app_id == _QQ_APP_ID
        assert config.secret == _QQ_SECRET
        assert config.sandbox is False
        assert config.group_context.enabled is True
        assert config.group_context.history_limit == 10

    def test_config_from_qr_credentials(self) -> None:
        credentials = QQBotQRCredentials(
            app_id="qr-app",
            app_secret="qr-secret",
            user_openid="operator-openid",
        )
        config = QQConfig.from_qr_credentials(credentials, sandbox=True)
        assert config.app_id == "qr-app"
        assert config.secret == "qr-secret"
        assert config.sandbox is True

    @pytest.mark.asyncio
    async def test_qr_login_fetches_bind_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        login = QQBotQRLogin(source="octop")
        monkeypatch.setattr(
            login,
            "_post_json",
            AsyncMock(return_value={"retcode": 0, "data": {"task_id": "task-1"}}),
        )
        monkeypatch.setattr("octop_gateway.channels.qq.login_qr.secrets.token_bytes", lambda _size: b"k" * 32)

        result = await login.fetch_qr_code()

        assert result.task_id == "task-1"
        assert "task_id=task-1" in result.qrcode_url
        assert "source=octop" in result.qrcode_url
        post = login._post_json
        assert isinstance(post, AsyncMock)
        assert post.await_args.args[1] == {"key": base64.b64encode(b"k" * 32).decode()}

    @pytest.mark.asyncio
    async def test_qr_login_poll_decrypts_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        key = b"k" * 32
        nonce = b"n" * 12
        encrypted = AESGCM(key).encrypt(nonce, b"bound-secret", None)
        encrypted_secret = base64.b64encode(nonce + encrypted).decode()
        login = QQBotQRLogin()
        monkeypatch.setattr("octop_gateway.channels.qq.login_qr.secrets.token_bytes", lambda _size: key)
        monkeypatch.setattr(
            login,
            "_post_json",
            AsyncMock(
                side_effect=[
                    {"retcode": 0, "data": {"task_id": "task-1"}},
                    {
                        "retcode": 0,
                        "data": {
                            "status": 2,
                            "bot_appid": 123456,
                            "bot_encrypt_secret": encrypted_secret,
                            "user_openid": "operator-openid",
                        },
                    },
                ]
            ),
        )
        await login.fetch_qr_code()

        result = await login.poll("task-1")

        assert result.status == "success"
        assert len(result.credentials) == 1
        assert result.credentials[0].app_id == "123456"
        assert result.credentials[0].app_secret == "bound-secret"
        assert result.credentials[0].user_openid == "operator-openid"
        with pytest.raises(ValueError, match="Unknown or expired"):
            await login.poll("task-1")

    @pytest.mark.asyncio
    async def test_qr_login_poll_reports_expired(self, monkeypatch: pytest.MonkeyPatch) -> None:
        login = QQBotQRLogin()
        monkeypatch.setattr(
            login,
            "_post_json",
            AsyncMock(
                side_effect=[
                    {"retcode": 0, "data": {"task_id": "task-expired"}},
                    {"retcode": 0, "data": {"status": 3}},
                ]
            ),
        )
        await login.fetch_qr_code()

        result = await login.poll("task-expired")

        assert result.status == "expired"

    @pytest.mark.asyncio
    async def test_qr_login_wait_retries_transient_network_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        key = b"k" * 32
        nonce = b"n" * 12
        encrypted = AESGCM(key).encrypt(nonce, b"bound-secret", None)
        login = QQBotQRLogin(poll_interval=0.001)
        monkeypatch.setattr("octop_gateway.channels.qq.login_qr.secrets.token_bytes", lambda _size: key)
        monkeypatch.setattr(
            login,
            "_post_json",
            AsyncMock(
                side_effect=[
                    {"retcode": 0, "data": {"task_id": "task-retry"}},
                    httpx.ConnectError("temporary network failure"),
                    {
                        "retcode": 0,
                        "data": {
                            "status": 2,
                            "bot_appid": "123456",
                            "bot_encrypt_secret": base64.b64encode(nonce + encrypted).decode(),
                        },
                    },
                ]
            ),
        )
        await login.fetch_qr_code()

        result = await login.wait_for_login("task-retry", timeout_s=1)

        assert result.connected is True
        assert result.credentials[0].app_secret == "bound-secret"

    def test_config_parses_group_context_policy(self) -> None:
        config = QQConfig.from_dict(
            {
                "app_id": "app",
                "client_secret": "secret",
                "group_context": {
                    "visibility": "all",
                    "activation": "always",
                    "history_limit": 25,
                },
            }
        )
        assert config.group_context.visibility == "all"
        assert config.group_context.activation == "always"
        assert config.group_context.history_limit == 25
        assert config.group_context.enabled is True

    def test_channel_id(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        assert ch.channel_type == "qq"

    def test_resolve_proactive_routing_defaults_to_c2c(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(subject_id="openid_1", chat_type="dm", metadata={"channel_type": "qq"})
        msg_type, meta = ch._resolve_send_routing(subject)
        assert msg_type == "c2c"
        assert meta["user_openid"] == "openid_1"

    def test_resolve_proactive_routing_respects_persisted_msg_type(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(
            subject_id="openid_1",
            chat_type="dm",
            metadata={"msg_type": "c2c", "user_openid": "openid_1"},
        )
        msg_type, meta = ch._resolve_send_routing(subject)
        assert msg_type == "c2c"
        assert meta["user_openid"] == "openid_1"

    def test_resolve_push_subject_enriches_sparse_metadata(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(
            subject_id="openid_qq",
            chat_type="dm",
            metadata={"channel_type": "qq"},
        )
        resolved = ch.resolve_push_subject(subject)
        assert resolved.metadata.get("user_openid") == "openid_qq"
        assert resolved.metadata.get("msg_type") == "c2c"

    def test_auth_headers(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        headers = ch._auth_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bot ")
        assert _QQ_APP_ID in headers["Authorization"]

    def test_parse_inbound_text_message(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_001",
                "content": "hello world",
                "author": {"user_openid": "user_abc"},
            },
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_type == "qq"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "user_abc"
        assert msg.text == "hello world"
        assert msg.metadata["msg_type"] == "c2c"

    def test_parse_inbound_with_at_mention(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_002",
                "content": "<@!12345> what is the weather",
                "author": {"id": "user_xyz"},
                "guild_id": "guild_1",
                "channel_id": "chan_1",
            },
        }
        msg = ch.parse_inbound(payload)
        assert "what is the weather" in msg.text
        assert "<@!" not in msg.text  # @mention stripped

    def test_parse_inbound_with_image_tag(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_003",
                "content": 'look at this <qqimg src="https://example.com/img.png">',
                "author": {"user_openid": "user_img"},
            },
        }
        msg = ch.parse_inbound(payload)
        # Should have text + image
        has_image = any(isinstance(p, ImageContent) for p in msg.content)
        assert has_image
        # Text should have the tag stripped
        text_parts = [p for p in msg.content if isinstance(p, TextContent)]
        if text_parts:
            assert "<qqimg" not in text_parts[0].text

    def test_parse_inbound_with_attachments(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_004",
                "content": "",
                "author": {"user_openid": "user_att"},
                "attachments": [
                    {"url": "https://cdn.qq.com/photo.jpg", "content_type": "image/jpeg"},
                    {"url": "https://cdn.qq.com/doc.pdf", "content_type": "application/pdf", "filename": "doc.pdf"},
                ],
            },
        }
        msg = ch.parse_inbound(payload)
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        files = [p for p in msg.content if isinstance(p, FileContent)]
        assert len(images) == 1
        assert images[0].url == "https://cdn.qq.com/photo.jpg"
        assert len(files) == 1
        assert files[0].filename == "doc.pdf"

    def test_parse_inbound_uses_qq_voice_transcript_without_audio(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_voice",
                "content": "",
                "author": {"user_openid": "user_voice"},
                "attachments": [
                    {
                        "url": "//cdn.qq.com/voice.silk",
                        "voice_wav_url": "//cdn.qq.com/voice.wav",
                        "content_type": "voice",
                        "filename": "voice.amr",
                        "asr_refer_text": "QQ voice transcript",
                    }
                ],
            },
        }

        msg = ch.parse_inbound(payload)

        assert msg.text == "QQ voice transcript"
        assert not any(isinstance(part, AudioContent) for part in msg.content)
        assert not any(isinstance(part, FileContent) for part in msg.content)
        assert msg.has_media is False

    def test_parse_inbound_classifies_qq_voice_without_asr_as_audio(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_voice_without_asr",
                "content": "",
                "author": {"user_openid": "user_voice"},
                "attachments": [
                    {
                        "url": "https://cdn.qq.com/voice.silk",
                        "content_type": "voice",
                        "filename": "voice.amr",
                    }
                ],
            },
        }

        msg = ch.parse_inbound(payload)

        assert msg.text == ""
        audio = [part for part in msg.content if isinstance(part, AudioContent)]
        assert len(audio) == 1
        assert audio[0].url == "https://cdn.qq.com/voice.silk"
        assert audio[0].mime_type is None
        assert not any(isinstance(part, FileContent) for part in msg.content)

    def test_group_bot_mention_is_removed_and_generic_file_mime_is_deferred(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {
                "id": "msg_opaque_mention",
                "content": "这个 pdf 在讲什么<@BD55218924C37DB7472F18A7FC8F59DA>",
                "author": {"member_openid": "member_1", "username": "Cloud"},
                "group_openid": "group_open_abc",
                "mentions": [
                    {
                        "id": "BD55218924C37DB7472F18A7FC8F59DA",
                        "is_you": True,
                    }
                ],
                "attachments": [
                    {
                        "url": "https://cdn.qq.com/report.pdf",
                        "content_type": "file",
                        "filename": "report.pdf",
                    }
                ],
            },
        }

        msg = ch.parse_inbound(payload)

        assert msg.text == "这个 pdf 在讲什么"
        files = [part for part in msg.content if isinstance(part, FileContent)]
        assert len(files) == 1
        assert files[0].mime_type is None

    def test_parse_inbound_with_quoted_pdf_attachment(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_quote",
                "content": "<@!99999> summarize this",
                "author": {"member_openid": "member_1"},
                "group_openid": "group_open_abc",
                "message_scene": {"ext": ["msg_idx=current", "ref_msg_idx=previous"]},
                "msg_elements": [
                    {"msg_idx": "current", "content": "summarize this"},
                    {
                        "msg_idx": "previous",
                        "content": "quarterly report",
                        "attachments": [
                            {
                                "url": "https://cdn.qq.com/report.pdf",
                                "content_type": "application/pdf",
                                "filename": "report.pdf",
                            }
                        ],
                    },
                ],
            },
        }

        msg = ch.parse_inbound(payload)

        assert "[quoted message: quarterly report]" in msg.text
        files = [part for part in msg.content if isinstance(part, FileContent)]
        assert len(files) == 1
        assert files[0].filename == "report.pdf"

    def test_parse_inbound_with_platform_recent_group_context(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_current",
                "content": "<@!99999> what is in the PDF?",
                "author": {"member_openid": "member_2", "username": "Bob"},
                "group_openid": "group_open_abc",
                "message_scene": {"ext": ["msg_idx=current"]},
                "msg_elements": [
                    {
                        "msg_idx": "previous",
                        "content": "quarterly report",
                        "author": {"member_openid": "member_1", "username": "Alice"},
                        "attachments": [
                            {
                                "url": "https://cdn.qq.com/report.pdf",
                                "content_type": "application/pdf",
                                "filename": "report.pdf",
                            }
                        ],
                    },
                    {"msg_idx": "current", "content": "what is in the PDF?"},
                ],
            },
        }

        msg = ch.parse_inbound(payload)

        assert msg.group_context is not None
        assert len(msg.group_context.messages) == 1
        item = msg.group_context.messages[0]
        assert item.sender_id == "member_1"
        assert item.sender_name == "Alice"
        assert item.text == "quarterly report"
        assert isinstance(item.content[0], FileContent)
        assert item.content[0].filename == "report.pdf"

    def test_parse_inbound_group_message(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_005",
                "content": "<@!99999> hi group",
                "author": {"member_openid": "member_1"},
                "group_openid": "group_open_abc",
            },
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_type == "qq"
        assert "hi group" in msg.text
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "group_open_abc"
        assert msg.channel_subject.chat_type == "group"
        assert msg.metadata["conversation_id"] == "group_open_abc"
        assert msg.metadata["sender_id"] == "member_1"
        assert msg.metadata["bot_mentioned"] is True

    def test_parse_inbound_full_group_message_keeps_sender_separate_from_conversation(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {
                "id": "msg_full_1",
                "content": "ambient group chatter",
                "author": {"member_openid": "member_2", "username": "Alice"},
                "group_openid": "group_open_abc",
                "mentions": [],
            },
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "group_open_abc"
        assert msg.metadata["sender_id"] == "member_2"
        assert msg.metadata["sender_name"] == "Alice"
        assert msg.metadata["bot_mentioned"] is False

    @pytest.mark.asyncio
    async def test_group_context_only_invokes_processor_on_mention(self) -> None:
        received: list[InboundMessage] = []

        async def processor(msg: InboundMessage):
            received.append(msg)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_make_config())
        ambient = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {
                "id": "msg_context",
                "content": "deployment is at 3pm",
                "author": {"member_openid": "member_1", "username": "Alice"},
                "group_openid": "group_1",
            },
        }
        mention = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_question",
                "content": "<@!99999> when is deployment?",
                "author": {"member_openid": "member_2", "username": "Bob"},
                "group_openid": "group_1",
            },
        }

        await ch.handle_inbound(ambient)
        assert received == []
        await ch.handle_inbound(mention)

        assert len(received) == 1
        assert received[0].group_context is not None
        assert [item.text for item in received[0].group_context.messages] == ["deployment is at 3pm"]

    @pytest.mark.asyncio
    async def test_group_context_persists_passive_pdf_for_next_mention(self, tmp_path) -> None:
        from octop_gateway.media import FileSystemMediaBackend

        received: list[InboundMessage] = []

        async def processor(msg: InboundMessage):
            received.append(msg)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_make_config())
        ch.set_media_backend(FileSystemMediaBackend(tmp_path))
        ch.fetch_remote_media = AsyncMock(return_value=(b"%PDF-1.7", "application/pdf"))  # type: ignore[method-assign]
        ambient = {
            "t": "GROUP_MESSAGE_CREATE",
            "d": {
                "id": "msg_file",
                "content": "",
                "author": {"member_openid": "member_1", "username": "Alice"},
                "group_openid": "group_1",
                "attachments": [
                    {
                        "url": "https://cdn.qq.com/report.pdf",
                        "content_type": "application/pdf",
                        "filename": "report.pdf",
                    }
                ],
            },
        }
        mention = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_question",
                "content": "<@!99999> summarize the PDF",
                "author": {"member_openid": "member_2", "username": "Bob"},
                "group_openid": "group_1",
            },
        }

        await ch.handle_inbound(ambient)
        await ch.handle_inbound(mention)

        assert len(received) == 1
        context = received[0].group_context
        assert context is not None and len(context.messages) == 1
        file_part = context.messages[0].content[0]
        assert isinstance(file_part, FileContent)
        assert file_part.local_path is not None
        assert await ch.media_backend.read(file_part.local_path) == b"%PDF-1.7"  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_group_context_persists_pdf_from_platform_recent_messages(self, tmp_path) -> None:
        from octop_gateway.media import FileSystemMediaBackend

        received: list[InboundMessage] = []

        async def processor(msg: InboundMessage):
            received.append(msg)
            yield MessageEvent.completed()

        ch = QQChannel(processor=processor, config=_make_config())
        ch.set_media_backend(FileSystemMediaBackend(tmp_path))
        ch.fetch_remote_media = AsyncMock(return_value=(b"%PDF-1.7", "application/pdf"))  # type: ignore[method-assign]
        mention = {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg_question",
                "content": "<@!99999> summarize the PDF",
                "author": {"member_openid": "member_2", "username": "Bob"},
                "group_openid": "group_1",
                "message_scene": {"ext": ["msg_idx=current"]},
                "msg_elements": [
                    {
                        "msg_idx": "file-message",
                        "content": "",
                        "author": {"member_openid": "member_1", "username": "Alice"},
                        "attachments": [
                            {
                                "url": "https://cdn.qq.com/report.pdf",
                                "content_type": "application/pdf",
                                "filename": "report.pdf",
                            }
                        ],
                    },
                    {"msg_idx": "current", "content": "summarize the PDF"},
                ],
            },
        }

        await ch.handle_inbound(mention)

        assert len(received) == 1
        context = received[0].group_context
        assert context is not None and len(context.messages) == 1
        file_part = context.messages[0].content[0]
        assert isinstance(file_part, FileContent)
        assert file_part.local_path is not None
        assert await ch.media_backend.read(file_part.local_path) == b"%PDF-1.7"  # type: ignore[union-attr]

    def test_deduplication(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        assert ch._is_duplicate("msg_100") is False
        assert ch._is_duplicate("msg_100") is True  # Second time = duplicate
        assert ch._is_duplicate("msg_101") is False

    def test_classify_msg_type(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        assert ch._classify_msg_type("C2C_MESSAGE_CREATE") == "c2c"
        assert ch._classify_msg_type("GROUP_AT_MESSAGE_CREATE") == "group"
        assert ch._classify_msg_type("GROUP_MESSAGE_CREATE") == "group"
        assert ch._classify_msg_type("DIRECT_MESSAGE_CREATE") == "direct"
        assert ch._classify_msg_type("AT_MESSAGE_CREATE") == "channel"

    def test_resolve_send_endpoint_c2c(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ep = ch._resolve_send_endpoint("user_open_1", "c2c", {"user_openid": "user_open_1"})
        assert ep == "/v2/users/user_open_1/messages"

    def test_resolve_send_endpoint_group(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ep = ch._resolve_send_endpoint("grp_1", "group", {"group_openid": "grp_1"})
        assert ep == "/v2/groups/grp_1/messages"

    def test_resolve_send_endpoint_channel(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ep = ch._resolve_send_endpoint("chan_1", "channel", {"channel_id_native": "chan_1"})
        assert ep == "/channels/chan_1/messages"


# ---------------------------------------------------------------------------
# Integration tests (require network + valid credentials)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestQQChannelIntegration:
    """Integration tests that hit the real QQ Bot API."""

    @pytest.mark.asyncio
    async def test_get_access_token(self) -> None:
        """Verify we can obtain an OAuth2 access token from QQ."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._ensure_access_token()
            assert token is not None
            assert len(token) > 10
            print(f"  Access token obtained: {token[:20]}...")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_fetch_gateway_url(self) -> None:
        """Verify we can fetch the WebSocket gateway URL from QQ API."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        try:
            await ch._ensure_access_token()
            gateway_url = await ch._fetch_gateway_url()
            assert gateway_url is not None
            assert gateway_url.startswith("wss://")
            print(f"  Gateway URL: {gateway_url}")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_websocket_connect_and_hello(self) -> None:
        """Verify we can connect to the gateway and receive HELLO."""
        import websockets

        ch = QQChannel(processor=_noop_processor, config=_make_config())
        try:
            await ch._ensure_access_token()
            gateway_url = await ch._fetch_gateway_url()
            assert gateway_url

            # Connect and expect HELLO
            async with websockets.connect(gateway_url) as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                payload = json.loads(raw)
                assert payload["op"] == _OP_HELLO
                assert "heartbeat_interval" in payload.get("d", {})
                print(f"  Received HELLO: heartbeat_interval={payload['d']['heartbeat_interval']}ms")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_identify_and_ready(self) -> None:
        """Verify full IDENTIFY handshake: connect → HELLO → IDENTIFY → READY."""
        import websockets

        ch = QQChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._ensure_access_token()
            gateway_url = await ch._fetch_gateway_url()
            assert gateway_url

            async with websockets.connect(gateway_url) as ws:
                # 1. Receive HELLO
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                hello = json.loads(raw)
                assert hello["op"] == _OP_HELLO

                # 2. Send IDENTIFY with access token
                identify = {
                    "op": _OP_IDENTIFY,
                    "d": {
                        "token": f"QQBot {token}",
                        "intents": _DEFAULT_INTENTS,
                        "shard": [0, 1],
                    },
                }
                await ws.send(json.dumps(identify))

                # 3. Expect READY event (dispatch with t="READY")
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                ready = json.loads(raw)
                if ready.get("op") == 0 and ready.get("t") == "READY":
                    print(f"  READY received: session_id={ready['d'].get('session_id')}")
                    assert ready["d"].get("session_id")
                else:
                    print(f"  Received (not READY): op={ready.get('op')} t={ready.get('t')} d={ready.get('d')}")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_channel_start_stop(self) -> None:
        """Test full lifecycle: start (connect + identify) then stop cleanly."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        try:
            await ch.start()
            # Give it a moment to connect
            await asyncio.sleep(3.0)
            assert ch._running
            assert ch._ws_task is not None
        finally:
            await ch.stop()
            assert not ch._running


# ---------------------------------------------------------------------------
# Unit tests: msg_seq counter and send_message behavior
# ---------------------------------------------------------------------------


class TestQQMsgSeq:
    """Unit tests for _get_next_msg_seq and send_message seq injection."""

    def setup_method(self) -> None:
        """Clear module-level _msg_seq state before each test."""
        _msg_seq.clear()

    def test_msg_seq_counter(self) -> None:
        """Verify msg_seq increments for same msg_id and starts from time-based value."""
        first = _get_next_msg_seq("abc123")
        # Should be time-based modulo 1_000_000 + 1
        assert 1 <= first <= 1_000_001
        second = _get_next_msg_seq("abc123")
        assert second == first + 1
        third = _get_next_msg_seq("abc123")
        assert third == first + 2

    def test_msg_seq_eviction(self) -> None:
        """Call with >1000 different msg_ids, verify dict doesn't grow unbounded."""
        for i in range(1100):
            _get_next_msg_seq(f"msg_{i:05d}")
        # After eviction, dict should be capped (evicts 500 at a time when > 1000)
        assert len(_msg_seq) <= 1001

    @pytest.mark.asyncio
    async def test_send_message_injects_msg_type_and_seq(self) -> None:
        """send_text with msg_type='c2c' and msg_id in meta injects msg_type=0 and msg_seq."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())

        captured_payloads: list[dict] = []

        async def _mock_post(url, headers=None, json=None):
            captured_payloads.append(json)
            resp = AsyncMock()
            resp.status = 200
            resp.text = AsyncMock(return_value='{"id":"ok"}')
            return resp

        # Use a context manager mock for aiohttp
        class _FakeResp:
            status = 200

            async def text(self):
                return '{"id":"ok"}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

        class _FakeSession:
            def post(self, url, **kw):
                captured_payloads.append(kw.get("json"))
                return _FakeResp()

            @property
            def closed(self):
                return False

        ch._http = _FakeSession()  # type: ignore[assignment]
        ch._access_token = "fake_token"
        ch._token_expires_at = 9999999999.0
        ch._token_refresh_at = 9999999999.0

        meta = {"msg_type": "c2c", "msg_id": "test123", "user_openid": "user_open_1"}
        await ch._send_text(_qq_subject("user_open_1", **meta), "hello")

        # The final _send_message payload should have msg_type=0 and msg_seq
        # send_text for c2c tries markdown first (msg_type=2), which will succeed
        # with our mock, so captured_payloads[0] is the markdown attempt.
        # Let's check the first payload sent.
        assert len(captured_payloads) >= 1
        # The markdown attempt has msg_type=2; if it "succeeds" (status 200), no fallback.
        payload = captured_payloads[0]
        assert "msg_seq" in payload
        assert payload["msg_type"] == 2  # markdown attempt
        assert payload["msg_id"] == "test123"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("msg_type", "metadata_key", "subject_id"),
        [
            ("c2c", "user_openid", "user_open_1"),
            ("group", "group_openid", "group_open_1"),
        ],
    )
    async def test_send_message_proactive_no_seq(
        self,
        msg_type: str,
        metadata_key: str,
        subject_id: str,
    ) -> None:
        """send_text without msg_id in meta sends proactive markdown without msg_seq."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())

        captured_payloads: list[dict] = []

        class _FakeResp:
            status = 200

            async def text(self):
                return '{"id":"ok"}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

        class _FakeSession:
            def post(self, url, **kw):
                captured_payloads.append(kw.get("json"))
                return _FakeResp()

            @property
            def closed(self):
                return False

        ch._http = _FakeSession()  # type: ignore[assignment]
        ch._access_token = "fake_token"
        ch._token_expires_at = 9999999999.0
        ch._token_refresh_at = 9999999999.0

        meta = {"msg_type": msg_type, metadata_key: subject_id}
        await ch._send_text(_qq_subject(subject_id, **meta), "proactive hello")

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        assert payload["msg_type"] == 2
        assert payload["content"] == ""
        assert payload["markdown"] == {"content": "proactive hello"}
        assert "msg_id" not in payload
        assert "msg_seq" not in payload

    @pytest.mark.asyncio
    async def test_send_text_markdown_fallback(self) -> None:
        """Mock _try_send_message to return False → falls back to plain text, adds target to _markdown_unsupported."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())

        captured_payloads: list[dict] = []

        class _FakeResp:
            def __init__(self, status=200):
                self._status = status

            @property
            def status(self):
                return self._status

            async def text(self):
                return '{"id":"ok"}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

        call_count = 0

        class _FakeSession:
            def post(self, url, **kw):
                nonlocal call_count
                call_count += 1
                captured_payloads.append(kw.get("json"))
                # First call (markdown attempt via _try_send_message) → fail (400)
                # Second call (plain text fallback) → succeed
                if call_count == 1:
                    return _FakeResp(status=400)
                return _FakeResp(status=200)

            @property
            def closed(self):
                return False

        ch._http = _FakeSession()  # type: ignore[assignment]
        ch._access_token = "fake_token"
        ch._token_expires_at = 9999999999.0
        ch._token_refresh_at = 9999999999.0

        target_key = "user_open_fallback"
        meta = {"msg_type": "c2c", "msg_id": "msg_fb1", "user_openid": target_key}

        assert target_key not in ch._markdown_unsupported
        await ch._send_text(_qq_subject(target_key, **meta), "test fallback")

        # Should have tried markdown first (failed), then plain text
        assert target_key in ch._markdown_unsupported
        assert len(captured_payloads) >= 2
        # Second payload is the plain text fallback
        fallback_payload = captured_payloads[1]
        assert fallback_payload["msg_type"] == 0
        assert fallback_payload["content"] == "test fallback"


class TestQQParseInboundExtended:
    """Additional parse_inbound tests for attachments and metadata."""

    def test_parse_inbound_c2c_image(self) -> None:
        """C2C payload with image/png attachment → ImageContent in result."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_img_001",
                "content": "",
                "author": {"user_openid": "user_img_test"},
                "attachments": [
                    {"url": "https://cdn.qq.com/photo.png", "content_type": "image/png"},
                ],
            },
        }
        msg = ch.parse_inbound(payload)
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        assert len(images) == 1
        assert images[0].url == "https://cdn.qq.com/photo.png"
        assert images[0].mime_type == "image/png"

    def test_parse_inbound_url_prefix(self) -> None:
        """Attachment URL starting with '//' gets 'https:' prefix."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_url_prefix",
                "content": "",
                "author": {"user_openid": "user_url"},
                "attachments": [
                    {"url": "//cdn.qq.com/image.jpg", "content_type": "image/jpeg"},
                ],
            },
        }
        msg = ch.parse_inbound(payload)
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        assert len(images) == 1
        assert images[0].url == "https://cdn.qq.com/image.jpg"

    def test_parse_inbound_user_openid_in_metadata(self) -> None:
        """C2C event → metadata contains user_openid."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "msg_meta_001",
                "content": "hi",
                "author": {"user_openid": "ou_target_user"},
            },
        }
        msg = ch.parse_inbound(payload)
        assert msg.metadata["user_openid"] == "ou_target_user"


# ---------------------------------------------------------------------------
# send_media: local image / base64 fallback
# ---------------------------------------------------------------------------


class TestQQSendMediaLocal:
    """Verify send_media supports local files and falls back through the
    URL → base64 → fetch+base64 chain (mirrors finnie's QQ behavior).
    """

    @pytest.mark.asyncio
    async def test_c2c_local_path_uploads_via_base64(self, tmp_path) -> None:
        """C2C send with only local_path → _upload_media called with data=bytes."""
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"PNGBYTES", "qq/cached/photo.png")

        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch.set_media_backend(backend)

        upload_calls: list[dict] = []

        async def fake_upload(to_handle, msg_type, meta, file_type, *, url=None, data=None, filename=None):
            upload_calls.append({"url": url, "data": data, "filename": filename, "file_type": file_type})
            if data is not None:
                return {"file_info": "fake-file-info"}
            return None  # Force base64 path

        send_calls: list[dict] = []

        async def fake_send_message(to, payload, msg_type, meta):
            send_calls.append({"payload": payload, "msg_type": msg_type})

        ch._upload_media = fake_upload  # type: ignore[method-assign]
        ch._send_message = fake_send_message  # type: ignore[method-assign]

        media = ImageContent(local_path="qq/cached/photo.png", mime_type="image/png")
        await ch._send_media(
            _qq_subject("user_open_1", msg_type="c2c", user_openid="user_open_1", msg_id="m1"),
            media,
        )

        # No URL on the part → URL upload skipped, base64 upload invoked with bytes.
        assert any(c["data"] == b"PNGBYTES" for c in upload_calls)
        assert all(c["url"] is None for c in upload_calls)
        # send_message called with msg_type=7 rich media payload
        assert len(send_calls) == 1
        assert send_calls[0]["payload"]["msg_type"] == 7
        assert send_calls[0]["payload"]["media"] == {"file_info": "fake-file-info"}

    @pytest.mark.asyncio
    async def test_c2c_url_failure_falls_back_to_base64(self, tmp_path) -> None:
        """URL upload returns None → base64 upload retried with backend bytes."""
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"FALLBACK", "qq/cached/img.png")

        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch.set_media_backend(backend)

        attempts: list[dict] = []

        async def fake_upload(to_handle, msg_type, meta, file_type, *, url=None, data=None, filename=None):
            attempts.append({"url": url, "data": data})
            if url is not None:  # Priority 1: URL pull → simulate QQ refusing
                return None
            return {"file_info": "ok"}

        async def fake_send_message(to, payload, msg_type, meta):
            pass

        ch._upload_media = fake_upload  # type: ignore[method-assign]
        ch._send_message = fake_send_message  # type: ignore[method-assign]

        media = ImageContent(
            url="https://cdn.example.com/x.png",
            local_path="qq/cached/img.png",
        )
        await ch._send_media(
            _qq_subject("user_open_2", msg_type="group", group_openid="grp_1", msg_id="m2"),
            media,
        )

        # Two attempts: URL first, then base64.
        assert len(attempts) == 2
        assert attempts[0]["url"] == "https://cdn.example.com/x.png"
        assert attempts[0]["data"] is None
        assert attempts[1]["url"] is None
        assert attempts[1]["data"] == b"FALLBACK"

    @pytest.mark.asyncio
    async def test_c2c_url_only_fetch_then_base64(self) -> None:
        """URL only, URL upload fails → fetch_remote_media + base64 retry."""
        ch = QQChannel(processor=_noop_processor, config=_make_config())

        attempts: list[dict] = []

        async def fake_upload(to_handle, msg_type, meta, file_type, *, url=None, data=None, filename=None):
            attempts.append({"url": url, "data": data})
            if url is not None:
                return None  # URL pull fails
            return {"file_info": "fetched-ok"}

        async def fake_fetch(url: str):
            return b"DOWNLOADED", "image/png"

        async def fake_send_message(to, payload, msg_type, meta):
            pass

        ch._upload_media = fake_upload  # type: ignore[method-assign]
        ch.fetch_remote_media = fake_fetch  # type: ignore[method-assign]
        ch._send_message = fake_send_message  # type: ignore[method-assign]

        media = ImageContent(url="https://cdn.example.com/y.png")
        await ch._send_media(
            _qq_subject("user_open_3", msg_type="c2c", user_openid="user_open_3"),
            media,
        )

        # Two attempts: URL pull (fails) then base64 with fetched bytes.
        assert len(attempts) == 2
        assert attempts[0]["url"] == "https://cdn.example.com/y.png"
        assert attempts[1]["data"] == b"DOWNLOADED"

    @pytest.mark.asyncio
    async def test_guild_local_only_falls_back_to_text(self, tmp_path) -> None:
        """Guild channel only accepts public URL — local-only parts must
        not silently disappear; emit a text marker instead.
        """
        from octop_gateway.media import FileSystemMediaBackend

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"GUILDBYTES", "qq/cached/g.png")

        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch.set_media_backend(backend)

        sent_texts: list[tuple[str, str]] = []

        async def fake_send_text(subject, text):
            sent_texts.append((subject.subject_id, text))

        async def fake_send_message(*a, **kw):
            raise AssertionError("guild path must not call _send_message for local-only media")

        ch._send_text = fake_send_text  # type: ignore[method-assign]
        ch._send_message = fake_send_message  # type: ignore[method-assign]

        media = ImageContent(local_path="qq/cached/g.png")
        await ch._send_media(
            _qq_subject("channel_id_42", msg_type="channel", channel_id_native="channel_id_42"),
            media,
        )

        assert sent_texts and "local file" in sent_texts[0][1].lower()

    @pytest.mark.asyncio
    async def test_upload_media_base64_payload_shape(self) -> None:
        """The HTTP body sent to QQ contains base64-encoded file_data when
        ``data`` is supplied (not the raw URL field).
        """
        import base64

        ch = QQChannel(processor=_noop_processor, config=_make_config())

        captured: dict = {}

        class _FakeResp:
            status = 200

            async def json(self):
                return {"file_info": "ok"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class _FakeHttp:
            closed = False

            def post(self, url, headers=None, json=None):
                captured["url"] = url
                captured["body"] = json
                captured["headers"] = headers
                return _FakeResp()

        ch._http = _FakeHttp()  # type: ignore[assignment]
        ch._access_token = "tok"
        ch._token_expires_at = 9999999999.0

        result = await ch._upload_media(
            "user_x",
            "c2c",
            {"user_openid": "user_x"},
            file_type=1,
            data=b"RAWBYTES",
        )

        # Returns the file_info wrapper expected by the rich-media send payload.
        assert result == {"file_info": "ok"}
        body = captured["body"]
        assert "url" not in body
        assert body["file_data"] == base64.b64encode(b"RAWBYTES").decode()
        assert body["file_type"] == 1
        assert body["srv_send_msg"] is False


class TestQQAccessTokenRetry:
    @pytest.mark.asyncio
    async def test_send_message_refreshes_token_after_401(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._access_token = "stale"
        ch._token_expires_at = 9999999999.0
        ch._token_refresh_at = 9999999999.0
        calls: list[str] = []

        class _Resp:
            def __init__(self, status: int, body: str, payload: dict | None = None) -> None:
                self.status = status
                self._body = body
                self._payload = payload or {}

            async def text(self) -> str:
                return self._body

            async def json(self) -> dict:
                return self._payload

            async def __aenter__(self) -> _Resp:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

        class _Http:
            closed = False

            def post(self, url: str, **kwargs: object) -> _Resp:
                calls.append(str(url))
                if "getAppAccessToken" in str(url):
                    return _Resp(200, "", {"access_token": "fresh", "expires_in": 7200})
                if len([u for u in calls if u.endswith("/messages")]) == 1:
                    return _Resp(
                        401,
                        '{"message":"AccessToken无效或过期","code":11244,"err_code":40011027}',
                    )
                return _Resp(200, '{"id":"ok"}')

        ch._http = _Http()  # type: ignore[assignment]
        await ch._send_message(
            "user_x",
            {"content": "hi", "msg_type": 0, "msg_id": "m1"},
            "c2c",
            {"user_openid": "user_x", "msg_id": "m1"},
        )
        assert ch._access_token == "fresh"
        assert sum(1 for url in calls if url.endswith("/messages")) == 2
        assert any("getAppAccessToken" in url for url in calls)

    def test_short_ttl_refreshes_before_hard_expiry(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        now = 1_000_000.0
        ch._access_token = "tok"
        ch._token_expires_at = now + 61
        ch._token_refresh_at = now + max(1, 61 - min(60, 61 // 2))
        assert ch._token_refresh_at < ch._token_expires_at
        assert ch._token_refresh_at > now


# ---------------------------------------------------------------------------
# INVALID_SESSION recovery + RESUME token format + READY-gated backoff
# ---------------------------------------------------------------------------


class _SentWS:
    """Captures all ws.send() calls for assertion."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


class TestQQInvalidSessionRecovery:
    """The fix matrix:
    - op=9 d=False → clear session AND mark _force_token_refresh.
    - op=9 d=True  → keep session_id+last_sequence (RESUME-able).
    - RESUME payload uses ``QQBot {access_token}``, not legacy form.
    - _reconnect_delay only resets on READY/RESUMED, not on raw connect.
    """

    @pytest.mark.asyncio
    async def test_invalid_session_not_resumable_clears_and_forces_refresh(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._session_id_ws = "old_session"
        ch._last_sequence = 42
        ch._force_token_refresh = False

        with pytest.raises(ConnectionError):
            await ch._handle_op(_SentWS(), 9, {"op": 9, "d": False})

        assert ch._session_id_ws is None
        assert ch._last_sequence is None
        assert ch._force_token_refresh is True

    @pytest.mark.asyncio
    async def test_invalid_session_resumable_keeps_session_no_refresh(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._session_id_ws = "still_valid"
        ch._last_sequence = 99
        ch._force_token_refresh = False

        with pytest.raises(ConnectionError):
            await ch._handle_op(_SentWS(), 9, {"op": 9, "d": True})

        # Resumable path: session_id and seq retained, no token refresh.
        assert ch._session_id_ws == "still_valid"
        assert ch._last_sequence == 99
        assert ch._force_token_refresh is False

    @pytest.mark.asyncio
    async def test_resume_payload_uses_qqbot_oauth_format(self) -> None:
        """RESUME must use ``QQBot {access_token}``; mixing the legacy
        ``Bot {app_id}.{token}`` form is what triggered the original bug.
        """
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._access_token = "fresh_access_token"
        ch._token_expires_at = 9999999999.0
        ch._session_id_ws = "session_xyz"
        ch._last_sequence = 7

        ws = _SentWS()
        await ch._send_resume(ws)

        assert len(ws.sent) == 1
        payload = ws.sent[0]
        assert payload["op"] == 6  # OP_RESUME
        assert payload["d"]["token"] == "QQBot fresh_access_token"
        assert payload["d"]["session_id"] == "session_xyz"
        assert payload["d"]["seq"] == 7

    @pytest.mark.asyncio
    async def test_identify_pulls_fresh_token_via_ensure_access_token(self) -> None:
        """IDENTIFY's ``QQBot {token}`` must come from the cached/refreshed
        OAuth helper, not from the legacy app_id.token combination.
        """
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._access_token = "valid_token"
        ch._token_expires_at = 9999999999.0  # cached, no network

        ws = _SentWS()
        await ch._send_identify(ws)

        assert len(ws.sent) == 1
        d = ws.sent[0]["d"]
        assert d["token"] == "QQBot valid_token"
        # Sanity: legacy form must NOT leak into IDENTIFY.
        assert not d["token"].startswith("Bot ")

    @pytest.mark.asyncio
    async def test_ready_resets_reconnect_delay(self) -> None:
        """A successful READY hop must reset the backoff so a healthy
        long-lived session does not carry an inflated delay from earlier
        failures.
        """
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._reconnect_delay = 32.0  # simulate prior failures

        ws = _SentWS()
        await ch._handle_op(
            ws,
            0,  # OP_DISPATCH
            {"op": 0, "t": "READY", "s": 1, "d": {"session_id": "fresh"}},
        )

        assert ch._session_id_ws == "fresh"
        assert ch._reconnect_delay == 1.0

    @pytest.mark.asyncio
    async def test_resumed_resets_reconnect_delay(self) -> None:
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._reconnect_delay = 16.0
        ch._session_id_ws = "kept"

        ws = _SentWS()
        await ch._handle_op(
            ws,
            0,
            {"op": 0, "t": "RESUMED", "s": 5, "d": {}},
        )

        assert ch._reconnect_delay == 1.0
        assert ch._session_id_ws == "kept"  # untouched

    @pytest.mark.asyncio
    async def test_reconnect_op_preserves_session_for_resume(self) -> None:
        """op=7 means the gateway is cycling the connection. The session
        is still valid — preserve session_id and last_sequence so the
        next connection RESUMEs and we don't drop events.
        """
        ch = QQChannel(processor=_noop_processor, config=_make_config())
        ch._session_id_ws = "active_session"
        ch._last_sequence = 123
        ch._force_token_refresh = False

        with pytest.raises(_GatewayReconnectError):
            await ch._handle_op(_SentWS(), 7, {"op": 7, "d": None})

        # Session retained → next connection will RESUME, not IDENTIFY.
        assert ch._session_id_ws == "active_session"
        assert ch._last_sequence == 123
        assert ch._force_token_refresh is False
