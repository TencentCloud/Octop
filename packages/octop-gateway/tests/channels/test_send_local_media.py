"""Cross-channel verification: send_media handles local_path-only parts.

Each platform behaves differently:

  - feishu / dingtalk: native bytes upload (multipart) → success
  - yuanbao / wecom: protocol does not support media uploads → emits
    a text marker so the message is not silently dropped
  - weixin: resolves local media bytes and uploads them through iLink CDN

These tests deliberately mock platform SDKs / HTTP layers so they run offline
in CI and document the contract.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from octop_gateway.media import FileSystemMediaBackend
from octop_gateway.models import ChannelSubject, FileContent, ImageContent, InboundMessage, MessageEvent


async def _noop(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    yield MessageEvent.completed()


# ---------------------------------------------------------------------------
# Feishu
# ---------------------------------------------------------------------------


def _u(user_id: str) -> ChannelSubject:
    return ChannelSubject(subject_id=user_id, first_seen=0, last_seen=0)


class TestFeishuLocalImage:
    @pytest.mark.asyncio
    async def test_local_image_uploads_via_load_media_bytes(self, tmp_path) -> None:
        from octop_gateway.channels.feishu import FeishuChannel, FeishuConfig

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"FEISHUBYTES", "feishu/cached/img.png")

        ch = FeishuChannel(
            processor=_noop,
            config=FeishuConfig(app_id="a", app_secret="s"),
        )
        ch.set_media_backend(backend)

        # Stub upload + send to inspect the bytes flowing through.
        captured: dict[str, Any] = {}

        async def fake_upload(media):
            data, mime = await ch.load_media_bytes(media)
            captured["data"] = data
            captured["mime"] = mime
            return "img_key_xyz"

        ch._upload_image_to_feishu = fake_upload  # type: ignore[method-assign]
        ch._send_message = AsyncMock(return_value={"code": 0})  # type: ignore[method-assign]

        await ch._send_media(
            _u("ou_user"),
            ImageContent(local_path="feishu/cached/img.png", mime_type="image/png"),
        )

        assert captured["data"] == b"FEISHUBYTES"
        ch._send_message.assert_awaited_once()
        sent = ch._send_message.await_args.kwargs
        assert sent["msg_type"] == "image"
        assert "img_key_xyz" in sent["content"]


# ---------------------------------------------------------------------------
# DingTalk
# ---------------------------------------------------------------------------


class TestDingTalkLocalImage:
    @pytest.mark.asyncio
    async def test_local_image_uploads_via_load_media_bytes(self, tmp_path) -> None:
        from octop_gateway.channels.dingtalk import DingTalkChannel, DingTalkConfig

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"DINGBYTES", "dingtalk/cached/img.png")

        ch = DingTalkChannel(
            processor=_noop,
            config=DingTalkConfig(app_key="k", app_secret="s"),
        )
        ch.set_media_backend(backend)

        captured: dict[str, Any] = {}

        async def fake_upload(part, media_type):
            data, _ = await ch.load_media_bytes(part)
            captured["data"] = data
            captured["media_type"] = media_type
            return "media_id_001"

        ch._upload_to_dingtalk = fake_upload  # type: ignore[method-assign]
        ch._send_media_message = AsyncMock()  # type: ignore[method-assign]

        await ch._send_media(
            _u("user_x"),
            ImageContent(local_path="dingtalk/cached/img.png"),
        )

        assert captured["data"] == b"DINGBYTES"
        assert captured["media_type"] == "image"
        ch._send_media_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# Yuanbao — text-fallback expected
# ---------------------------------------------------------------------------


class TestYuanbaoLocalImage:
    @pytest.mark.asyncio
    async def test_local_image_falls_back_to_text(self) -> None:
        from octop_gateway.channels.yuanbao import YuanbaoChannel, YuanbaoConfig

        ch = YuanbaoChannel(
            processor=_noop,
            config=YuanbaoConfig(api_base="http://x", token="t"),
        )

        sent: list[str] = []
        ch._send_text = AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda user, text, *a, **kw: sent.append(text)
        )

        await ch._send_media(_u("user"), ImageContent(local_path="yuanbao/img.png"))

        assert sent and "local file" in sent[0].lower()


# ---------------------------------------------------------------------------
# Weixin
# ---------------------------------------------------------------------------


class TestWeixinLocalImage:
    @pytest.mark.asyncio
    async def test_local_image_uploads_via_load_media_bytes(self, tmp_path) -> None:
        from octop_gateway.channels.weixin import WeixinAccountConfig, WeixinChannel, WeixinConfig
        from octop_gateway.channels.weixin.types import SendMessageResponse

        backend = FileSystemMediaBackend(tmp_path)
        await backend.save(b"WEIXINBYTES", "weixin/cached/img.png")

        ch = WeixinChannel(
            processor=_noop,
            config=WeixinConfig(accounts=[WeixinAccountConfig(account_id="a", token="t")]),
        )
        ch.set_media_backend(backend)

        captured: dict[str, Any] = {}

        async def fake_upload(**kwargs):
            captured["data"] = kwargs["data"]
            captured["media_type"] = kwargs["media_type"]
            return {"type": 2, "image_item": {"media": {"encrypt_query_param": "p", "aes_key": "k"}}}

        fake_api = SimpleNamespace(send_items=AsyncMock(return_value=SendMessageResponse(ret=0)))
        ch._upload_media_part = fake_upload  # type: ignore[method-assign]
        ch._api = AsyncMock(return_value=fake_api)  # type: ignore[method-assign]
        ch._send_text = AsyncMock()  # type: ignore[method-assign]

        await ch._send_media(
            ChannelSubject(subject_id="u", metadata={"account_id": "a", "from_user_id": "u"}),
            ImageContent(local_path="weixin/cached/img.png", mime_type="image/png"),
        )

        assert captured["data"] == b"WEIXINBYTES"
        assert captured["media_type"] == 1
        fake_api.send_items.assert_awaited_once()
        ch._send_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# WeCom — native upload expected
# ---------------------------------------------------------------------------


class TestWeComLocalImage:
    @pytest.mark.asyncio
    async def test_local_file_uses_native_upload(self) -> None:
        from octop_gateway.channels.wecom import WeComChannel, WeComConfig

        ch = WeComChannel(
            processor=_noop,
            config=WeComConfig(bot_id="b", secret="s"),
        )

        ch._ws_client = AsyncMock()
        ch._ws_client.upload_media.return_value = {"media_id": "media-1"}
        ch.load_media_bytes = AsyncMock(  # type: ignore[method-assign]
            return_value=(b"data", "application/octet-stream")
        )

        await ch._send_media(_u("u"), FileContent(local_path="wecom/file.bin", filename="data.bin"))

        ch._ws_client.upload_media.assert_awaited_once_with(b"data", type="file", filename="data.bin")
        ch._ws_client.send_media_message.assert_awaited_once_with("u", "file", "media-1")
