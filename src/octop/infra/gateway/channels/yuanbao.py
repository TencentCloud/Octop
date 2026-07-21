"""Tencent Yuanbao (腾讯元宝) IM channel — WSS + hand-rolled protobuf.

Replaces the broken ``YuanbaoConfig`` stub in harness-gateway 0.8.5, which
incorrectly required ``token`` / ``bot_id``. The real platform uses
``app_key`` + ``app_secret`` plus an HMAC-signed ``sign-token`` REST call
to obtain a short-lived bot token, then speaks a custom protobuf-over-WSS
protocol (``ConnMsg`` frames) for auth-bind, heartbeat, send and inbound
push.

Protocol references:

* ``probe.py`` — independent connectivity probe (sign-token + auth-bind +
  ping) verified against the live Tencent endpoint.
* Official JS plugin ``openclaw-plugin-yuanbao`` v2.17.0 (``client.js``,
  ``conn-codec.js``, ``biz-codec.js``) and proto descriptors
  (``conn.json``, ``biz.json``).

This module is intentionally self-contained: only harness-gateway base
classes/models + stdlib + aiohttp. Media upload, message chunking and
typing indicators are out of scope.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import logging
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from harness_gateway.channel import (
    BaseChannel,
    ChannelConfig,
    ChannelCredentialsError,
    MessageProcessor,
)
from harness_gateway.models import (
    ChannelSubject,
    ContentPart,
    InboundMessage,
    TextContent,
)

logger = logging.getLogger(__name__)

# =========================================================================
# Configuration
# =========================================================================


@dataclass
class YuanbaoConfig(ChannelConfig):
    """Yuanbao channel configuration.

    The dashboard persists exactly these keys::

        {"app_key": ..., "app_secret": ..., "api_domain": ...,
         "ws_url": "wss://bot-wss.yuanbao.tencent.com/wss/connection"}
    """

    app_key: str = ""
    app_secret: str = ""
    api_domain: str = "bot.yuanbao.tencent.com"
    ws_url: str = "wss://bot-wss.yuanbao.tencent.com/wss/connection"

    def missing_credentials(self) -> list[str]:
        missing: list[str] = []
        if not self.app_key:
            missing.append("app_key")
        if not self.app_secret:
            missing.append("app_secret")
        return missing


def yuanbao_config_from_dict(data: dict[str, Any]) -> YuanbaoConfig:
    """Build a ``YuanbaoConfig`` from a raw dict, ignoring unknown keys."""
    known = {"app_key", "app_secret", "api_domain", "ws_url"}

    def _clean(v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    return YuanbaoConfig(**{k: _clean(v) for k, v in data.items() if k in known})


# =========================================================================
# Protobuf codec (hand-rolled; mirrors probe.py and conn.json/biz.json)
# =========================================================================


def _varint(value: int) -> bytes:
    out = bytearray()
    value &= (1 << 64) - 1
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def pb_string(field: int, value: str) -> bytes:
    data = value.encode()
    return _tag(field, 2) + _varint(len(data)) + data


def pb_bytes(field: int, value: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(value)) + value


def pb_varint(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint(value)


def pb_msg(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


# (field, wire, value) — value is bytes for wire 2, int for wire 0/1/5
_PBField = tuple[int, int, "bytes | int"]


def pb_decode(buf: bytes) -> list[_PBField]:
    fields: list[_PBField] = []
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        field_num, wire = key >> 3, key & 7
        value: bytes | int
        if wire == 0:
            value, pos = _read_varint(buf, pos)
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            chunk = buf[pos : pos + length]
            pos += length
            value = bytes(chunk)
        elif wire == 5:
            value = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
        elif wire == 1:
            value = struct.unpack_from("<Q", buf, pos)[0]
            pos += 8
        else:
            raise ValueError(f"unsupported wire type {wire}")
        fields.append((field_num, wire, value))
    return fields


def _first(fields: list[_PBField], num: int, default: Any = None) -> Any:
    for f, _w, v in fields:
        if f == num:
            return v
    return default


def _as_str(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    if isinstance(value, int):
        return str(value)
    return str(value) if value else ""


def _as_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 0


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return b""


# ----------------------------------------------------------------- ConnMsg
# Head: cmdType=1(u32), cmd=2, seqNo=3(u32), msgId=4, module=5,
#       needAck=6(bool), meta=7(repeated), status=10(int32)
# ConnMsg: head=1(msg), data=2(bytes)


def build_conn_msg(cmd: str, module: str, msg_id: str, data: bytes, seq: int = 0) -> bytes:
    head = (
        pb_varint(1, 0)  # cmdType = Request
        + pb_string(2, cmd)
        + pb_varint(3, seq)
        + pb_string(4, msg_id)
        + pb_string(5, module)
    )
    return pb_msg(1, head) + pb_bytes(2, data)


def parse_conn_msg(raw: bytes) -> dict[str, Any]:
    top = pb_decode(raw)
    head_raw = _as_bytes(_first(top, 1, b""))
    data = _as_bytes(_first(top, 2, b""))
    head: dict[str, Any] = {}
    for f, _w, v in pb_decode(head_raw):
        if f == 1:
            head["cmdType"] = _as_int(v)
        elif f == 2:
            head["cmd"] = _as_str(v)
        elif f == 3:
            head["seqNo"] = _as_int(v)
        elif f == 4:
            head["msgId"] = _as_str(v)
        elif f == 5:
            head["module"] = _as_str(v)
        elif f == 6:
            head["needAck"] = bool(v)
        elif f == 10:
            head["status"] = struct.unpack("<i", struct.pack("<I", _as_int(v) & 0xFFFFFFFF))[0]
    return {"head": head, "data": data}


def build_push_ack(original_head: dict[str, Any]) -> bytes:
    """Build a PushAck frame echoing the original head fields (cmdType=3)."""
    head = (
        pb_varint(1, 3)  # cmdType = PushAck
        + pb_string(2, _as_str(original_head.get("cmd", "")))
        + pb_varint(3, _as_int(original_head.get("seqNo", 0)))
        + pb_string(4, _as_str(original_head.get("msgId", "")))
        + pb_string(5, _as_str(original_head.get("module", "")))
    )
    return pb_msg(1, head) + pb_bytes(2, b"")


# -------------------------------------------------------------- AuthBind
# AuthBindReq: bizId=1, authInfo=2{uid=1,source=2,token=3},
#              deviceInfo=3{appVersion=1,appOperationSystem=2,
#                            instanceId=10,botVersion=24},
#              envName=5


def build_auth_bind(
    uid: str,
    source: str,
    token: str,
    msg_id: str,
    *,
    app_version: str,
    bot_version: str,
) -> bytes:
    auth_info = pb_string(1, uid) + pb_string(2, source) + pb_string(3, token)
    device_info = (
        pb_string(1, app_version)
        + pb_string(2, "linux")
        + pb_string(10, "16")
        + pb_string(24, bot_version)
    )
    inner = pb_string(1, "ybBot") + pb_msg(2, auth_info) + pb_msg(3, device_info)
    return build_conn_msg("auth-bind", "conn_access", msg_id, inner)


def parse_auth_bind_rsp(data: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f, _w, v in pb_decode(data):
        if f == 1:
            out["code"] = struct.unpack("<i", struct.pack("<I", _as_int(v) & 0xFFFFFFFF))[0]
        elif f == 2:
            out["message"] = _as_str(v)
        elif f == 3:
            out["connectId"] = _as_str(v)
        elif f == 4:
            out["timestamp"] = _as_int(v)
        elif f == 5:
            out["clientIp"] = _as_str(v)
    return out


# --------------------------------------------------------------- Ping


def build_ping(msg_id: str) -> bytes:
    return build_conn_msg("ping", "conn_access", msg_id, b"")


def parse_ping_rsp(data: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f, _w, v in pb_decode(data):
        if f == 1:
            out["heartInterval"] = _as_int(v)
        elif f == 2:
            out["timestamp"] = _as_int(v)
    return out


# ---------------------------------------------------- Send-message requests
# SendC2CMessageReq: msgId=1, toAccount=2, fromAccount=3,
#                    msgRandom=4(u32), msgBody=5(repeated MsgBodyElement)
# SendGroupMessageReq: msgId=1, groupCode=2, fromAccount=3,
#                      random=5(string), msgBody=6(repeated MsgBodyElement)
# MsgBodyElement: msgType=1(string), msgContent=2(MsgContent)
# MsgContent: text=1, url=10, fileName=12 (subset we care about)


def _build_msg_body_text(text: str) -> bytes:
    """Encode a single ``MsgBodyElement`` containing a ``TIMTextElem``."""
    msg_content = pb_string(1, text)  # MsgContent.text
    return pb_string(1, "TIMTextElem") + pb_msg(2, msg_content)


def build_send_c2c_message(msg_id: str, from_account: str, to_account: str, text: str) -> bytes:
    body = _build_msg_body_text(text)
    inner = (
        pb_string(1, msg_id)
        + pb_string(2, to_account)
        + pb_string(3, from_account)
        + pb_varint(4, _random_u32())
        + pb_msg(5, body)
    )
    return build_conn_msg("send_c2c_message", "yuanbao_openclaw_proxy", msg_id, inner)


def build_send_group_message(msg_id: str, from_account: str, group_code: str, text: str) -> bytes:
    body = _build_msg_body_text(text)
    inner = (
        pb_string(1, msg_id)
        + pb_string(2, group_code)
        + pb_string(3, from_account)
        + pb_string(5, uuid.uuid4().hex)
        + pb_msg(6, body)
    )
    return build_conn_msg("send_group_message", "yuanbao_openclaw_proxy", msg_id, inner)


def parse_send_message_rsp(data: bytes) -> dict[str, Any]:
    """Decode ``SendC2CMessageRsp`` / ``SendGroupMessageRsp`` (isomorphic)."""
    out: dict[str, Any] = {"code": 0, "message": ""}
    for f, _w, v in pb_decode(data):
        if f == 1:
            out["code"] = struct.unpack("<i", struct.pack("<I", _as_int(v) & 0xFFFFFFFF))[0]
        elif f == 2:
            out["message"] = _as_str(v)
    return out


# ------------------------------------------------------------- Inbound push
# PushMsg wrapper: cmd=1, module=2, msgId=3, data=4(bytes)
# InboundMessagePush: callbackCommand=1, fromAccount=2, toAccount=3,
#   senderNickname=4, groupCode=6, msgSeq=8(u32), msgTime=10(u32),
#   msgId=12, msgBody=13(repeated MsgBodyElement), clawMsgType=18(enum)


def parse_push_msg(data: bytes) -> dict[str, Any] | None:
    """Decode outer ``PushMsg`` wrapper; returns None if neither cmd nor module is set."""
    out: dict[str, Any] = {"cmd": "", "module": "", "msgId": "", "data": b""}
    has_field = False
    for f, _w, v in pb_decode(data):
        if f == 1:
            out["cmd"] = _as_str(v)
            has_field = True
        elif f == 2:
            out["module"] = _as_str(v)
            has_field = True
        elif f == 3:
            out["msgId"] = _as_str(v)
        elif f == 4:
            out["data"] = _as_bytes(v)
    return out if has_field else None


def _parse_msg_body_element(raw: bytes) -> dict[str, str]:
    msg_type = ""
    text = ""
    url = ""
    file_name = ""
    for f, _w, v in pb_decode(raw):
        if f == 1:
            msg_type = _as_str(v)
        elif f == 2:
            content_raw = _as_bytes(v)
            for cf, _cw, cv in pb_decode(content_raw):
                if cf == 1:
                    text = _as_str(cv)
                elif cf == 10:
                    url = _as_str(cv)
                elif cf == 12:
                    file_name = _as_str(cv)
    el: dict[str, str] = {"msg_type": msg_type}
    if text:
        el["text"] = text
    if url:
        el["url"] = url
    if file_name:
        el["file_name"] = file_name
    return el


def parse_inbound_push(data: bytes) -> dict[str, Any]:
    """Decode an ``InboundMessagePush`` payload to a snake_case dict."""
    out: dict[str, Any] = {
        "callback_command": "",
        "from_account": "",
        "to_account": "",
        "sender_nickname": "",
        "group_code": "",
        "msg_seq": 0,
        "msg_id": "",
        "msg_body": [],
        "claw_msg_type": 0,
    }
    for f, _w, v in pb_decode(data):
        if f == 1:
            out["callback_command"] = _as_str(v)
        elif f == 2:
            out["from_account"] = _as_str(v)
        elif f == 3:
            out["to_account"] = _as_str(v)
        elif f == 4:
            out["sender_nickname"] = _as_str(v)
        elif f == 6:
            out["group_code"] = _as_str(v)
        elif f == 8:
            out["msg_seq"] = _as_int(v)
        elif f == 12:
            out["msg_id"] = _as_str(v)
        elif f == 13:
            out["msg_body"].append(_parse_msg_body_element(_as_bytes(v)))
        elif f == 18:
            out["claw_msg_type"] = _as_int(v)
    return out


# ----------------------------------------------------------------- helpers


def _random_u32() -> int:
    return uuid.uuid4().int & 0xFFFFFFFF


# =========================================================================
# sign-token
# =========================================================================

_BJ_TZ = timezone(timedelta(hours=8))
_TOKEN_REFRESH_MARGIN_S = 300  # refresh 5 min before expiry
_SIGN_TOKEN_MAX_ATTEMPTS = 3
_SIGN_TOKEN_RETRY_DELAY_S = 1.0
_SIGN_TOKEN_THROTTLE_CODE = 10099


def _make_signature(nonce: str, timestamp: str, app_key: str, app_secret: str) -> str:
    plain = nonce + timestamp + app_key + app_secret
    return hmac.new(app_secret.encode(), plain.encode(), hashlib.sha256).hexdigest()


def _make_timestamp(now: datetime | None = None) -> str:
    bj = now if now is not None else datetime.now(_BJ_TZ)
    bj = bj.replace(tzinfo=_BJ_TZ) if bj.tzinfo is None else bj.astimezone(_BJ_TZ)
    return bj.strftime("%Y-%m-%dT%H:%M:%S+08:00")


async def fetch_sign_token(
    http: aiohttp.ClientSession,
    config: YuanbaoConfig,
    *,
    bot_version: str,
) -> dict[str, Any]:
    """POST ``/api/v5/robotLogic/sign-token`` and return ``data`` on code==0.

    Retries on transient throttle code (10099) up to 3 times.
    """
    url = f"https://{config.api_domain}/api/v5/robotLogic/sign-token"
    headers = {
        "Content-Type": "application/json",
        "X-AppVersion": _PLUGIN_VERSION,
        "X-OperationSystem": "linux",
        "X-Instance-Id": "16",
        "X-Bot-Version": bot_version,
    }
    last_exc: Exception | None = None
    for attempt in range(_SIGN_TOKEN_MAX_ATTEMPTS):
        nonce = uuid.uuid4().hex
        timestamp = _make_timestamp()
        signature = _make_signature(nonce, timestamp, config.app_key, config.app_secret)
        body = {
            "app_key": config.app_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "signature": signature,
        }
        try:
            async with http.post(url, json=body, headers=headers) as resp:
                payload = await resp.json()
        except Exception as exc:
            last_exc = exc
            logger.warning("sign-token network error (attempt=%d): %s", attempt + 1, exc)
            await asyncio.sleep(_SIGN_TOKEN_RETRY_DELAY_S)
            continue
        code = payload.get("code")
        if code == 0:
            data = payload.get("data") or {}
            if not isinstance(data, dict):
                raise RuntimeError(f"sign-token data not a dict: {payload!r}")
            return data
        if code == _SIGN_TOKEN_THROTTLE_CODE:
            logger.warning(
                "sign-token throttled (code=%s), retrying (attempt=%d)",
                code,
                attempt + 1,
            )
            await asyncio.sleep(_SIGN_TOKEN_RETRY_DELAY_S)
            continue
        raise RuntimeError(f"sign-token failed: code={code} msg={payload.get('msg')}")
    raise RuntimeError(f"sign-token failed after {_SIGN_TOKEN_MAX_ATTEMPTS} attempts: {last_exc}")


# =========================================================================
# Channel
# =========================================================================

# Head.cmdType values
_CMD_TYPE_REQUEST = 0
_CMD_TYPE_RESPONSE = 1
_CMD_TYPE_PUSH = 2

# AuthBind success / retry codes (see conn.json RetCode)
_AUTH_ALREADY_CODE = 41101
_AUTH_TOKEN_REFRESH_CODES = {41103, 41104, 41108}

# Close codes that should never trigger reconnect (per JS client.js)
_NO_RECONNECT_CLOSE_CODES = {4012, 4013, 4014, 4018, 4019, 4021}

# Reconnect backoff (seconds) — cycled
_RECONNECT_DELAYS = (1, 2, 5, 10, 30, 60)

# Send timeout for business requests
_SEND_TIMEOUT_S = 30.0

# Heartbeat config
_DEFAULT_HEARTBEAT_INTERVAL_S = 30
_FIRST_HEARTBEAT_DELAY_S = 5.0
_HEARTBEAT_TIMEOUT_THRESHOLD = 2

_PLUGIN_VERSION = "2.17.0"
_BOT_VERSION = "octop/0.1"


class YuanbaoChannel(BaseChannel):
    """Tencent Yuanbao bot channel over WSS + hand-rolled protobuf."""

    channel_type = "yuanbao"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: YuanbaoConfig,
        channel_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            config=config,
        )
        self._config = config
        self._running = False

        # WebSocket state
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_interval: float = float(_DEFAULT_HEARTBEAT_INTERVAL_S)
        self._heartbeat_ack_received = True
        self._heartbeat_timeout_count = 0

        # Sign-token state
        self._bot_id: str = ""
        self._source: str = ""
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

        # Pending business requests keyed by msgId
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

        # Reconnect backoff index (cycles through _RECONNECT_DELAYS)
        self._reconnect_idx = 0

    # ----------------------------------------------------- lifecycle

    async def start(self) -> None:
        self._running = True
        await self._ensure_http()
        self._ws_task = asyncio.create_task(self._ws_loop(), name="yuanbao-ws-loop")
        logger.info("YuanbaoChannel starting: app_key=%s", self._config.app_key)

    async def stop(self) -> None:
        self._running = False
        for task_attr in ("_heartbeat_task", "_ws_task"):
            task: asyncio.Task[None] | None = getattr(self, task_attr)
            if task is not None and not task.done():
                task.cancel()
        for task_attr in ("_heartbeat_task", "_ws_task"):
            task = getattr(self, task_attr)
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            setattr(self, task_attr, None)

        ws = self._ws
        if ws is not None and not ws.closed:
            with contextlib.suppress(Exception):
                await ws.close()
        self._ws = None

        for fut in list(self._pending.values()):
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        await self._close_http()
        logger.info("YuanbaoChannel stopped")

    # ----------------------------------------------------- ws reconnect loop

    async def _ws_loop(self) -> None:
        while self._running:
            close_code: int | None = None
            try:
                close_code = await self._run_one_session()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("YuanbaoChannel session crashed")
            if not self._running:
                break
            if close_code is not None and close_code in _NO_RECONNECT_CLOSE_CODES:
                logger.error("YuanbaoChannel close_code=%s — not reconnecting", close_code)
                break
            delay = _RECONNECT_DELAYS[self._reconnect_idx % len(_RECONNECT_DELAYS)]
            self._reconnect_idx += 1
            # Force token refresh on next connect (covers 41103/41104/41108).
            self._token = ""
            self._token_expires_at = 0.0
            logger.info("YuanbaoChannel reconnecting in %.1fs", delay)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

    async def _run_one_session(self) -> int | None:
        http = await self._ensure_http()
        # Always pull a fresh token on connect — avoids stale-token auth failures.
        await self._refresh_token()
        if not self._token or not self._bot_id:
            raise RuntimeError("sign-token returned empty token or bot_id")

        ws_url = self._config.ws_url
        logger.info("YuanbaoChannel connecting to %s", ws_url)
        async with http.ws_connect(ws_url) as ws:
            self._ws = ws
            self._heartbeat_ack_received = True
            self._heartbeat_timeout_count = 0

            await self._send_auth_bind(ws)

            close_code: int | None = None
            async for msg in ws:
                if not self._running:
                    break
                if msg.type == aiohttp.WSMsgType.BINARY:
                    await self._handle_frame(msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    close_code = ws.close_code
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning("YuanbaoChannel ws error: %s", ws.exception())
                    break

            self._ws = None
            if self._heartbeat_task is not None and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                self._heartbeat_task = None
            return close_code if close_code is not None else ws.close_code

    async def _send_auth_bind(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        msg_id = uuid.uuid4().hex
        frame = build_auth_bind(
            self._bot_id,
            self._source,
            self._token,
            msg_id,
            app_version=_PLUGIN_VERSION,
            bot_version=_BOT_VERSION,
        )
        await ws.send_bytes(frame)
        logger.info("YuanbaoChannel auth-bind sent msgId=%s", msg_id)

    # ----------------------------------------------------- frame dispatch

    async def _handle_frame(self, raw: bytes) -> None:
        try:
            conn_msg = parse_conn_msg(raw)
        except Exception:
            logger.warning("YuanbaoChannel failed to parse frame (%d bytes)", len(raw))
            return
        head = conn_msg["head"]
        cmd_type = head.get("cmdType")
        data = _as_bytes(conn_msg["data"])
        if cmd_type == _CMD_TYPE_RESPONSE:
            await self._on_response(head, data)
        elif cmd_type == _CMD_TYPE_PUSH:
            await self._on_push(head, data)
        else:
            logger.debug(
                "YuanbaoChannel ignoring cmdType=%s cmd=%s",
                cmd_type,
                head.get("cmd"),
            )

    async def _on_response(self, head: dict[str, Any], data: bytes) -> None:
        cmd = head.get("cmd")
        if cmd == "auth-bind":
            await self._on_auth_bind_response(data)
            return
        if cmd == "ping":
            self._on_ping_response(data)
            return
        # Business response — match by msgId
        msg_id = _as_str(head.get("msgId", ""))
        fut = self._pending.pop(msg_id, None)
        if fut is None or fut.done():
            logger.debug("YuanbaoChannel unmatched response cmd=%s msgId=%s", cmd, msg_id)
            return
        try:
            rsp = parse_send_message_rsp(data)
        except Exception as exc:
            fut.set_exception(exc)
            return
        fut.set_result(rsp)

    async def _on_auth_bind_response(self, data: bytes) -> None:
        try:
            rsp = parse_auth_bind_rsp(data)
        except Exception:
            logger.exception("YuanbaoChannel auth-bind decode failed")
            return
        code = int(rsp.get("code", 0) or 0)
        logger.info(
            "YuanbaoChannel auth-bind rsp: code=%s connectId=%s",
            code,
            rsp.get("connectId"),
        )
        if code in (0, _AUTH_ALREADY_CODE):
            # Reset backoff on clean auth.
            self._reconnect_idx = 0
            if self._heartbeat_task is not None and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name="yuanbao-heartbeat"
            )
            return
        if code in _AUTH_TOKEN_REFRESH_CODES:
            logger.warning(
                "YuanbaoChannel auth-bind token invalid (code=%s) — closing for reconnect",
                code,
            )
            self._token = ""
            self._token_expires_at = 0.0
            await self._close_ws_safe()
            return
        logger.error(
            "YuanbaoChannel auth-bind failed: code=%s msg=%s",
            code,
            rsp.get("message"),
        )
        await self._close_ws_safe()

    def _on_ping_response(self, data: bytes) -> None:
        self._heartbeat_ack_received = True
        self._heartbeat_timeout_count = 0
        try:
            rsp = parse_ping_rsp(data)
        except Exception:
            rsp = {}
        interval = rsp.get("heartInterval")
        if isinstance(interval, int) and interval > 1:
            self._heartbeat_interval = float(interval)
            logger.debug("YuanbaoChannel heartbeat interval updated: %ss", interval)

    async def _on_push(self, head: dict[str, Any], data: bytes) -> None:
        # ACK first if requested.
        if head.get("needAck"):
            ws = self._ws
            if ws is not None and not ws.closed:
                try:
                    await ws.send_bytes(build_push_ack(head))
                except Exception:
                    logger.warning("YuanbaoChannel failed to send push ACK", exc_info=True)

        cmd = head.get("cmd")
        if cmd == "kickout":
            logger.warning("YuanbaoChannel kicked out — closing for reconnect")
            await self._close_ws_safe()
            return

        # Try PushMsg wrapper first; fall back to raw ConnMsg.data on
        # misparse (InboundMessagePush fields 1/2/3/4 can look like
        # PushMsg.cmd/module/msgId/data on the wire).
        push = parse_push_msg(data)
        inbound: dict[str, Any] | None = None
        if push is not None and (push.get("cmd") or push.get("module")):
            push_data = _as_bytes(push.get("data"))
            if push_data:
                try:
                    candidate = parse_inbound_push(push_data)
                except Exception:
                    candidate = None
                # A real wrapped InboundMessagePush carries a callback_command
                # or msg_body. If decode yields nothing useful, fall back.
                if candidate is not None and (
                    candidate.get("msg_body") or candidate.get("callback_command")
                ):
                    inbound = candidate
        if inbound is None:
            try:
                inbound = parse_inbound_push(data)
            except Exception:
                logger.warning(
                    "YuanbaoChannel failed to decode InboundMessagePush",
                    exc_info=True,
                )
                return

        # Anti-loop: ignore our own outbound echoes.
        if self._bot_id and inbound.get("from_account") == self._bot_id:
            return

        self.enqueue(inbound)

    async def _heartbeat_loop(self) -> None:
        first = True
        try:
            while self._running:
                delay = (
                    _FIRST_HEARTBEAT_DELAY_S if first else max(1.0, self._heartbeat_interval - 1)
                )
                first = False
                await asyncio.sleep(delay)
                if not self._running:
                    return
                if not self._heartbeat_ack_received:
                    self._heartbeat_timeout_count += 1
                    if self._heartbeat_timeout_count >= _HEARTBEAT_TIMEOUT_THRESHOLD:
                        logger.warning(
                            "YuanbaoChannel heartbeat timeout %d times — reconnecting",
                            self._heartbeat_timeout_count,
                        )
                        self._heartbeat_timeout_count = 0
                        await self._close_ws_safe()
                        return
                    continue
                ws = self._ws
                if ws is None or ws.closed:
                    return
                msg_id = uuid.uuid4().hex
                try:
                    await ws.send_bytes(build_ping(msg_id))
                except Exception:
                    logger.warning("YuanbaoChannel failed to send ping", exc_info=True)
                    return
                self._heartbeat_ack_received = False
        except asyncio.CancelledError:
            pass

    async def _close_ws_safe(self) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            return
        try:
            await ws.close()
        except Exception:
            logger.warning("YuanbaoChannel failed to close ws", exc_info=True)

    # ----------------------------------------------------- sign-token

    async def _refresh_token(self) -> None:
        async with self._token_lock:
            now = time.time()
            if (
                self._token
                and self._token_expires_at
                and now < self._token_expires_at - _TOKEN_REFRESH_MARGIN_S
            ):
                return
            http = await self._ensure_http()
            data = await fetch_sign_token(http, self._config, bot_version=_BOT_VERSION)
            self._bot_id = str(data.get("bot_id") or "")
            self._source = str(data.get("source") or "bot")
            self._token = str(data.get("token") or "")
            try:
                duration = int(data.get("duration") or 0)
            except (TypeError, ValueError):
                duration = 0
            if duration <= 0:
                duration = 7200
            self._token_expires_at = now + duration
            if not self._bot_id or not self._token:
                raise RuntimeError("sign-token response missing bot_id or token")
            logger.info(
                "YuanbaoChannel token refreshed: bot_id=%s duration=%ss",
                self._bot_id,
                duration,
            )

    # ----------------------------------------------------- outbound

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        await self._ensure_http()
        await self._refresh_token()
        ws = self._ws
        if ws is None or ws.closed:
            raise RuntimeError("YuanbaoChannel cannot send — ws is closed")

        meta = subject.metadata or {}
        group_code = ""
        if subject.chat_type == "group":
            group_code = str(meta.get("group_code") or subject.subject_id)
        elif meta.get("group_code"):
            group_code = str(meta.get("group_code"))

        msg_id = uuid.uuid4().hex
        if group_code:
            frame = build_send_group_message(msg_id, self._bot_id, group_code, text)
        else:
            frame = build_send_c2c_message(msg_id, self._bot_id, subject.subject_id, text)

        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await ws.send_bytes(frame)
        except Exception:
            self._pending.pop(msg_id, None)
            raise

        try:
            rsp = await asyncio.wait_for(fut, timeout=_SEND_TIMEOUT_S)
        except TimeoutError:
            self._pending.pop(msg_id, None)
            logger.error("YuanbaoChannel send timed out msgId=%s", msg_id)
            return
        code = int(rsp.get("code", 0) or 0)
        if code != 0:
            logger.error(
                "YuanbaoChannel send failed: code=%s msg=%s",
                code,
                rsp.get("message"),
            )

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        for part in parts:
            if isinstance(part, TextContent):
                await self._send_text(subject, part.text)
                continue
            # Minimal fallback for non-text parts.
            url = getattr(part, "url", "") or ""
            label = type(part).__name__
            marker = f"[{label}] {url}".strip()
            await self._send_text(subject, marker)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        await self._send_content(subject, [media])

    # ----------------------------------------------------- inbound parsing

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload
        if not isinstance(raw_payload, dict):
            raise ValueError(f"YuanbaoChannel.parse_inbound expects dict, got {type(raw_payload)}")
        data = raw_payload
        from_account = _as_str(data.get("from_account"))
        group_code = _as_str(data.get("group_code"))
        sender_nickname = _as_str(data.get("sender_nickname"))
        msg_id = _as_str(data.get("msg_id"))
        msg_seq = int(data.get("msg_seq") or 0)
        claw_msg_type = int(data.get("claw_msg_type") or 0)
        is_group = bool(group_code) or claw_msg_type == 1

        subject_id = group_code or from_account
        chat_type = "group" if is_group else "direct"

        content_parts: list[ContentPart] = []
        for el in data.get("msg_body") or []:
            if not isinstance(el, dict):
                continue
            msg_type = _as_str(el.get("msg_type"))
            text = _as_str(el.get("text"))
            url = _as_str(el.get("url"))
            file_name = _as_str(el.get("file_name"))
            content_parts.append(self._content_part_from_element(msg_type, text, url, file_name))
        if not content_parts:
            content_parts.append(TextContent(text=""))

        metadata: dict[str, Any] = {
            "msg_id": msg_id,
            "from_account": from_account,
            "group_code": group_code,
            "sender_nickname": sender_nickname,
            "msg_seq": msg_seq,
        }
        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=subject_id,
                chat_type=chat_type,
                metadata=dict(metadata),
            ),
            channel_session_id=msg_id or subject_id,
            content=content_parts,
            metadata=metadata,
            timestamp=time.time(),
        )

    @staticmethod
    def _content_part_from_element(
        msg_type: str, text: str, url: str, file_name: str
    ) -> TextContent:
        """Map a ``MsgBodyElement`` to a ``ContentPart`` (text-only minimal impl).

        Non-text elements degrade to a localized text marker so the agent has
        something to reason about. ``TIMTextElem`` carries the real text.
        """
        if msg_type == "TIMTextElem":
            return TextContent(text=text)
        lower = msg_type.lower()
        if "image" in lower:
            return TextContent(text=f"[图片] {url}".strip())
        if "video" in lower:
            return TextContent(text=f"[视频] {url}".strip())
        if "audio" in lower or "sound" in lower:
            return TextContent(text=f"[语音] {url}".strip())
        if "file" in lower:
            label = f"[文件] {file_name}".strip()
            if url:
                label = f"{label} {url}".strip()
            return TextContent(text=label)
        if text:
            return TextContent(text=text)
        if url:
            return TextContent(text=url)
        return TextContent(text=f"[{msg_type or 'unknown'}]")


# =========================================================================
# Probe helper (no registration)
# =========================================================================


async def probe_yuanbao(config: YuanbaoConfig) -> None:
    """Verify credentials end-to-end without registering a channel.

    Steps: credentials check → sign-token → WSS connect → auth-bind → close.
    Raises ``ChannelCredentialsError`` on missing fields, ``RuntimeError``
    on any other failure.
    """
    missing = config.missing_credentials()
    if missing:
        raise ChannelCredentialsError("yuanbao", missing)

    http = aiohttp.ClientSession()
    try:
        data = await fetch_sign_token(http, config, bot_version=_BOT_VERSION)
        bot_id = str(data.get("bot_id") or "")
        source = str(data.get("source") or "bot")
        token = str(data.get("token") or "")
        if not bot_id or not token:
            raise RuntimeError("sign-token response missing bot_id or token")

        auth_msg_id = uuid.uuid4().hex
        auth_frame = build_auth_bind(
            bot_id,
            source,
            token,
            auth_msg_id,
            app_version=_PLUGIN_VERSION,
            bot_version=_BOT_VERSION,
        )

        deadline = asyncio.get_running_loop().time() + 15.0
        authed = False
        async with http.ws_connect(config.ws_url) as ws:
            await ws.send_bytes(auth_frame)
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
                except TimeoutError:
                    break
                if msg.type != aiohttp.WSMsgType.BINARY:
                    if msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        raise RuntimeError(f"ws closed during auth-bind: code={ws.close_code}")
                    continue
                try:
                    conn_msg = parse_conn_msg(msg.data)
                except Exception:
                    continue
                head = conn_msg["head"]
                if head.get("cmd") == "auth-bind" and head.get("cmdType") == _CMD_TYPE_RESPONSE:
                    rsp = parse_auth_bind_rsp(_as_bytes(conn_msg["data"]))
                    code = int(rsp.get("code", 0) or 0)
                    if code in (0, _AUTH_ALREADY_CODE):
                        authed = True
                    else:
                        raise RuntimeError(
                            f"auth-bind failed: code={code} msg={rsp.get('message')}"
                        )
                    break
        if not authed:
            raise RuntimeError("auth-bind timed out")
    finally:
        await http.close()
