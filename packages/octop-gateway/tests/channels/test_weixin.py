"""Unit tests for WeChat (iLink Bot) channel.

Tests cover:
- Config creation with accounts list
- Channel initialization
- Inbound message parsing (text/image/file, passthrough)
- Poll loop session-expired handling (errcode -14 → pause)
- Send text payload format and auth headers for the iLink protocol

No network calls — aiohttp.ClientSession is mocked where needed.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop_gateway.channels.weixin import (
    WeixinAccountConfig,
    WeixinChannel,
    WeixinConfig,
)
from octop_gateway.channels.weixin.channel import _WeixinTurn
from octop_gateway.channels.weixin.text import split_weixin_text
from octop_gateway.channels.weixin.types import SendMessageResponse, WeixinAPIError
from octop_gateway.media import FileSystemMediaBackend
from octop_gateway.models import (
    ChannelSubject,
    FileContent,
    InboundMessage,
    MessageEvent,
    TextContent,
)
from octop_gateway.push_routing import WEIXIN_CONTEXT_TOKEN_KEY

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_account() -> WeixinAccountConfig:
    return WeixinAccountConfig(
        account_id="acc_001",
        token="test_token_abc",
        account_name="Test Bot",
        bot_uin="bot_123",
        user_uin="user_456",
    )


def _make_config() -> WeixinConfig:
    return WeixinConfig(accounts=[_make_account()])


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestWeixinChannelUnit:
    """Unit tests for WeChat iLink channel logic (no API calls)."""

    def test_config_creation(self) -> None:
        config = _make_config()
        assert len(config.accounts) == 1
        assert config.accounts[0].account_id == "acc_001"
        assert config.accounts[0].token == "test_token_abc"
        assert config.accounts[0].account_name == "Test Bot"

    def test_config_empty_accounts(self) -> None:
        config = WeixinConfig()
        assert config.accounts == []

    def test_channel_init(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        assert ch.channel_type == "weixin"
        assert ch._config.accounts[0].account_id == "acc_001"
        assert ch._running is False

    def test_channel_init_with_constraints(self) -> None:
        from octop_gateway.constraints import ChannelConstraints

        custom = ChannelConstraints(reply_timeout=15.0)
        ch = WeixinChannel(processor=_noop_processor, config=_make_config(), constraints=custom)
        assert ch._constraints.reply_timeout == 0

    def test_resolve_push_subject_enriches_sparse_metadata(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        subject = ChannelSubject(
            subject_id="user@im.wechat",
            metadata={"channel_type": "weixin"},
        )
        resolved = ch.resolve_push_subject(subject)
        assert resolved.metadata.get("from_user_id") == "user@im.wechat"
        assert resolved.metadata.get("account_id") == "acc_001"

    def test_parse_inbound_text(self) -> None:
        """item_list with a text_item parses to InboundMessage with metadata."""
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "_account_id": "acc_001",
            "from_user_id": "wx_user_789",
            "session_id": "sess_1",
            "context_token": "ctx_token_abc",
            "item_list": [{"type": 1, "text_item": {"text": "hello weixin"}}],
        }
        msg = ch.parse_inbound(payload)

        assert isinstance(msg, InboundMessage)
        assert msg.channel_type == "weixin"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "wx_user_789"
        assert msg.text == "hello weixin"
        assert msg.metadata["account_id"] == "acc_001"
        assert msg.metadata["from_user_id"] == "wx_user_789"
        assert msg.metadata["context_token"] == "ctx_token_abc"

    def test_parse_inbound_image(self) -> None:
        from octop_gateway.models import ImageContent

        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "_account_id": "acc_001",
            "from_user_id": "img_user",
            "item_list": [{"type": 2, "image_item": {"url": "https://example.com/photo.png"}}],
        }
        msg = ch.parse_inbound(payload)
        images = [p for p in msg.content if isinstance(p, ImageContent)]
        assert len(images) == 1
        assert images[0].url == "https://example.com/photo.png"

    def test_parse_inbound_file(self) -> None:
        from octop_gateway.models import FileContent

        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "_account_id": "acc_001",
            "from_user_id": "file_user",
            "item_list": [{"type": 4, "file_item": {"url": "https://example.com/doc.pdf", "file_name": "doc.pdf"}}],
        }
        msg = ch.parse_inbound(payload)
        files = [p for p in msg.content if isinstance(p, FileContent)]
        assert len(files) == 1
        assert files[0].url == "https://example.com/doc.pdf"
        assert files[0].filename == "doc.pdf"

    def test_parse_inbound_encrypted_file_media(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        payload = {
            "_account_id": "acc_001",
            "from_user_id": "file_user",
            "item_list": [
                {
                    "type": 4,
                    "file_item": {
                        "file_name": "doc.pdf",
                        "media": {
                            "encrypt_query_param": "encrypted-param",
                            "aes_key": "aes-key",
                            "encrypt_type": 1,
                        },
                    },
                }
            ],
        }
        msg = ch.parse_inbound(payload)
        files = [p for p in msg.content if isinstance(p, FileContent)]

        assert len(files) == 1
        assert files[0].filename == "doc.pdf"
        assert files[0].local_path
        assert files[0].local_path.startswith("weixin-cdn:")

    def test_parse_inbound_returns_existing(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        original = InboundMessage(
            channel_id="weixin",
            content=[TextContent(text="passthrough")],
            channel_subject=ChannelSubject(subject_id="wx_pass"),
        )
        result = ch.parse_inbound(original)
        assert result is original
        assert result.text == "passthrough"

    def test_parse_inbound_empty_items_fallback(self) -> None:
        """Empty item_list yields a single empty text part (no crash)."""
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        payload = {"_account_id": "acc_001", "from_user_id": "user_empty", "item_list": []}
        msg = ch.parse_inbound(payload)
        assert msg.text == ""

    def test_default_constraints(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        defaults = ch._default_constraints()
        assert defaults.reply_timeout == 0
        assert defaults.timeout_strategy == "none"
        assert defaults.show_thinking is False

    @pytest.mark.asyncio
    async def test_poll_session_expired_pauses(self) -> None:
        """getUpdates raising -14 pauses the account instead of tight-looping."""
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        ch._running = True
        account = _make_account()

        call_count = 0

        async def mock_get_updates(acc, buf, timeout_ms):
            nonlocal call_count
            call_count += 1
            raise WeixinAPIError(ret=-14, errcode=-14, errmsg="session timeout")

        async def fake_sleep(*_a, **_k):
            # Once the loop reaches its first sleep (the pause wait), end it.
            ch._running = False

        with (
            patch.object(ch, "_get_updates", side_effect=mock_get_updates),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            await ch._poll_loop(account)

        # -14 sets a pause window for the account; getUpdates is called once,
        # after which the loop only waits out the pause (no tight retry).
        assert "acc_001" in ch._session_pause_until
        assert ch._remaining_pause_s("acc_001") > 0
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_send_text_payload_format(self) -> None:
        """sendMessage receives the expected iLink body and auth headers."""
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ret": 0, "messageId": 12345})
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.object(ch, "_ensure_http", new_callable=AsyncMock, return_value=mock_session):
            await ch._send_text(
                ChannelSubject(
                    subject_id="wx_target_user",
                    metadata={
                        "account_id": "acc_001",
                        "from_user_id": "wx_target_user",
                        "context_token": "ctx_existing_token",
                    },
                    first_seen=0,
                    last_seen=0,
                ),
                "Hello from test",
            )

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args

        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert "ilink/bot/sendmessage" in url

        body = json.loads(call_args.kwargs["data"])
        msg = body["msg"]
        assert msg["to_user_id"] == "wx_target_user"
        assert msg["context_token"] == "ctx_existing_token"
        assert msg["message_type"] == 2
        assert msg["message_state"] == 2
        assert msg["item_list"] == [{"type": 1, "text_item": {"text": "Hello from test"}}]
        assert msg["client_id"].startswith("hg-weixin-")

        headers = call_args.kwargs["headers"]
        assert headers["AuthorizationType"] == "ilink_bot_token"
        assert headers["Authorization"] == "Bearer test_token_abc"
        assert "X-WECHAT-UIN" in headers

    @pytest.mark.asyncio
    async def test_send_text_prefers_live_context_cache_over_stale_metadata(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        ch._context_tokens[ch._context_cache_key("acc_001", "wx_target_user")] = "ctx_live"

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ret": 0, "messageId": 99})
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch.object(ch, "_ensure_http", new_callable=AsyncMock, return_value=mock_session):
            await ch._send_text(
                ChannelSubject(
                    subject_id="wx_target_user",
                    metadata={
                        "account_id": "acc_001",
                        "from_user_id": "wx_target_user",
                        "context_token": "ctx_stale",
                    },
                ),
                "cron ping",
            )

        body = json.loads(mock_session.post.call_args.kwargs["data"])
        assert body["msg"]["context_token"] == "ctx_live"

    @pytest.mark.asyncio
    async def test_send_text_retries_without_context_token_on_ret_minus_2(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        responses = [
            WeixinAPIError(ret=-2, errcode=-2, errmsg="auth failed"),
            SendMessageResponse(ret=0, message_id=1),
        ]

        fake_api = SimpleNamespace(send_message=AsyncMock(side_effect=responses))
        ch._api = AsyncMock(return_value=fake_api)  # type: ignore[method-assign]

        await ch._send_text(
            ChannelSubject(
                subject_id="wx_target_user",
                metadata={
                    "account_id": "acc_001",
                    "from_user_id": "wx_target_user",
                    "context_token": "ctx_stale",
                },
            ),
            "cron ping",
        )

        assert fake_api.send_message.await_count == 2
        assert fake_api.send_message.await_args_list[1].kwargs["context_token"] == ""

    @pytest.mark.asyncio
    async def test_send_file_uploads_weixin_media_item(self) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        ch.load_media_bytes = AsyncMock(return_value=(b"PDFBYTES", "application/pdf"))  # type: ignore[method-assign]
        ch._upload_media_part = AsyncMock(  # type: ignore[method-assign]
            return_value={"type": 4, "file_item": {"media": {"encrypt_query_param": "p", "aes_key": "k"}}}
        )
        fake_api = SimpleNamespace(send_items=AsyncMock(return_value=SendMessageResponse(ret=0)))
        ch._api = AsyncMock(return_value=fake_api)  # type: ignore[method-assign]
        ch._send_text = AsyncMock()  # type: ignore[method-assign]

        await ch._send_media(
            ChannelSubject(
                subject_id="wx_target_user",
                metadata={"account_id": "acc_001", "from_user_id": "wx_target_user"},
            ),
            FileContent(filename="paper.pdf"),
        )

        ch._upload_media_part.assert_awaited_once()
        send_kwargs = fake_api.send_items.await_args.kwargs
        assert send_kwargs["to_user_id"] == "wx_target_user"
        assert send_kwargs["items"][0]["type"] == 4
        assert send_kwargs["items"][0]["file_item"]["file_name"] == "paper.pdf"
        ch._send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resolve_inbound_encrypted_file_persists_to_backend(self, tmp_path) -> None:
        ch = WeixinChannel(processor=_noop_processor, config=_make_config())
        backend = FileSystemMediaBackend(tmp_path)
        ch.set_media_backend(backend)
        ch._ensure_http = AsyncMock(return_value=object())  # type: ignore[method-assign]

        msg = ch.parse_inbound(
            {
                "_account_id": "acc_001",
                "from_user_id": "file_user",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "doc.pdf",
                            "media": {"encrypt_query_param": "encrypted-param", "aes_key": "aes-key"},
                        },
                    }
                ],
            }
        )

        with patch("octop_gateway.channels.weixin.media.download_and_decrypt", new=AsyncMock(return_value=b"%PDF-1.7")):
            await ch._resolve_inbound_media(msg)

        files = [p for p in msg.content if isinstance(p, FileContent)]
        assert files[0].local_path
        assert files[0].local_path.startswith(f"weixin/{ch.channel_id}/")
        assert files[0].mime_type == "application/pdf"
        assert files[0].size == len(b"%PDF-1.7")
        assert await backend.read(files[0].local_path) == b"%PDF-1.7"

    @pytest.mark.asyncio
    async def test_get_updates_includes_longpolling_timeout(self) -> None:
        """getUpdates request body must carry longpolling_timeout_ms for the server."""
        from octop_gateway.channels.weixin.api import WeixinAPIClient

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ret": 0, "getUpdatesBuf": "buf1"})
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        client = WeixinAPIClient(
            base_url="https://example.test",
            token="tok",
            session=mock_session,
        )
        await client.get_updates("cursor0", timeout_ms=35000)

        body = json.loads(mock_session.post.call_args.kwargs["data"])
        assert body["longpolling_timeout_ms"] == 35000
        assert body["get_updates_buf"] == "cursor0"


def test_split_weixin_text_prefers_a_line_break() -> None:
    first = "a" * 10
    second = "b" * 10
    parts = split_weixin_text(f"{first}\n{second}", limit=12)
    assert parts == [first, second]


def _subject() -> ChannelSubject:
    return ChannelSubject(
        subject_id="wx_target_user",
        metadata={"account_id": "acc_001", "from_user_id": "wx_target_user"},
    )


def _api(ch: WeixinChannel) -> AsyncMock:
    send = AsyncMock(return_value=SendMessageResponse(ret=0, message_id=1))
    ch._api = AsyncMock(return_value=SimpleNamespace(send_message=send))  # type: ignore[method-assign]
    return send


@pytest.mark.asyncio
async def test_send_uses_durable_context_token_when_ephemeral_is_stripped() -> None:
    ch = WeixinChannel(processor=_noop_processor, config=_make_config())
    send = _api(ch)
    await ch._send_text(
        ChannelSubject(
            subject_id="wx_target_user",
            metadata={
                "account_id": "acc_001",
                "from_user_id": "wx_target_user",
                WEIXIN_CONTEXT_TOKEN_KEY: "ctx_saved",
            },
        ),
        "cron ping",
    )
    assert send.await_args.kwargs["context_token"] == "ctx_saved"


@pytest.mark.asyncio
async def test_long_text_is_split_across_sends() -> None:
    ch = WeixinChannel(processor=_noop_processor, config=_make_config())
    send = _api(ch)
    await ch._send_text(_subject(), ("字" * 10) + "\n" + ("字" * 10))
    with patch("octop_gateway.channels.weixin.channel.split_weixin_text", return_value=["甲", "乙"]):
        await ch._send_text(_subject(), "ignored")
    texts = [call.kwargs["text"] for call in send.await_args_list]
    assert texts[-2:] == ["甲", "乙"]


@pytest.mark.asyncio
async def test_failed_thinking_light_placeholder_stays_before_the_answer() -> None:
    async def processor(_msg: InboundMessage):
        await asyncio.sleep(0.05)
        yield MessageEvent.delta("答案")
        yield MessageEvent.completed()

    ch = WeixinChannel(processor=processor, config=_make_config())
    send = _api(ch)
    ch._typing_once = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with patch("octop_gateway.channels.weixin.channel._PLACEHOLDER_WAIT_S", 0.01):
        await ch._process_inbound(
            InboundMessage(
                channel_id="weixin",
                channel_type="weixin",
                channel_subject=_subject(),
                content=[TextContent(text="hi")],
            ),
            _subject(),
        )

    texts = [call.kwargs["text"] for call in send.await_args_list]
    assert texts[0] == "⏳ 思考中..."
    assert texts[-1] == "答案"
    assert texts.index("答案") > texts.index("⏳ 思考中...")


@pytest.mark.asyncio
async def test_fast_answer_is_not_followed_by_placeholder() -> None:
    async def processor(_msg: InboundMessage):
        yield MessageEvent.delta("答案")
        yield MessageEvent.completed()

    ch = WeixinChannel(processor=processor, config=_make_config())
    send = _api(ch)
    ch._typing_once = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with patch("octop_gateway.channels.weixin.channel._PLACEHOLDER_WAIT_S", 5):
        await ch._process_inbound(
            InboundMessage(
                channel_id="weixin",
                channel_type="weixin",
                channel_subject=_subject(),
                content=[TextContent(text="hi")],
            ),
            _subject(),
        )

    texts = [call.kwargs["text"] for call in send.await_args_list]
    assert texts == ["答案"]


@pytest.mark.asyncio
async def test_typing_start_is_not_sent_after_the_turn_stops() -> None:
    ch = WeixinChannel(processor=_noop_processor, config=_make_config())
    turn = _WeixinTurn()
    turn.stop.set()
    send_typing = AsyncMock()
    ch._api = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            get_config=AsyncMock(return_value=SimpleNamespace(typing_ticket="tkt")),
            send_typing=send_typing,
        )
    )
    ok = await ch._typing_once(_subject(), status=1, turn=turn)
    assert ok is False
    send_typing.assert_not_awaited()
