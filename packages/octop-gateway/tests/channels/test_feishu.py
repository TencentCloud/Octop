"""Integration tests for Feishu channel.

Tests the full Feishu API lifecycle including:
- Tenant access token retrieval
- Bot info query
- Message sending (to self/test chat)
- Image upload
- Interactive card sending

Run with: pytest tests/channels/test_feishu.py -m integration
Requires: FEISHU_APP_ID and FEISHU_APP_SECRET environment variables
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from octop_gateway.channels.feishu import FeishuChannel, FeishuConfig
from octop_gateway.constraints import ChannelConstraints
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

_FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_test_app_id")
_FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "test_feishu_app_secret")


def _make_config() -> FeishuConfig:
    return FeishuConfig(
        app_id=_FEISHU_APP_ID,
        app_secret=_FEISHU_APP_SECRET,
    )


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


# ---------------------------------------------------------------------------
# Unit tests (no network)
# ---------------------------------------------------------------------------


class TestFeishuChannelUnit:
    """Unit tests for Feishu channel logic."""

    def test_channel_id(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        assert ch.channel_type == "feishu"

    def test_config_creation(self) -> None:
        config = _make_config()
        assert config.app_id == _FEISHU_APP_ID
        assert config.app_secret == _FEISHU_APP_SECRET

    def test_parse_inbound_text(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "msg_001",
            "message_type": "text",
            "content": '{"text":"hello feishu"}',
            "chat_id": "oc_chat001",
            "chat_type": "p2p",
            "sender": {"sender_id": "ou_abc123", "sender_type": "user"},
            "create_time": "1716700000000",
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_type == "feishu"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "ou_abc123"
        assert msg.channel_subject.chat_type == "direct"
        assert msg.metadata["bot_mentioned"] is True
        assert "hello feishu" in msg.text

    def test_parse_inbound_sticker(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "msg_sticker",
            "message_type": "sticker",
            "content": '{"file_key":"file_v2_sticker_abc"}',
            "chat_id": "oc_chat_sticker",
            "chat_type": "p2p",
            "sender": {"sender_id": "ou_sticker_user", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        assert "[Sticker: file_v2_sticker_abc]" in msg.text
        assert msg.has_media is False

    def test_parse_inbound_post_with_emotion_and_image(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "om_post_1",
            "message_type": "post",
            "content": (
                '{"title":"","content":['
                '[{"tag":"emotion","emoji_type":"SMILE"},{"tag":"text","text":" hi"}],'
                '[{"tag":"img","image_key":"img_v2_post"}]'
                "]}"
            ),
            "chat_id": "oc_post",
            "chat_type": "p2p",
            "sender": {"sender_id": "ou_post_user", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        assert "[SMILE]" in msg.text
        assert "hi" in msg.text
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        assert len(images) == 1
        assert images[0].url is not None
        assert "img_v2_post" in images[0].url

    def test_parse_inbound_group_mention_sets_bot_mentioned(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._bot_open_id = "ou_bot_open"
        payload = {
            "message_id": "om_mention",
            "message_type": "text",
            "content": '{"text":"@_user_1 please help\\nsecond line"}',
            "chat_id": "oc_group",
            "chat_type": "group",
            "mentions": [{"key": "@_user_1", "open_id": "ou_bot_open", "name": "Bot"}],
            "sender": {"sender_id": "ou_human", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_subject is not None
        assert msg.channel_subject.chat_type == "group"
        assert msg.metadata["bot_mentioned"] is True
        assert msg.metadata["sender_id"] == "ou_human"
        assert "@_user_1" not in msg.text
        assert "please help" in msg.text
        assert "\n" in msg.text
        assert "second line" in msg.text

    def test_parse_inbound_group_without_mention(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._bot_open_id = "ou_bot_open"
        payload = {
            "message_id": "om_passive",
            "message_type": "text",
            "content": '{"text":"side chat"}',
            "chat_id": "oc_group",
            "chat_type": "group",
            "mentions": [],
            "sender": {"sender_id": "ou_human", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        assert msg.metadata["bot_mentioned"] is False

    def test_parse_inbound_image(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "msg_002",
            "message_type": "image",
            "content": '{"image_key":"img_v2_abc123"}',
            "chat_id": "oc_chat002",
            "chat_type": "p2p",
            "sender": {"sender_id": "ou_img_user", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        assert len(images) >= 1

    def test_parse_inbound_file(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "msg_004",
            "message_type": "file",
            "content": '{"file_key":"file_v2_xyz","file_name":"report.pdf"}',
            "chat_id": "oc_chat003",
            "chat_type": "p2p",
            "sender": {"sender_id": "ou_file_user", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        files = [p for p in msg.content if isinstance(p, FileContent)]
        assert len(files) >= 1

    def test_deduplication(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        assert ch._is_duplicate("msg_100") is False
        assert ch._is_duplicate("msg_100") is True
        assert ch._is_duplicate("msg_101") is False

    def test_parse_inbound_thread_message(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "om_thread_msg",
            "message_type": "text",
            "content": '{"text":"hi in topic"}',
            "chat_id": "oc_topic_chat",
            "chat_type": "group",
            "thread_id": "omt_topic_1",
            "sender": {"sender_id": "ou_topic_user", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_subject is not None
        # One session per topic, while replies still route through the chat.
        assert msg.channel_subject.subject_id == "omt_topic_1"
        assert msg.metadata["thread_id"] == "omt_topic_1"
        assert msg.metadata["to_handle"] == "oc_topic_chat"

    def test_parse_inbound_group_without_thread(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "message_id": "om_plain",
            "message_type": "text",
            "content": '{"text":"plain group"}',
            "chat_id": "oc_plain_chat",
            "chat_type": "group",
            "sender": {"sender_id": "ou_plain_user", "sender_type": "user"},
        }
        msg = ch.parse_inbound(payload)
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "oc_plain_chat"
        assert "thread_id" not in msg.metadata

    @pytest.mark.asyncio
    async def test_deliver_uses_reply_api_inside_thread(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        replies: list[tuple[str, str]] = []
        sends: list[str] = []

        async def _fake_reply(message_id: str, *, msg_type: str, content: str) -> dict[str, object]:
            replies.append((message_id, msg_type))
            return {"code": 0}

        async def _fake_send(**kwargs: object) -> dict[str, object]:
            sends.append(str(kwargs.get("receive_id")))
            return {"code": 0}

        ch._reply_message = _fake_reply  # type: ignore[method-assign]
        ch._send_message = _fake_send  # type: ignore[method-assign]

        subject = ChannelSubject(
            subject_id="omt_topic_1",
            metadata={
                "thread_id": "omt_topic_1",
                "message_id": "om_thread_msg",
                "chat_id": "oc_topic_chat",
                "chat_type": "group",
                "to_handle": "oc_topic_chat",
            },
        )
        await ch._send_text(subject, "hello")

        assert replies == [("om_thread_msg", "post")]
        assert sends == []

    @pytest.mark.asyncio
    async def test_deliver_falls_back_to_chat_send_when_reply_fails(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        sends: list[tuple[str, str]] = []

        async def _fake_reply(message_id: str, *, msg_type: str, content: str) -> dict[str, object]:
            return {"code": 230002, "msg": "message not found"}

        async def _fake_send(
            *,
            receive_id: str,
            receive_id_type: str,
            msg_type: str,
            content: str,
        ) -> dict[str, object]:
            sends.append((receive_id, receive_id_type))
            return {"code": 0}

        ch._reply_message = _fake_reply  # type: ignore[method-assign]
        ch._send_message = _fake_send  # type: ignore[method-assign]

        subject = ChannelSubject(
            subject_id="omt_topic_1",
            metadata={
                "thread_id": "omt_topic_1",
                "message_id": "om_expired",
                "chat_id": "oc_topic_chat",
                "chat_type": "group",
                "to_handle": "oc_topic_chat",
            },
        )
        await ch._send_text(subject, "hello")

        assert sends == [("oc_topic_chat", "chat_id")]

    def test_resolve_push_subject_keeps_chat_handle_for_thread_subject(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(
            subject_id="omt_topic_1",
            chat_type="group",
            metadata={"channel_type": "feishu", "chat_id": "oc_topic_chat"},
        )
        resolved = ch.resolve_push_subject(subject)
        assert resolved.metadata.get("to_handle") == "oc_topic_chat"

    def test_resolve_push_subject_enriches_sparse_metadata(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(
            subject_id="ou_abc123",
            chat_type="dm",
            metadata={"channel_type": "feishu"},
        )
        resolved = ch.resolve_push_subject(subject)
        assert resolved.metadata.get("chat_type") == "dm"
        assert resolved.metadata.get("to_handle") == "ou_abc123"


# ---------------------------------------------------------------------------
# Integration tests (require network + valid credentials)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFeishuChannelIntegration:
    """Integration tests that hit the real Feishu API."""

    @pytest.mark.asyncio
    async def test_get_tenant_access_token(self) -> None:
        """Verify we can obtain a tenant_access_token."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            assert token is not None
            assert len(token) > 10
            print(f"  Feishu token: {token[:20]}...")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_get_bot_info(self) -> None:
        """Verify bot identity via /bot/v3/info."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            http = await ch._ensure_http()
            headers = {"Authorization": f"Bearer {token}"}
            async with http.get("https://open.feishu.cn/open-apis/bot/v3/info", headers=headers) as resp:
                data = await resp.json()
                assert data.get("code") == 0
                bot = data.get("bot", {})
                print(f"  Bot name: {bot.get('app_name')}")
                print(f"  Bot open_id: {bot.get('open_id')}")
                assert bot.get("app_name")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_list_chats(self) -> None:
        """List bot's joined chats (groups)."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            http = await ch._ensure_http()
            headers = {"Authorization": f"Bearer {token}"}
            url = "https://open.feishu.cn/open-apis/im/v1/chats?page_size=10"
            async with http.get(url, headers=headers) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    items = data.get("data", {}).get("items", [])
                    print(f"  Bot joined {len(items)} chats:")
                    for item in items[:5]:
                        print(f"    - {item.get('name', 'unnamed')} (id={item.get('chat_id', '')[:20]})")
                else:
                    print(f"  List chats: code={data.get('code')} msg={data.get('msg')}")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_channel_start_stop(self) -> None:
        """Test lifecycle: token refresh works (WS start may require lark-oapi ws module)."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            # Just test token refresh (start() also tries WS which may not be available)
            token = await ch._refresh_token()
            assert token is not None
            assert ch._tenant_token is not None
            print(f"  Token acquired: {token[:20]}...")
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_send_text_to_bot_self(self) -> None:
        """Send a text message to the bot itself (useful for verifying send works).

        Note: This requires the bot to be able to message itself, which may not
        always work. We test the API call doesn't error.
        """
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            http = await ch._ensure_http()

            # Get bot's own open_id
            headers = {"Authorization": f"Bearer {token}"}
            async with http.get("https://open.feishu.cn/open-apis/bot/v3/info", headers=headers) as resp:
                data = await resp.json()
                bot_open_id = data.get("bot", {}).get("open_id")

            if not bot_open_id:
                pytest.skip("Cannot determine bot open_id")

            # Try sending (may fail if bot can't message itself, that's OK)
            headers["Content-Type"] = "application/json"
            send_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
            payload = {
                "receive_id": bot_open_id,
                "msg_type": "text",
                "content": '{"text":"Integration test message from octop-gateway"}',
            }
            async with http.post(send_url, json=payload, headers=headers) as resp:
                result = await resp.json()
                print(f"  Send result: code={result.get('code')} msg={result.get('msg')}")
                # Code 0 = success, other codes may be permission-related (acceptable)
        finally:
            await ch._close_http()


@pytest.mark.integration
class TestFeishuExtendedFeatures:
    """Test Feishu-specific extended features (cards, interactive, etc.).

    These test the platform-specific capabilities beyond the base interface.
    """

    @pytest.mark.asyncio
    async def test_send_card_message(self) -> None:
        """Test sending an interactive card (Feishu-specific feature)."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            http = await ch._ensure_http()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Get bot open_id
            async with http.get("https://open.feishu.cn/open-apis/bot/v3/info", headers=headers) as resp:
                data = await resp.json()
                bot_open_id = data.get("bot", {}).get("open_id")

            if not bot_open_id:
                pytest.skip("Cannot determine bot open_id")

            # Build interactive card
            card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "octop-gateway Test"},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "plain_text", "content": "This is a card message test."}},
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": "**Status**: ✅ Working"},
                    },
                ],
            }

            import json

            send_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
            payload = {
                "receive_id": bot_open_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            }
            async with http.post(send_url, json=payload, headers=headers) as resp:
                result = await resp.json()
                print(f"  Card send: code={result.get('code')} msg={result.get('msg')}")
                # Success or permission-denied both acceptable for test
        finally:
            await ch._close_http()

    @pytest.mark.asyncio
    async def test_feishu_api_capabilities(self) -> None:
        """Enumerate available Feishu API scopes (shows extended capabilities)."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        try:
            token = await ch._refresh_token()
            http = await ch._ensure_http()
            headers = {"Authorization": f"Bearer {token}"}

            # Check available scopes by testing various endpoints
            capabilities = {}

            # Test: can we list messages?
            url = "https://open.feishu.cn/open-apis/im/v1/messages?container_id_type=chat&container_id=test&page_size=1"
            async with http.get(url, headers=headers) as resp:
                data = await resp.json()
                capabilities["im:message:read"] = data.get("code") != 99991403

            # Test: can we get user info?
            url = "https://open.feishu.cn/open-apis/contact/v3/users/me"
            async with http.get(url, headers=headers) as resp:
                data = await resp.json()
                capabilities["contact:user:read"] = data.get("code") != 99991403

            print("  Feishu API capabilities:")
            for scope, available in capabilities.items():
                status = "✅" if available else "❌"
                print(f"    {status} {scope}")
        finally:
            await ch._close_http()


# ---------------------------------------------------------------------------
# Additional unit tests: constraints, content parsing, event handling
# ---------------------------------------------------------------------------


class TestFeishuChannelExtendedUnit:
    """Extended unit tests for Feishu channel."""

    def test_init_accepts_constraints(self) -> None:
        """FeishuChannel(processor, config, constraints=ChannelConstraints(...)) doesn't error."""
        constraints = ChannelConstraints(
            reply_timeout=10,
            send_rate_limit=(5, 60),
        )
        ch = FeishuChannel(
            processor=_noop_processor,
            config=_make_config(),
            constraints=constraints,
        )
        assert ch._constraints is constraints
        assert ch._constraints.reply_timeout == 10

    def test_parse_content_parts_image(self) -> None:
        """Parse image content into an ImageContent with a resource URL."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        parts = ch._parse_content_parts("image", {"image_key": "img_v2_test_key"}, message_id="om_test_message")
        assert len(parts) == 1
        assert isinstance(parts[0], ImageContent)
        assert parts[0].url.endswith("/im/v1/messages/om_test_message/resources/img_v2_test_key?type=image")

    def test_parse_content_parts_file(self) -> None:
        """message_type='file', content_data with file_key and file_name → FileContent."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        parts = ch._parse_content_parts(
            "file",
            {"file_key": "file_v2_xyz", "file_name": "doc.pdf"},
            message_id="om_test_message",
        )
        assert len(parts) == 1
        assert isinstance(parts[0], FileContent)
        assert parts[0].url.endswith("/im/v1/messages/om_test_message/resources/file_v2_xyz?type=file")
        assert parts[0].filename == "doc.pdf"

    def test_build_resource_url_escapes_identifiers(self) -> None:
        url = FeishuChannel._build_resource_url("om/message", "file key", resource_type="file")
        assert url.endswith("/im/v1/messages/om%2Fmessage/resources/file%20key?type=file")

    def test_on_message_event_builds_payload(self) -> None:
        """_on_message_event with valid data calls _enqueue_callback with correct dict."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._running = True

        enqueued: list[dict] = []
        ch._enqueue_callback = lambda payload: enqueued.append(payload)

        # Build a mock data object matching lark-oapi P2ImMessageReceiveV1 structure
        mock_sender_id = MagicMock()
        mock_sender_id.open_id = "ou_sender_123"

        mock_sender = MagicMock()
        mock_sender.sender_type = "user"
        mock_sender.sender_id = mock_sender_id

        mock_message = MagicMock()
        mock_message.message_id = "msg_event_001"
        mock_message.message_type = "text"
        mock_message.content = '{"text":"hello from event"}'
        mock_message.chat_id = "oc_chat_event"
        mock_message.chat_type = "p2p"
        mock_message.thread_id = ""
        mock_message.mentions = []

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.sender = mock_sender

        mock_header = MagicMock()
        mock_header.create_time = "1716700000000"

        mock_data = MagicMock()
        mock_data.event = mock_event
        mock_data.header = mock_header

        ch._on_message_event(mock_data)

        assert len(enqueued) == 1
        payload = enqueued[0]
        assert payload["message_id"] == "msg_event_001"
        assert payload["message_type"] == "text"
        assert payload["content"] == '{"text":"hello from event"}'
        assert payload["chat_id"] == "oc_chat_event"
        assert payload["chat_type"] == "p2p"
        assert payload["mentions"] == []
        assert payload["sender"]["sender_id"] == "ou_sender_123"
        assert payload["sender"]["sender_type"] == "user"
        assert payload["create_time"] == "1716700000000"

    def test_on_ws_reconnected_refreshes_session(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._ws_session_id = "old-session"
        ch._ws_reconnecting_since = 123.0
        ch._on_ws_reconnected()
        assert ch._ws_reconnecting_since is None
        assert ch._ws_session_id != "old-session"
        assert ch._ws_session_id is not None

    def test_ws_is_unhealthy_when_thread_missing(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._ws_thread = None
        assert ch._ws_is_unhealthy() is True

    def test_ws_is_unhealthy_when_reconnect_stale(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        alive = MagicMock()
        alive.is_alive.return_value = True
        ch._ws_thread = alive
        ch._ws_reconnecting_since = 0.0
        assert ch._ws_is_unhealthy() is True

    def test_ws_is_unhealthy_when_activity_stale(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        alive = MagicMock()
        alive.is_alive.return_value = True
        ch._ws_thread = alive
        ch._ws_reconnecting_since = None
        ch._last_ws_activity_at = 1.0
        assert ch._ws_is_unhealthy() is True
        assert "activity_stale" in ch._ws_unhealthy_reason()

    def test_ws_is_healthy_when_recently_active(self) -> None:
        import time

        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        alive = MagicMock()
        alive.is_alive.return_value = True
        ch._ws_thread = alive
        ch._ws_reconnecting_since = None
        ch._last_ws_activity_at = time.time()
        assert ch._ws_is_unhealthy() is False

    @pytest.mark.asyncio
    async def test_stop_ws_client_refuses_to_clear_live_thread_without_force(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        alive = MagicMock()
        alive.is_alive.return_value = True
        ch._ws_thread = alive
        ch._ws_client = object()
        ch._ws_loop = None

        stopped = await ch._stop_ws_client(force=False)

        assert stopped is False
        assert ch._ws_thread is alive
        assert ch._ws_client is not None
        alive.join.assert_called()

    @pytest.mark.asyncio
    async def test_stop_ws_client_force_orphans_live_thread(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        alive = MagicMock()
        alive.is_alive.return_value = True
        ch._ws_thread = alive
        ch._ws_client = object()

        stopped = await ch._stop_ws_client(force=True)

        assert stopped is True
        assert ch._ws_thread is None
        assert ch._ws_client is None
        assert alive in ch._ws_orphan_threads

    @pytest.mark.asyncio
    async def test_restart_skips_when_previous_thread_still_alive(self) -> None:
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._running = True
        start_calls: list[str] = []

        async def _fake_stop(*, force: bool = True) -> bool:
            assert force is False
            return False

        async def _fake_start() -> None:
            start_calls.append("started")

        ch._stop_ws_client = _fake_stop  # type: ignore[method-assign]
        ch._start_ws_client = _fake_start  # type: ignore[method-assign]

        await ch._restart_ws_client()

        assert start_calls == []
        assert ch._ws_reconnecting_since is not None

    def test_init_preserves_custom_constraints(self) -> None:
        """Timeout/rate-limit constraints stay intact (display flags follow config)."""
        constraints = ChannelConstraints(
            reply_timeout=42,
            send_rate_limit=(3, 10.0),
            timeout_strategy="placeholder",
        )
        ch = FeishuChannel(
            processor=_noop_processor,
            config=_make_config(),
            constraints=constraints,
        )
        assert ch._constraints is constraints
        assert ch._constraints.reply_timeout == 42
        assert ch._constraints.send_rate_limit == (3, 10.0)
        assert ch._constraints.timeout_strategy == "placeholder"
        # ChannelConfig display flags overlay onto the shared constraints object.
        assert ch._constraints.show_thinking is False
        assert ch._constraints.show_tool_hints is True

    def test_on_message_event_skips_bot(self) -> None:
        """sender.sender_type = 'bot' → callback not called."""
        ch = FeishuChannel(processor=_noop_processor, config=_make_config())
        ch._running = True

        enqueued: list[dict] = []
        ch._enqueue_callback = lambda payload: enqueued.append(payload)

        mock_sender_id = MagicMock()
        mock_sender_id.open_id = "ou_bot_123"

        mock_sender = MagicMock()
        mock_sender.sender_type = "bot"
        mock_sender.sender_id = mock_sender_id

        mock_message = MagicMock()
        mock_message.message_id = "msg_bot_001"
        mock_message.message_type = "text"
        mock_message.content = '{"text":"bot message"}'
        mock_message.chat_id = "oc_chat_bot"
        mock_message.chat_type = "p2p"
        mock_message.thread_id = ""
        mock_message.mentions = []

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.sender = mock_sender

        mock_header = MagicMock()
        mock_header.create_time = "1716700000000"

        mock_data = MagicMock()
        mock_data.event = mock_event
        mock_data.header = mock_header

        ch._on_message_event(mock_data)

        # Bot messages should be skipped
        assert len(enqueued) == 0
