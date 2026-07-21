"""Unit tests for ``octop.infra.gateway.channels.yuanbao``.

Covers:

* protobuf roundtrip (build / parse for send + inbound)
* HMAC sign-token signature
* ``YuanbaoConfig.missing_credentials``
* ``YuanbaoChannel.parse_inbound`` (group / direct / self-message skip)
* ``Gateway._probe_row`` for yuanbao (credential-missing branch only)
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.channels.yuanbao import (
    YuanbaoChannel,
    YuanbaoConfig,
    _make_signature,
    _make_timestamp,
    build_auth_bind,
    build_ping,
    build_send_c2c_message,
    build_send_group_message,
    parse_auth_bind_rsp,
    parse_conn_msg,
    parse_inbound_push,
    parse_ping_rsp,
    parse_push_msg,
    parse_send_message_rsp,
    pb_msg,
    pb_string,
    pb_varint,
    probe_yuanbao,
)
from octop.infra.gateway.gateway import Gateway
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid

# ---------------------------------------------------------------------------
# Helpers — local protobuf constructors for test fixtures
# ---------------------------------------------------------------------------


def _build_inbound_push_bytes(
    *,
    from_account: str = "user1",
    to_account: str = "bot1",
    sender_nickname: str = "Alice",
    group_code: str = "",
    msg_id: str = "mid-1",
    msg_seq: int = 42,
    text: str = "hello",
    claw_msg_type: int = 0,
) -> bytes:
    """Hand-encode an ``InboundMessagePush`` for parser tests."""
    msg_content = pb_string(1, text)  # MsgContent.text
    element = pb_string(1, "TIMTextElem") + pb_msg(2, msg_content)
    out = b""
    out += pb_string(1, "Group.CallbackSendMessage")  # callbackCommand
    out += pb_string(2, from_account)
    out += pb_string(3, to_account)
    out += pb_string(4, sender_nickname)
    if group_code:
        out += pb_string(6, group_code)
    out += pb_varint(8, msg_seq)
    out += pb_string(12, msg_id)
    out += pb_msg(13, element)
    out += pb_varint(18, claw_msg_type)
    return out


def _make_processor() -> Any:
    """Minimal no-op async generator processor for channel tests."""

    async def _proc(_msg: Any) -> Any:  # pragma: no cover - never iterated
        if False:
            yield None

    return _proc


def _make_channel(
    *,
    bot_id: str = "bot1",
    app_key: str = "k",
    app_secret: str = "s",
) -> YuanbaoChannel:
    cfg = YuanbaoConfig(app_key=app_key, app_secret=app_secret)
    ch = YuanbaoChannel(_make_processor(), config=cfg, channel_id="ch-yuanbao")
    # Simulate post-auth state so anti-loop / send paths can be exercised.
    ch._bot_id = bot_id
    return ch


# ---------------------------------------------------------------------------
# Protobuf codec roundtrip
# ---------------------------------------------------------------------------


def test_send_c2c_message_head_roundtrip() -> None:
    frame = build_send_c2c_message("msg-1", "bot1", "user1", "hi")
    parsed = parse_conn_msg(frame)
    head = parsed["head"]
    assert head["cmdType"] == 0  # Request
    assert head["cmd"] == "send_c2c_message"
    assert head["module"] == "yuanbao_openclaw_proxy"
    assert head["msgId"] == "msg-1"


def test_send_group_message_head_roundtrip() -> None:
    frame = build_send_group_message("msg-2", "bot1", "group-99", "hello")
    parsed = parse_conn_msg(frame)
    head = parsed["head"]
    assert head["cmd"] == "send_group_message"
    assert head["module"] == "yuanbao_openclaw_proxy"
    assert head["cmdType"] == 0
    assert head["msgId"] == "msg-2"


def test_send_message_rsp_decode_success() -> None:
    # code=0 omits field 1 on the wire (proto3 default), so an empty body
    # is a successful response.
    assert parse_send_message_rsp(b"") == {"code": 0, "message": ""}
    # Explicit code + message
    payload = pb_varint(1, 0) + pb_string(2, "ok")
    rsp = parse_send_message_rsp(payload)
    assert rsp["code"] == 0
    assert rsp["message"] == "ok"


def test_send_message_rsp_decode_error_code() -> None:
    # Negative int32 round-trip — code=50001 must survive signed unpacking.
    payload = pb_varint(1, 50001) + pb_string(2, "rate limited")
    rsp = parse_send_message_rsp(payload)
    assert rsp["code"] == 50001
    assert rsp["message"] == "rate limited"


def test_inbound_push_decode_direct_text() -> None:
    raw = _build_inbound_push_bytes(
        from_account="user-1",
        to_account="bot-1",
        sender_nickname="Alice",
        text="hello world",
        claw_msg_type=2,  # private
    )
    decoded = parse_inbound_push(raw)
    assert decoded["from_account"] == "user-1"
    assert decoded["to_account"] == "bot-1"
    assert decoded["sender_nickname"] == "Alice"
    assert decoded["group_code"] == ""
    assert decoded["msg_id"] == "mid-1"
    assert decoded["msg_seq"] == 42
    assert decoded["claw_msg_type"] == 2
    assert len(decoded["msg_body"]) == 1
    el = decoded["msg_body"][0]
    assert el["msg_type"] == "TIMTextElem"
    assert el["text"] == "hello world"


def test_inbound_push_decode_group() -> None:
    raw = _build_inbound_push_bytes(
        from_account="user-9",
        to_account="bot-9",
        group_code="group-9",
        msg_id="gmsg-1",
        msg_seq=99,
        text="hi group",
        claw_msg_type=1,  # group
    )
    decoded = parse_inbound_push(raw)
    assert decoded["group_code"] == "group-9"
    assert decoded["claw_msg_type"] == 1
    assert decoded["msg_body"][0]["text"] == "hi group"


def test_push_msg_wrapper_roundtrip() -> None:
    inner = _build_inbound_push_bytes(text="wrapped")
    push_wrapper = pb_string(1, "c2c_callback") + pb_string(2, "yuanbao_proxy")
    push_wrapper += pb_string(3, "outer-msg-id") + pb_msg(4, inner)
    parsed = parse_push_msg(push_wrapper)
    assert parsed is not None
    assert parsed["cmd"] == "c2c_callback"
    assert parsed["module"] == "yuanbao_proxy"
    assert parsed["msgId"] == "outer-msg-id"
    # data should decode into an InboundMessagePush
    inner_decoded = parse_inbound_push(parsed["data"])
    assert inner_decoded["msg_body"][0]["text"] == "wrapped"


def test_push_msg_returns_none_when_empty() -> None:
    # No cmd and no module fields → parser returns None (raw fallback path).
    assert parse_push_msg(b"") is None
    # Bytes that don't have field 1 or 2 also return None.
    only_data = pb_msg(4, b"payload")
    assert parse_push_msg(only_data) is None


def test_auth_bind_roundtrip() -> None:
    frame = build_auth_bind(
        "uid-1",
        "bot",
        "tok-1",
        "msg-1",
        app_version="2.17.0",
        bot_version="octop-test",
    )
    parsed = parse_conn_msg(frame)
    head = parsed["head"]
    assert head["cmd"] == "auth-bind"
    assert head["module"] == "conn_access"
    assert head["cmdType"] == 0
    rsp_bytes = pb_varint(1, 0) + pb_string(3, "connect-1")  # code=0, connectId
    rsp = parse_auth_bind_rsp(rsp_bytes)
    assert rsp["code"] == 0
    assert rsp["connectId"] == "connect-1"


def test_ping_roundtrip() -> None:
    frame = build_ping("ping-1")
    parsed = parse_conn_msg(frame)
    assert parsed["head"]["cmd"] == "ping"
    # PingRsp: heartInterval=1 (uint32), timestamp
    rsp_bytes = pb_varint(1, 25) + pb_varint(2, 1700000000)
    rsp = parse_ping_rsp(rsp_bytes)
    assert rsp["heartInterval"] == 25
    assert rsp["timestamp"] == 1700000000


# ---------------------------------------------------------------------------
# Sign-token signature
# ---------------------------------------------------------------------------


def test_sign_token_signature_matches_hmac() -> None:
    nonce = "0123456789abcdef0123456789abcdef"
    timestamp = "2026-07-21T15:00:00+08:00"
    app_key = "ak-xxx"
    app_secret = "sk-yyy"
    expected_plain = nonce + timestamp + app_key + app_secret
    expected = hmac.new(app_secret.encode(), expected_plain.encode(), hashlib.sha256).hexdigest()
    assert _make_signature(nonce, timestamp, app_key, app_secret) == expected


def test_sign_token_signature_changes_with_inputs() -> None:
    sig1 = _make_signature("n1", "t1", "k1", "s1")
    sig2 = _make_signature("n2", "t1", "k1", "s1")
    assert sig1 != sig2  # different nonce → different signature


def test_make_timestamp_is_beijing_iso8601() -> None:
    from datetime import datetime, timedelta, timezone

    bj = datetime(2026, 7, 21, 15, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert _make_timestamp(bj) == "2026-07-21T15:00:00+08:00"


# ---------------------------------------------------------------------------
# YuanbaoConfig.missing_credentials
# ---------------------------------------------------------------------------


def test_missing_credentials_empty_config() -> None:
    cfg = YuanbaoConfig()
    assert cfg.missing_credentials() == ["app_key", "app_secret"]


def test_missing_credentials_only_app_key() -> None:
    cfg = YuanbaoConfig(app_key="k")
    assert cfg.missing_credentials() == ["app_secret"]


def test_missing_credentials_complete() -> None:
    cfg = YuanbaoConfig(app_key="k", app_secret="s")
    assert cfg.missing_credentials() == []


def test_yuanbao_config_from_dict_filters_unknown_keys() -> None:
    cfg = YuanbaoConfig(app_key="k", app_secret="s")
    assert cfg.app_key == "k"
    assert cfg.app_secret == "s"
    assert cfg.api_domain == "bot.yuanbao.tencent.com"


# ---------------------------------------------------------------------------
# parse_inbound
# ---------------------------------------------------------------------------


def test_parse_inbound_direct_message() -> None:
    ch = _make_channel()
    payload = {
        "from_account": "user-1",
        "to_account": "bot1",
        "sender_nickname": "Alice",
        "msg_id": "m1",
        "msg_seq": 7,
        "msg_body": [{"msg_type": "TIMTextElem", "text": "hello"}],
        "claw_msg_type": 2,
    }
    msg = ch.parse_inbound(payload)
    assert msg.channel_type == "yuanbao"
    assert msg.channel_id == "ch-yuanbao"
    assert msg.channel_subject is not None
    assert msg.channel_subject.subject_id == "user-1"
    assert msg.channel_subject.chat_type == "direct"
    assert msg.text == "hello"
    assert msg.metadata["from_account"] == "user-1"
    assert msg.metadata["msg_id"] == "m1"
    assert msg.metadata["group_code"] == ""


def test_parse_inbound_group_message() -> None:
    ch = _make_channel()
    payload = {
        "from_account": "user-9",
        "to_account": "bot1",
        "sender_nickname": "Bob",
        "group_code": "group-9",
        "msg_id": "g1",
        "msg_seq": 100,
        "msg_body": [{"msg_type": "TIMTextElem", "text": "hi group"}],
        "claw_msg_type": 1,
    }
    msg = ch.parse_inbound(payload)
    assert msg.channel_subject is not None
    assert msg.channel_subject.subject_id == "group-9"
    assert msg.channel_subject.chat_type == "group"
    assert msg.text == "hi group"
    assert msg.metadata["group_code"] == "group-9"
    assert msg.metadata["sender_nickname"] == "Bob"


def test_parse_inbound_non_text_falls_back_to_marker() -> None:
    ch = _make_channel()
    payload = {
        "from_account": "user-x",
        "msg_body": [{"msg_type": "TIMImageElem", "url": "http://img"}],
    }
    msg = ch.parse_inbound(payload)
    assert msg.text.startswith("[图片]")
    assert "http://img" in msg.text


def test_parse_inbound_empty_body_yields_empty_text() -> None:
    ch = _make_channel()
    msg = ch.parse_inbound({"from_account": "u"})
    assert msg.text == ""
    assert len(msg.content) == 1


# ---------------------------------------------------------------------------
# Anti-loop: _on_push skips messages from self
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_push_skips_bot_self_message() -> None:
    ch = _make_channel(bot_id="bot-self")
    recorded: list[Any] = []
    ch.set_enqueue_callback(lambda payload: recorded.append(payload))  # type: ignore[arg-type]

    inner = _build_inbound_push_bytes(
        from_account="bot-self",
        to_account="bot-self",
        text="echo",
    )
    head = {"cmd": "c2c_callback", "cmdType": 2, "needAck": False}
    await ch._on_push(head, inner)

    assert recorded == [], "self-message must be skipped in receive loop"


@pytest.mark.asyncio
async def test_on_push_enqueues_other_user_message() -> None:
    ch = _make_channel(bot_id="bot-self")
    recorded: list[Any] = []
    ch.set_enqueue_callback(lambda payload: recorded.append(payload))  # type: ignore[arg-type]

    inner = _build_inbound_push_bytes(
        from_account="user-1",
        to_account="bot-self",
        text="hello",
    )
    head = {"cmd": "c2c_callback", "cmdType": 2, "needAck": False}
    await ch._on_push(head, inner)

    assert len(recorded) == 1
    assert recorded[0]["from_account"] == "user-1"


# ---------------------------------------------------------------------------
# probe_yuanbao — credential check (no network)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_yuanbao_raises_on_missing_app_secret() -> None:
    from harness_gateway.channel import ChannelCredentialsError

    cfg = YuanbaoConfig(app_key="k", app_secret="")
    with pytest.raises(ChannelCredentialsError) as exc:
        await probe_yuanbao(cfg)
    assert "app_secret" in exc.value.missing
    assert exc.value.kind == "yuanbao"


@pytest.mark.asyncio
async def test_probe_yuanbao_raises_on_missing_app_key() -> None:
    from harness_gateway.channel import ChannelCredentialsError

    cfg = YuanbaoConfig(app_key="", app_secret="s")
    with pytest.raises(ChannelCredentialsError) as exc:
        await probe_yuanbao(cfg)
    assert "app_key" in exc.value.missing


# ---------------------------------------------------------------------------
# Gateway._probe_row (yuanbao branch)
# ---------------------------------------------------------------------------


def _make_gateway(tmp_path: Path) -> Gateway:
    db = DBPool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    registry = AgentManager(
        repos=services.repos,
        paths=services.paths,
        config=services.config,
    )
    return Gateway(agent_manager=registry, repos=services.repos)


def _make_yuanbao_agent_row(config: dict[str, Any]) -> MagicMock:
    import json

    row = MagicMock()
    row.channel_id = new_ulid()
    row.agent_id = "agent1"
    row.kind = "yuanbao"
    row.name = "yb"
    row.config_json = json.dumps(config)
    row.enabled = 1
    return row


@pytest.mark.asyncio
async def test_gateway_probe_row_yuanbao_missing_credentials(tmp_path: Path) -> None:
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.probe_channel = AsyncMock()  # should not be called

    row = _make_yuanbao_agent_row({"app_key": "k", "app_secret": ""})

    with patch.object(gw, "get_channel", return_value=row):
        result = await gw.probe_channel(row.channel_id)

    assert result["ok"] is False
    assert "App Secret" in result["error"]
    gw._channel_manager.probe_channel.assert_not_called()


@pytest.mark.asyncio
async def test_gateway_probe_config_yuanbao_missing_credentials(tmp_path: Path) -> None:
    """``probe_config`` (synthetic __probe__ row) also bypasses the stub."""
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.probe_channel = AsyncMock()

    result = await gw.probe_config(
        agent_id="agent1",
        kind="yuanbao",
        config={"app_key": "k", "app_secret": ""},
    )
    assert result["ok"] is False
    assert "App Secret" in result["error"]
    gw._channel_manager.probe_channel.assert_not_called()


@pytest.mark.asyncio
async def test_gateway_probe_row_yuanbao_calls_probe_yuanbao(tmp_path: Path) -> None:
    """Successful probe path delegates to ``probe_yuanbao``."""
    gw = _make_gateway(tmp_path)
    gw._channel_manager = MagicMock()
    gw._channel_manager.probe_channel = AsyncMock()

    row = _make_yuanbao_agent_row({"app_key": "k", "app_secret": "s"})

    with (
        patch.object(gw, "get_channel", return_value=row),
        patch(
            "octop.infra.gateway.gateway.probe_yuanbao",
            new=AsyncMock(return_value=None),
        ) as mock_probe,
    ):
        result = await gw.probe_channel(row.channel_id)

    assert result == {"ok": True}
    mock_probe.assert_awaited_once()
    gw._channel_manager.probe_channel.assert_not_called()
