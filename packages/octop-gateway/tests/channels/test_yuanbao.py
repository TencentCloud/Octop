"""Unit tests for Yuanbao channel."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest

import octop_gateway.channels.yuanbao as proto
from octop_gateway.channels.yuanbao import (
    YuanbaoChannel,
    YuanbaoConfig,
    _compute_signature,
    _YuanbaoToken,
)
from octop_gateway.channels.yuanbao.utils import _resource_id_from_url
from octop_gateway.manager import ChannelManager
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
    VideoContent,
)


async def _noop_processor(msg: InboundMessage) -> AsyncIterator[MessageEvent]:
    yield MessageEvent.completed()


def _status_payload(code: int, message: str = "") -> bytes:
    payload = proto._field(1, proto.WT_VARINT, proto._varint(code))
    if message:
        payload += proto._field(2, proto.WT_LEN, proto._string(message))
    return payload


def _first_msg_content_fields(
    payload: bytes, *, body_field: int = 5
) -> tuple[str, dict[int, list[tuple[int, bytes | int]]]]:
    request_fields = proto._fields_to_dict(proto._parse_fields(payload))
    body_bytes = request_fields[body_field][0][1]
    assert isinstance(body_bytes, bytes)
    element_fields = proto._fields_to_dict(proto._parse_fields(body_bytes))
    content_bytes = proto._get_bytes(element_fields, 2)
    return proto._get_string(element_fields, 1), proto._fields_to_dict(proto._parse_fields(content_bytes))


def test_config_accepts_frontend_shape() -> None:
    cfg = YuanbaoConfig.from_dict(
        {
            "app_key": "  app-key  ",
            "app_secret": "  app-secret  ",
            "api_domain": "bot.yuanbao.tencent.com",
            "ws_url": "bot-wss.yuanbao.tencent.com/wss/connection",
        }
    )

    assert cfg.app_key == "app-key"
    assert cfg.app_secret == "app-secret"
    assert cfg.api_domain == proto.DEFAULT_API_DOMAIN
    assert cfg.ws_url == proto.DEFAULT_WS_URL
    assert cfg.app_operation_system == sys.platform
    assert cfg.operation_system == sys.platform
    assert cfg.instance_id == str(proto.HERMES_INSTANCE_ID)
    assert cfg.missing_credentials() == []


def test_config_accepts_camelcase_aliases() -> None:
    cfg = YuanbaoConfig.from_dict(
        {
            "appKey": "app-key",
            "appSecret": "app-secret",
            "apiDomain": "https://custom.example.com/",
            "wsUrl": "https://custom.example.com/ws",
            "routeEnv": "test",
            "botId": "bot-1",
            "operationSystem": "darwin",
        }
    )

    assert cfg.app_key == "app-key"
    assert cfg.app_secret == "app-secret"
    assert cfg.api_domain == "https://custom.example.com"
    assert cfg.ws_url == "wss://custom.example.com/ws"
    assert cfg.route_env == "test"
    assert cfg.bot_id == "bot-1"
    assert cfg.identifier == "bot-1"
    assert cfg.app_operation_system == "darwin"
    assert cfg.operation_system == "darwin"


def test_config_accepts_legacy_operation_system_field() -> None:
    cfg = YuanbaoConfig.from_dict(
        {
            "appKey": "app-key",
            "appSecret": "app-secret",
            "operation_system": "linux",
        }
    )

    assert cfg.app_operation_system == "linux"
    assert cfg.operation_system == "linux"


def test_config_accepts_direct_legacy_api_base() -> None:
    cfg = YuanbaoConfig(app_key="app-key", app_secret="app-secret", api_base="custom.example.com")

    assert cfg.api_domain == "https://custom.example.com"
    assert cfg.api_base == "https://custom.example.com"
    assert cfg.ws_url == proto.DEFAULT_WS_URL


def test_missing_credentials_use_app_key_secret() -> None:
    assert YuanbaoConfig.from_dict({"app_key": "app-key"}).missing_credentials() == ["app_secret"]
    assert YuanbaoConfig.from_dict({"token": "token", "bot_id": "bot"}).missing_credentials() == [
        "app_key",
        "app_secret",
    ]


@pytest.mark.asyncio
async def test_manager_probe_accepts_frontend_config_without_token_bot_id(monkeypatch: pytest.MonkeyPatch) -> None:
    started = False
    stopped = False

    async def fake_start(self: YuanbaoChannel) -> None:
        nonlocal started
        started = True

    async def fake_stop(self: YuanbaoChannel) -> None:
        nonlocal stopped
        stopped = True

    monkeypatch.setattr(YuanbaoChannel, "start", fake_start)
    monkeypatch.setattr(YuanbaoChannel, "stop", fake_stop)

    manager = ChannelManager(processor=_noop_processor)
    await manager.probe_channel("yuanbao", {"app_key": "app-key", "app_secret": "app-secret"})

    assert started is True
    assert stopped is True


@pytest.mark.asyncio
async def test_manager_probe_uses_sign_token_only_for_yuanbao(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_probe_mode = ""

    async def fake_sign_token(self: YuanbaoChannel, *, force: bool = False) -> _YuanbaoToken:
        nonlocal seen_probe_mode
        seen_probe_mode = self._config.probe_mode
        return _YuanbaoToken("token", "bot-1", "source-1", time_left(), 600)

    async def fail_connect_once(self: YuanbaoChannel, *, force_token: bool = False) -> None:
        raise AssertionError("probe should not open Yuanbao WebSocket")

    monkeypatch.setattr(YuanbaoChannel, "_sign_token", fake_sign_token)
    monkeypatch.setattr(YuanbaoChannel, "_connect_once", fail_connect_once)

    manager = ChannelManager(processor=_noop_processor)
    await manager.probe_channel("yuanbao", {"app_key": "app-key", "app_secret": "app-secret"})

    assert seen_probe_mode == "sign_token"


def test_compute_signature_matches_documented_plaintext() -> None:
    expected = hmac.new(
        b"app-secret",
        b"nonce2026-07-21T15:00:00+08:00app-keyapp-secret",
        hashlib.sha256,
    ).hexdigest()
    assert _compute_signature("app-secret", "nonce", "2026-07-21T15:00:00+08:00", "app-key") == expected


def test_resource_id_from_url_ignores_malformed_url() -> None:
    assert _resource_id_from_url("https://hunyuan.tencent.com/download?resourceId=resource-1") == "resource-1"
    assert _resource_id_from_url("https://[invalid/download?resourceId=resource-1") == ""


@pytest.mark.asyncio
async def test_sign_token_posts_signed_request(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status = 200

        async def __aenter__(self) -> FakeResponse:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def json(self, content_type: object = None) -> dict[str, Any]:
            return {
                "code": 0,
                "data": {
                    "token": "signed-token",
                    "bot_id": "bot-1",
                    "duration": 600,
                    "source": "source-1",
                },
            }

    class FakeHttp:
        def __init__(self) -> None:
            self.url = ""
            self.payload: dict[str, Any] = {}
            self.headers: dict[str, str] = {}

        def post(
            self,
            url: str,
            *,
            json: dict[str, Any],
            timeout: object,
            headers: dict[str, str],
        ) -> FakeResponse:
            del timeout
            self.url = url
            self.payload = json
            self.headers = headers
            return FakeResponse()

    fake_http = FakeHttp()
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )

    async def fake_ensure_http() -> FakeHttp:
        return fake_http

    monkeypatch.setattr(channel, "_ensure_http", fake_ensure_http)
    monkeypatch.setattr("octop_gateway.channels.yuanbao.secrets.token_hex", lambda _n: "nonce")

    token = await channel._sign_token()

    assert fake_http.url == f"{proto.DEFAULT_API_DOMAIN}{proto.SIGN_TOKEN_PATH}"
    assert fake_http.payload["app_key"] == "app-key"
    assert fake_http.payload["nonce"] == "nonce"
    assert fake_http.payload["signature"] == _compute_signature(
        "app-secret",
        "nonce",
        str(fake_http.payload["timestamp"]),
        "app-key",
    )
    assert fake_http.headers["X-OperationSystem"] == sys.platform
    assert fake_http.headers["X-Instance-Id"] == str(proto.HERMES_INSTANCE_ID)
    assert token.token == "signed-token"
    assert token.bot_id == "bot-1"


@pytest.mark.asyncio
async def test_fetch_remote_media_resolves_yuanbao_resource_url(monkeypatch: pytest.MonkeyPatch) -> None:
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

        async def json(self, content_type: object = None) -> dict[str, Any]:
            del content_type
            return self._json_body

        async def read(self) -> bytes:
            return self._data

    class FakeHttp:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def get(self, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append({"url": url, **kwargs})
            if url.endswith("/api/resource/v1/download"):
                return FakeResponse(json_body={"code": 0, "data": {"url": "https://cos.example.com/report.pdf"}})
            return FakeResponse(data=b"pdf-bytes", content_type="application/pdf")

    fake_http = FakeHttp()
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )

    async def fake_ensure_http() -> FakeHttp:
        return fake_http

    async def fake_sign_token(*, force: bool = False) -> _YuanbaoToken:
        del force
        return _YuanbaoToken("token-1", "bot-1", "web", time_left(), 600)

    monkeypatch.setattr(channel, "_ensure_http", fake_ensure_http)
    monkeypatch.setattr(channel, "_sign_token", fake_sign_token)

    data, mime = await channel.fetch_remote_media(
        "https://hunyuan.tencent.com/api/resource/download?resourceId=resource-1"
    )

    assert data == b"pdf-bytes"
    assert mime == "application/pdf"
    assert fake_http.calls[0]["url"] == f"{proto.DEFAULT_API_DOMAIN}/api/resource/v1/download"
    assert fake_http.calls[0]["params"] == {"resourceId": "resource-1"}
    assert fake_http.calls[0]["headers"]["X-ID"] == "bot-1"
    assert fake_http.calls[0]["headers"]["X-Token"] == "token-1"
    assert fake_http.calls[0]["headers"]["X-Source"] == "web"
    assert fake_http.calls[1]["url"] == "https://cos.example.com/report.pdf"
    assert fake_http.calls[1]["headers"] == {}


@pytest.mark.asyncio
async def test_fetch_remote_media_refreshes_token_on_resource_download_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __init__(self, *, status: int = 200, json_body: dict[str, Any] | None = None, data: bytes = b"") -> None:
            self.status = status
            self._json_body = json_body or {}
            self._data = data
            self.content_type = "application/octet-stream"

        async def __aenter__(self) -> FakeResponse:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            if self.status >= 400:
                raise aiohttp.ClientResponseError(None, (), status=self.status, message="Unauthorized")

        async def json(self, content_type: object = None) -> dict[str, Any]:
            del content_type
            return self._json_body

        async def read(self) -> bytes:
            return self._data

    class FakeHttp:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def get(self, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append({"url": url, **kwargs})
            resource_calls = [call for call in self.calls if call["url"].endswith("/api/resource/v1/download")]
            if url.endswith("/api/resource/v1/download") and len(resource_calls) == 1:
                return FakeResponse(status=401)
            if url.endswith("/api/resource/v1/download"):
                return FakeResponse(json_body={"code": 0, "data": {"realUrl": "https://cos.example.com/a.bin"}})
            return FakeResponse(data=b"ok")

    force_values: list[bool] = []
    fake_http = FakeHttp()
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )

    async def fake_ensure_http() -> FakeHttp:
        return fake_http

    async def fake_sign_token(*, force: bool = False) -> _YuanbaoToken:
        force_values.append(force)
        token = "fresh-token" if force else "stale-token"
        return _YuanbaoToken(token, "bot-1", "web", time_left(), 600)

    monkeypatch.setattr(channel, "_ensure_http", fake_ensure_http)
    monkeypatch.setattr(channel, "_sign_token", fake_sign_token)

    data, _mime = await channel.fetch_remote_media(
        "https://hunyuan.tencent.com/api/resource/download?resourceId=resource-2"
    )

    assert data == b"ok"
    assert force_values[:2] == [False, True]
    resource_headers = [
        call["headers"] for call in fake_http.calls if call["url"].endswith("/api/resource/v1/download")
    ]
    assert resource_headers[0]["X-Token"] == "stale-token"
    assert resource_headers[1]["X-Token"] == "fresh-token"


def test_parse_yuanbao_c2c_text_message() -> None:
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-1"

    msg = channel.parse_inbound(
        {
            "callback_command": proto.CALLBACK_C2C_SEND_MSG,
            "from_account": "user-1",
            "to_account": "bot-1",
            "sender_nickname": "Alice",
            "msg_id": "msg-1",
            "msg_body": [{"msg_type": proto.MSG_TYPE_TEXT, "msg_content": {"text": "hello"}}],
            "log_ext": {"trace_id": "trace-1"},
        }
    )

    assert msg.channel_subject is not None
    assert msg.channel_subject.subject_id == "user-1"
    assert msg.channel_subject.chat_type == "direct"
    assert msg.text == "hello"
    assert msg.metadata["reply_to_account"] == "user-1"
    assert msg.metadata["bot_id"] == "bot-1"
    assert msg.metadata["trace_id"] == "trace-1"


def test_parse_yuanbao_group_text_message() -> None:
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )

    msg = channel.parse_inbound(
        {
            "callback_command": proto.CALLBACK_GROUP_SEND_MSG,
            "from_account": "user-1",
            "group_code": "group-1",
            "group_name": "Group",
            "msg_id": "msg-1",
            "msg_body": [{"msg_type": proto.MSG_TYPE_TEXT, "msg_content": {"text": "hi group"}}],
        }
    )

    assert msg.channel_subject is not None
    assert msg.channel_subject.subject_id == "group-1"
    assert msg.channel_subject.chat_type == "group"
    assert msg.channel_session_id == "group-1"
    assert msg.text == "hi group"


def test_parse_yuanbao_rich_media_message_normalizes_urls() -> None:
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )

    msg = channel.parse_inbound(
        {
            "callback_command": proto.CALLBACK_C2C_SEND_MSG,
            "from_account": "user-1",
            "msg_id": "msg-media",
            "msg_body": [
                {
                    "msg_type": proto.MSG_TYPE_IMAGE,
                    "msg_content": {
                        "image_info_array": [
                            {"type": 1, "size": 12, "width": 32, "height": 24, "url": "//cdn.example.com/a.png"}
                        ]
                    },
                },
                {
                    "msg_type": proto.MSG_TYPE_FILE,
                    "msg_content": {
                        "url": "files.example.com/a.pdf",
                        "file_name": "a.pdf",
                        "file_size": 42,
                    },
                },
                {
                    "msg_type": proto.MSG_TYPE_SOUND,
                    "msg_content": {"url": "/voice.amr", "file_size": 7},
                },
                {
                    "msg_type": proto.MSG_TYPE_VIDEO,
                    "msg_content": {"url": "https://cdn.example.com/v.mp4", "file_size": 99},
                },
            ],
        }
    )

    assert isinstance(msg.content[0], ImageContent)
    assert msg.content[0].url == "https://cdn.example.com/a.png"
    assert msg.content[0].width == 32
    assert msg.content[0].height == 24
    assert msg.content[0].size == 12
    assert isinstance(msg.content[1], FileContent)
    assert msg.content[1].url == "https://files.example.com/a.pdf"
    assert msg.content[1].filename == "a.pdf"
    assert msg.content[1].size == 42
    assert isinstance(msg.content[2], AudioContent)
    assert msg.content[2].url == f"{proto.DEFAULT_API_DOMAIN}/voice.amr"
    assert msg.content[2].size == 7
    assert isinstance(msg.content[3], VideoContent)
    assert msg.content[3].url == "https://cdn.example.com/v.mp4"
    assert msg.content[3].size == 99


def test_legacy_parse_keeps_metadata_dict() -> None:
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )

    msg = channel.parse_inbound(
        {
            "from_user": "user-1",
            "conversation_id": "conv-1",
            "message_id": "msg-1",
            "message_type": "text",
            "content": {"text": "legacy hello"},
        }
    )

    assert msg.channel_subject is not None
    assert msg.channel_subject.metadata["conversation_id"] == "conv-1"
    assert msg.channel_subject.metadata["message_id"] == "msg-1"
    assert msg.text == "legacy hello"


def test_protocol_request_round_trip() -> None:
    packet = proto.encode_request(proto.CMD_PING, proto.MODULE_CONN_ACCESS, "req-1", 7)
    decoded = proto.decode_conn_msg(packet)

    assert decoded["head"]["cmd_type"] == proto.CMD_TYPE_REQUEST
    assert decoded["head"]["cmd"] == proto.CMD_PING
    assert decoded["head"]["msg_id"] == "req-1"
    assert decoded["head"]["module"] == proto.MODULE_CONN_ACCESS
    assert decoded["head"]["seq_no"] == 7


def test_protocol_encodes_image_info_array() -> None:
    payload = proto.encode_c2c_message_payload(
        to_account="user-1",
        from_account="bot-1",
        msg_body=proto.build_image_msg_body(
            url="https://cos.example.com/image.png",
            uuid="image-uuid",
            filename="image.png",
            size=123,
            width=16,
            height=9,
            mime_type="image/png",
        ),
    )

    msg_type, content_fields = _first_msg_content_fields(payload)
    assert msg_type == proto.MSG_TYPE_IMAGE
    assert proto._get_string(content_fields, 2) == "image-uuid"
    assert proto._get_varint(content_fields, 3) == 3
    image_info = content_fields[8][0][1]
    assert isinstance(image_info, bytes)
    image_fields = proto._fields_to_dict(proto._parse_fields(image_info))
    assert proto._get_varint(image_fields, 1) == 1
    assert proto._get_varint(image_fields, 2) == 123
    assert proto._get_varint(image_fields, 3) == 16
    assert proto._get_varint(image_fields, 4) == 9
    assert proto._get_string(image_fields, 5) == "https://cos.example.com/image.png"


@pytest.mark.asyncio
async def test_inbound_text_frame_sends_immediate_heartbeat_and_enqueues(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "callback_command": proto.CALLBACK_C2C_SEND_MSG,
        "from_account": "user-1",
        "to_account": "bot-1",
        "msg_id": "msg-1",
        "msg_body": [{"msg_type": proto.MSG_TYPE_TEXT, "msg_content": {"text": "hello"}}],
    }
    enqueued: list[dict[str, Any]] = []
    heartbeats: list[ChannelSubject] = []
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-1"
    channel.set_enqueue_callback(enqueued.append)

    async def fake_typing(subject: ChannelSubject) -> None:
        heartbeats.append(subject)

    monkeypatch.setattr(channel, "_send_typing_indicator", fake_typing)

    await channel._handle_text_frame(json.dumps(payload))
    await channel._handle_text_frame(json.dumps(payload))

    assert enqueued == [payload]
    assert len(heartbeats) == 1
    assert heartbeats[0].subject_id == "user-1"


@pytest.mark.asyncio
async def test_start_uses_ws_url_and_auth_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWs:
        closed = False

        def __aiter__(self) -> FakeWs:
            return self

        async def __anext__(self) -> object:
            await asyncio.sleep(3600)
            raise StopAsyncIteration

        async def close(self) -> None:
            self.closed = True

    class FakeHttp:
        def __init__(self) -> None:
            self.ws_url = ""

        async def ws_connect(self, url: str, *, timeout: object) -> FakeWs:
            self.ws_url = url
            return FakeWs()

    fake_http = FakeHttp()
    auth_called = False

    async def fake_ensure_http() -> FakeHttp:
        return fake_http

    async def fake_sign_token(self: YuanbaoChannel, *, force: bool = False) -> _YuanbaoToken:
        return _YuanbaoToken("token", "bot-1", "source-1", time_left(), 600)

    async def fake_auth_bind(self: YuanbaoChannel, token: _YuanbaoToken) -> None:
        nonlocal auth_called
        auth_called = True

    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret", ws_url="wss://example.com/ws"),
    )
    monkeypatch.setattr(channel, "_ensure_http", fake_ensure_http)
    monkeypatch.setattr(YuanbaoChannel, "_sign_token", fake_sign_token)
    monkeypatch.setattr(YuanbaoChannel, "_auth_bind", fake_auth_bind)

    await channel.start()
    await channel.stop()

    assert fake_http.ws_url == "wss://example.com/ws"
    assert auth_called is True


@pytest.mark.asyncio
async def test_send_text_routes_to_c2c_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-1"

    async def fake_request(
        cmd: str,
        module: str,
        payload: bytes,
        *,
        msg_id: str | None = None,
        wait_response: bool = True,
    ) -> bytes:
        calls.append(
            {
                "cmd": cmd,
                "module": module,
                "payload": payload,
                "msg_id": msg_id,
                "wait_response": wait_response,
            }
        )
        return b""

    monkeypatch.setattr(channel, "_request", fake_request)

    await channel._send_text(
        ChannelSubject(
            subject_id="user-1",
            chat_type="direct",
            metadata={"msg_id": "msg-1", "reply_to_account": "user-1", "trace_id": "trace-1"},
        ),
        "hello",
    )

    assert calls[0]["cmd"] == proto.CMD_SEND_C2C_MESSAGE
    assert calls[0]["module"] == proto.MODULE_BIZ
    assert str(calls[0]["msg_id"]).startswith("c2c_")
    c2c_fields = proto._fields_to_dict(proto._parse_fields(calls[0]["payload"]))
    assert proto._get_string(c2c_fields, 1) == calls[0]["msg_id"]
    assert proto._get_string(c2c_fields, 2) == "user-1"
    assert proto._get_string(c2c_fields, 3) == "bot-1"
    assert 4 not in c2c_fields
    assert 7 not in c2c_fields
    assert 8 not in c2c_fields
    assert b"msg-1" not in calls[0]["payload"]

    assert calls[1]["cmd"] == proto.CMD_SEND_PRIVATE_HEARTBEAT
    assert calls[1]["wait_response"] is False
    heartbeat_fields = proto._fields_to_dict(proto._parse_fields(calls[1]["payload"]))
    assert proto._get_varint(heartbeat_fields, 3) == proto.HEARTBEAT_FINISH


@pytest.mark.asyncio
async def test_send_text_reports_cloud_im_failure_without_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-from-token"

    async def fake_request(
        cmd: str,
        module: str,
        payload: bytes,
        *,
        msg_id: str | None = None,
        wait_response: bool = True,
    ) -> bytes:
        calls.append(
            {
                "cmd": cmd,
                "module": module,
                "payload": payload,
                "msg_id": msg_id,
                "wait_response": wait_response,
            }
        )
        if cmd == proto.CMD_SEND_C2C_MESSAGE:
            return _status_payload(1692501, "cloud im failed")
        return b""

    monkeypatch.setattr(channel, "_request", fake_request)

    with pytest.raises(RuntimeError, match="1692501"):
        await channel._send_text(
            ChannelSubject(
                subject_id="user-1",
                chat_type="direct",
                metadata={
                    "msg_id": "reply-msg-1",
                    "reply_to_account": "user-1",
                    "to_account": "bot-from-inbound",
                    "bot_id": "bot-from-token",
                },
            ),
            "hello",
        )

    send_calls = [call for call in calls if call["cmd"] == proto.CMD_SEND_C2C_MESSAGE]
    assert len(send_calls) == 1
    assert str(send_calls[0]["msg_id"]).startswith("c2c_")
    assert b"bot-from-token" in send_calls[0]["payload"]
    assert b"bot-from-inbound" not in send_calls[0]["payload"]
    assert b"reply-msg-1" not in send_calls[0]["payload"]
    assert any(call["cmd"] == proto.CMD_SEND_PRIVATE_HEARTBEAT and call["wait_response"] is False for call in calls)


@pytest.mark.asyncio
async def test_send_image_uploads_bytes_and_sends_image_body(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    uploads: list[dict[str, Any]] = []
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-1"

    async def fake_load(part: ImageContent) -> tuple[bytes, str]:
        assert part.data == "inline"
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "image/png"

    async def fake_upload(data: bytes, filename: str, mime_type: str) -> dict[str, Any]:
        uploads.append({"data": data, "filename": filename, "mime_type": mime_type})
        return {
            "url": "https://cos.example.com/image.png",
            "uuid": "image-md5",
            "size": len(data),
            "width": 1,
            "height": 1,
        }

    async def fake_request(
        cmd: str,
        module: str,
        payload: bytes,
        *,
        msg_id: str | None = None,
        wait_response: bool = True,
    ) -> bytes:
        calls.append(
            {
                "cmd": cmd,
                "module": module,
                "payload": payload,
                "msg_id": msg_id,
                "wait_response": wait_response,
            }
        )
        return b""

    monkeypatch.setattr(channel, "load_media_bytes", fake_load)
    monkeypatch.setattr(channel, "_upload_media_to_yuanbao", fake_upload)
    monkeypatch.setattr(channel, "_request", fake_request)

    await channel._send_media(
        ChannelSubject(subject_id="user-1", chat_type="direct", metadata={"reply_to_account": "user-1"}),
        ImageContent(data="inline", mime_type="image/png"),
    )

    assert uploads[0]["filename"] == "image.png"
    assert uploads[0]["mime_type"] == "image/png"
    send_call = next(call for call in calls if call["cmd"] == proto.CMD_SEND_C2C_MESSAGE)
    msg_type, content_fields = _first_msg_content_fields(send_call["payload"])
    assert msg_type == proto.MSG_TYPE_IMAGE
    assert proto._get_string(content_fields, 2) == "image-md5"
    image_info = content_fields[8][0][1]
    assert isinstance(image_info, bytes)
    image_fields = proto._fields_to_dict(proto._parse_fields(image_info))
    assert proto._get_string(image_fields, 5) == "https://cos.example.com/image.png"
    assert proto._get_varint(image_fields, 3) == 1
    assert proto._get_varint(image_fields, 4) == 1


@pytest.mark.asyncio
async def test_send_file_url_falls_back_to_native_file_body_if_upload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-1"

    async def fail_load(part: FileContent) -> tuple[bytes, str]:
        del part
        raise RuntimeError("download failed")

    async def fake_request(
        cmd: str,
        module: str,
        payload: bytes,
        *,
        msg_id: str | None = None,
        wait_response: bool = True,
    ) -> bytes:
        calls.append(
            {
                "cmd": cmd,
                "module": module,
                "payload": payload,
                "msg_id": msg_id,
                "wait_response": wait_response,
            }
        )
        return b""

    monkeypatch.setattr(channel, "load_media_bytes", fail_load)
    monkeypatch.setattr(channel, "_request", fake_request)

    await channel._send_media(
        ChannelSubject(subject_id="user-1", chat_type="direct", metadata={"reply_to_account": "user-1"}),
        FileContent(url="//cdn.example.com/report.pdf", filename="report.pdf", size=10),
    )

    send_call = next(call for call in calls if call["cmd"] == proto.CMD_SEND_C2C_MESSAGE)
    msg_type, content_fields = _first_msg_content_fields(send_call["payload"])
    assert msg_type == proto.MSG_TYPE_FILE
    assert proto._get_string(content_fields, 10) == "https://cdn.example.com/report.pdf"
    assert proto._get_string(content_fields, 12) == "report.pdf"
    assert proto._get_varint(content_fields, 11) == 10


@pytest.mark.asyncio
async def test_send_local_media_failure_emits_visible_text_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    channel = YuanbaoChannel(
        processor=_noop_processor,
        config=YuanbaoConfig(app_key="app-key", app_secret="app-secret"),
    )
    channel._bot_id = "bot-1"

    async def fail_load(part: FileContent) -> tuple[bytes, str]:
        del part
        raise RuntimeError("backend missing file")

    async def fake_request(
        cmd: str,
        module: str,
        payload: bytes,
        *,
        msg_id: str | None = None,
        wait_response: bool = True,
    ) -> bytes:
        calls.append(
            {
                "cmd": cmd,
                "module": module,
                "payload": payload,
                "msg_id": msg_id,
                "wait_response": wait_response,
            }
        )
        return b""

    monkeypatch.setattr(channel, "load_media_bytes", fail_load)
    monkeypatch.setattr(channel, "_request", fake_request)

    await channel._send_media(
        ChannelSubject(subject_id="user-1", chat_type="direct", metadata={"reply_to_account": "user-1"}),
        FileContent(local_path="yuanbao/out/report.pdf", filename="report.pdf"),
    )

    send_call = next(call for call in calls if call["cmd"] == proto.CMD_SEND_C2C_MESSAGE)
    msg_type, content_fields = _first_msg_content_fields(send_call["payload"])
    assert msg_type == proto.MSG_TYPE_TEXT
    assert proto._get_string(content_fields, 1) == "[File: report.pdf (local file upload failed)]"


def time_left() -> float:
    return asyncio.get_event_loop().time() + 600
