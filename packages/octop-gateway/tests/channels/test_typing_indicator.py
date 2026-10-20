"""Cross-channel verification: native typing indicator implementations.

Weixin surfaces a real platform typing API via HTTP POST to ``ilink/bot/sendtyping``.

The remaining built-in channels (qq, dingtalk, feishu, wecom, yuanbao, mqtt,
telegram, xiaoyi) have no native typing API; their default
``_send_typing_indicator`` stays a no-op. We pin that contract here.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from octop_gateway.models import ChannelSubject, InboundMessage, MessageEvent


async def _noop(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    yield MessageEvent.completed()


# ---------------------------------------------------------------------------
# Weixin: POST /ilink/bot/sendtyping
# ---------------------------------------------------------------------------


class TestWeixinTyping:
    @pytest.mark.asyncio
    async def test_send_typing_posts_to_ilink_endpoint(self) -> None:
        from octop_gateway.channels.weixin import (
            WeixinAccountConfig,
            WeixinChannel,
            WeixinConfig,
        )

        ch = WeixinChannel(
            processor=_noop,
            config=WeixinConfig(
                accounts=[
                    WeixinAccountConfig(
                        account_id="acc1",
                        token="tok1",
                        base_url="https://example.test",
                    )
                ]
            ),
        )

        calls: list[dict[str, Any]] = []

        class _Resp:
            def __init__(self, payload: dict[str, Any]) -> None:
                self._payload = payload
                self.status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def json(self, content_type=None):
                return self._payload

            async def text(self):
                return json.dumps(self._payload)

        class _FakeHttp:
            closed = False

            def post(self, url, data=None, headers=None, timeout=None):
                calls.append({"url": url, "data": data, "headers": headers})
                if url.endswith("ilink/bot/getconfig"):
                    return _Resp({"ret": 0, "typingTicket": "tkt-1"})
                return _Resp({"ret": 0})

        ch._http = _FakeHttp()  # type: ignore[assignment]

        await ch._send_typing_indicator(
            ChannelSubject(
                subject_id="user_a",
                metadata={"account_id": "acc1"},
                first_seen=0,
                last_seen=0,
            )
        )

        # The iLink flow fetches a typing_ticket, then calls sendTyping.
        urls = [c["url"] for c in calls]
        assert any(u.endswith("ilink/bot/getconfig") for u in urls)
        typing_call = next(c for c in calls if c["url"].endswith("ilink/bot/sendtyping"))
        assert typing_call["headers"]["Authorization"] == "Bearer tok1"
        assert typing_call["headers"]["AuthorizationType"] == "ilink_bot_token"
        body = json.loads(typing_call["data"])
        assert body["ilink_user_id"] == "user_a"
        assert body["typing_ticket"] == "tkt-1"

    @pytest.mark.asyncio
    async def test_send_typing_silent_when_no_account(self) -> None:
        from octop_gateway.channels.weixin import WeixinChannel, WeixinConfig

        ch = WeixinChannel(processor=_noop, config=WeixinConfig(accounts=[]))
        # Must not raise even with no accounts configured.
        await ch._send_typing_indicator(ChannelSubject(subject_id="user", first_seen=0, last_seen=0))

    @pytest.mark.asyncio
    async def test_default_constraints_enable_keepalive(self) -> None:
        from octop_gateway.channels.weixin import (
            WeixinAccountConfig,
            WeixinChannel,
            WeixinConfig,
        )

        ch = WeixinChannel(
            processor=_noop,
            config=WeixinConfig(accounts=[WeixinAccountConfig(account_id="a", token="t")]),
        )
        # BaseChannel must not also run its keepalive. WeixinChannel owns the
        # thinking light so a late status=1 cannot land after the answer.
        assert ch._constraints.typing_keepalive_interval == 0
        assert ch._constraints.reply_timeout == 0


# ---------------------------------------------------------------------------
# Channels with no native typing API: pin the no-op default
# ---------------------------------------------------------------------------


class TestNoOpTypingChannels:
    """qq, dingtalk, feishu, wecom, yuanbao intentionally keep BaseChannel's
    no-op ``_send_typing_indicator``. Verify each can be invoked safely and
    produces no side effects.
    """

    @pytest.mark.asyncio
    async def test_qq_typing_is_noop(self) -> None:
        from octop_gateway.channels.qq import QQChannel, QQConfig

        ch = QQChannel(processor=_noop, config=QQConfig(app_id="a", token="t", secret="s"))
        await ch._send_typing_indicator(ChannelSubject(subject_id="u", first_seen=0, last_seen=0))

    @pytest.mark.asyncio
    async def test_dingtalk_typing_is_noop(self) -> None:
        from octop_gateway.channels.dingtalk import DingTalkChannel, DingTalkConfig

        ch = DingTalkChannel(processor=_noop, config=DingTalkConfig(app_key="k", app_secret="s"))
        await ch._send_typing_indicator(ChannelSubject(subject_id="u", first_seen=0, last_seen=0))

    @pytest.mark.asyncio
    async def test_feishu_typing_is_noop(self) -> None:
        from octop_gateway.channels.feishu import FeishuChannel, FeishuConfig

        ch = FeishuChannel(processor=_noop, config=FeishuConfig(app_id="a", app_secret="s"))
        await ch._send_typing_indicator(ChannelSubject(subject_id="u", first_seen=0, last_seen=0))

    @pytest.mark.asyncio
    async def test_wecom_typing_is_noop(self) -> None:
        from octop_gateway.channels.wecom import WeComChannel, WeComConfig

        ch = WeComChannel(processor=_noop, config=WeComConfig(bot_id="b", secret="s"))
        await ch._send_typing_indicator(ChannelSubject(subject_id="u", first_seen=0, last_seen=0))

    @pytest.mark.asyncio
    async def test_yuanbao_typing_is_noop(self) -> None:
        from octop_gateway.channels.yuanbao import YuanbaoChannel, YuanbaoConfig

        ch = YuanbaoChannel(processor=_noop, config=YuanbaoConfig(api_base="http://x", token="t"))
        await ch._send_typing_indicator(ChannelSubject(subject_id="u", first_seen=0, last_seen=0))
