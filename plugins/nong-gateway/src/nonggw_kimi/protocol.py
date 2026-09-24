# 出处：本文件从 kimi-claw-py 的 kimi_client.py 原样移植（2026-09-15）。
# 那个实现经真流量验证（订阅流 / 游标续传 / 流式出站 / 手写 WS 帧），本文件一行逻辑未改。
# 改这里 = 改协议：务必让本包的 tests/test_kimi_channel.py 与 kimi-claw-py 自检一起跑。
# 协议依据与两处设计理由（订阅不走 http.client、写必须串行）见下面的模块 docstring。

"""Kimi Claw IM 协议层（纯 stdlib，零第三方依赖）。

这个模块只做一件事：把月之暗面 Kimi Claw 的云端 IM 协议封好，让上层
（bridge.py / Octop 插件壳）只看到「订阅事件流」「查历史消息」「流式发一条回复」三种动作。

协议依据（全部来自官方 npm 包 kimi-claw@0.27.1 的 dist，未改一行，路径见 README）：

  1. IM 基址 = 把 kimiapiHost（缺省 https://www.kimi.com/api-claw）的路径
     /api-claw 换成 /api-ws（service/static-im-rpc/client.js: resolveStaticImRpcBaseUrl）。
  2. 入站是 Connect 协议的**服务器流**：POST {base}/kimi.gateway.im.v1.IMService/Subscribe，
     content-type application/connect+json; charset=utf-8，accept application/connect+json，
     connect-protocol-version: 1。请求体与响应体都是 Connect 封包：
     flags(1B) + 长度(4B 大端) + payload(JSON)。见 im/rpc-protocol.js 的
     encodeConnectEnvelope 与 createConnectEnvelopeReader（本文件两个方向各重写一份）。
  3. 单次调用（ListMessages / SendMessage / GetMe / UpdateBotMeta）是普通 POST + 裸 JSON
     （content-type application/json; charset=utf-8），body 是 protojson。
  4. 出站流式走 WebSocket {base}/im/send-message/ws：首帧 {"chatId":...}，之后
     {"block":{op,mask,block}}，最后 {"end":{}}；官方每 10s 一个 {"ping":{}} 保活
     （rpc-protocol.js: setInterval(..., 1e4)。二手资料有写 15s 的，以官方包为准）。
  5. 字段名/类型/枚举**不是反推出来的**：官方包 dist/src/im/proto/generated/**/_pb.js 里
     每个 fileDesc("<base64>") 解出来就是完整的 FileDescriptorProto。protojson 线格式用
     lowerCamelCase 字段名、枚举用值名、oneof 直接以字段名落一层、FieldMask 是逗号分隔串。

为什么自己写而不引 aiohttp / websockets：插件形态要跟 Octop 一起常驻，独立服务形态要能在
只有系统 python3 的机器上跑；两条都成立的前提是没有第三方依赖。WS 只用到「客户端 + 文本帧 +
掩码 + ping/pong」，stdlib 的 socket/ssl/base64/hashlib 就够（见 WsConn）。

两处必须知道的设计理由：
  * 订阅流**不走 http.client**。HTTPResponse.read(n) 在 chunked 编码下会等凑满 n 字节才返回
    （CPython _safe_read 语义），而一个事件帧只有两三百字节——用它做长连接事件流会表现为
    「收到消息但半天不吐」。所以订阅用 _RawStream：自己发请求头、自己拆 chunked、
    每次只等到「有一块数据」为止。
  * 一条流式回复的所有 socket 写必须串行。官方是单条 async 队列 drain；我们这里保活 ping 来自
    独立线程、业务帧来自 worker 线程，所以 WsConn 的所有写都过一把锁。少了它，ping 与文本帧
    会在同一条 TCP 流上交错撕帧。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import Any, Callable, Iterable, Iterator

# --------------------------------------------------------------------------- #
# 常量（值抄自官方包，出处写在注释里）
# --------------------------------------------------------------------------- #

DEFAULT_KIMIAPI_HOST = "https://www.kimi.com/api-claw"  # static-im-rpc/client.js
AUTH_HEADER = "X-Kimi-Bot-Token"  # proto/generated/index.js: IM_AUTH_HEADER
CLAW_VERSION_HEADER = "X-Kimi-Claw-Version"
OPENCLAW_VERSION_HEADER = "X-Kimi-OpenClaw-Version"
SERVICE_NAME = "kimi.gateway.im.v1.IMService"
SUBSCRIBE_HEADER_DEFAULT_CHAT = "x-kimi-claw-default-chat"  # rpc-protocol.js
SUBSCRIBE_HEADER_BOT_REGION = "x-kimi-claw-bot-region"  # errors/lifecycle-error-hints.js
CONNECT_JSON = "application/connect+json"
JSON_CT = "application/json; charset=utf-8"
CONNECT_STREAMING_JSON_CT = "application/connect+json; charset=utf-8"
CONNECT_PROTOCOL_VERSION = "1"
FLAG_COMPRESSED = 1
FLAG_END_STREAM = 2

METHODS: dict[str, str] = {
    "Subscribe": f"/{SERVICE_NAME}/Subscribe",
    "SendMessage": f"/{SERVICE_NAME}/SendMessage",
    "GetMessages": f"/{SERVICE_NAME}/GetMessages",
    "ListMessages": f"/{SERVICE_NAME}/ListMessages",
    "GetMe": f"/{SERVICE_NAME}/GetMe",
    "UpdateBotMeta": f"/{SERVICE_NAME}/UpdateBotMeta",
    "ListRooms": f"/{SERVICE_NAME}/ListRooms",
    "GetRoom": f"/{SERVICE_NAME}/GetRoom",
    "ListMembers": f"/{SERVICE_NAME}/ListMembers",
}
SEND_MESSAGE_WS_PATH = "/im/send-message/ws"

# 订阅流心跳阈值（subscribe-runtime.js: expectedPingIntervalMs=1e4, pingTimeoutMs=3e4）
SUBSCRIBE_PING_TIMEOUT_SEC = 30.0
# 出站 WS 保活间隔（rpc-protocol.js sendMessageStream 的 setInterval 1e4）
WS_KEEPALIVE_SEC = 10.0

_MENTION_RE = re.compile(r"<@[^>\n|]+\|[^>\n]+>")


def im_base_from(kimiapi_host: str) -> str:
    """https://www.kimi.com/api-claw -> https://www.kimi.com/api-ws（去尾斜杠）。"""
    host = (kimiapi_host or DEFAULT_KIMIAPI_HOST).strip().rstrip("/")
    parts = urllib.parse.urlsplit(host)
    path = parts.path
    if path == "/api-claw" or path.startswith("/api-claw/"):
        path = "/api-ws" + path[len("/api-claw") :]
        host = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    return host.rstrip("/")


def ws_url_from(im_base: str, path: str = SEND_MESSAGE_WS_PATH) -> str:
    """{im_base}/im/send-message/ws，scheme 换成 ws/wss。"""
    parts = urllib.parse.urlsplit(im_base.rstrip("/") + path)
    scheme = {"https": "wss", "http": "ws"}.get(parts.scheme, parts.scheme)
    return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path, "", ""))


# --------------------------------------------------------------------------- #
# Connect 封包（纯函数，自检直接断言）
# --------------------------------------------------------------------------- #

def encode_envelope(payload: Any, flags: int = 0) -> bytes:
    """dict -> Connect 封包字节，与官方 encodeConnectEnvelope 逐字节同形。"""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return bytes([flags & 0xFF]) + struct.pack(">I", len(body)) + body


def decode_envelope(raw: bytes | bytearray) -> tuple[int, Any, str]:
    """封包字节 -> (flags, payload, payload_text)。空 payload 按 protojson 惯例当 null。"""
    if len(raw) < 5:
        raise ValueError(f"Connect 封包不足 5 字节：{len(raw)}")
    flags = raw[0]
    (size,) = struct.unpack(">I", bytes(raw[1:5]))
    if len(raw) < 5 + size:
        raise ValueError(f"Connect 封包不完整：声明 {size} 字节，实有 {len(raw) - 5}")
    if flags & FLAG_COMPRESSED:
        raise ValueError("收到压缩的 Connect 封包，本客户端不支持（flags & 1）")
    body = bytes(raw[5 : 5 + size])
    text = body.decode("utf-8") if body else "null"
    return flags, json.loads(text or "null"), text


class EnvelopeStream:
    """从「每次返回若干字节的 read 函数」里切出封包序列。

    read() 返回 b'' 表示对端正常结束；异常原样冒泡。分包/粘包都在这里兜住——长连接上
    一个 TCP 段可能带两个封包，也可能一个封包被拆成两段。
    """

    def __init__(self, read: Callable[[int], bytes], max_frame: int = 64 * 1024 * 1024) -> None:
        self._read = read
        self._buf = bytearray()
        self._max_frame = max_frame

    def __iter__(self) -> Iterator[tuple[int, Any, str]]:
        while True:
            env = self.next_envelope()
            if env is None:
                return
            yield env

    def next_envelope(self):
        while True:
            if len(self._buf) >= 5:
                (size,) = struct.unpack(">I", bytes(self._buf[1:5]))
                if size > self._max_frame:
                    raise ValueError(f"Connect 封包过大：{size}")
                if len(self._buf) >= 5 + size:
                    chunk = bytes(self._buf[: 5 + size])
                    del self._buf[: 5 + size]
                    return decode_envelope(chunk)
            data = self._read(8192)
            if not data:
                if self._buf:
                    raise ValueError("流在半个封包处结束（对端异常断开）")
                return None
            self._buf.extend(data)


# --------------------------------------------------------------------------- #
# protojson 风格的请求/帧构造
# --------------------------------------------------------------------------- #

def drop_empty(d: dict[str, Any]) -> dict[str, Any]:
    """丢掉 None 与空串——protojson 的缺省值不落线，与官方 toJson 输出保持同形。"""
    return {k: v for k, v in d.items() if v is not None and v != ""}


# 出站块帧（SendMessageStreamRequest）。线格式 = protojson：payload 是 oneof，
# 直接以字段名落一层，所以 {"chatId":...} / {"block":{...}} / {"ping":{}} / {"end":{}}。

def frame_chat_start(chat_id: str) -> dict[str, Any]:
    return {"chatId": chat_id}


def frame_ping() -> dict[str, Any]:
    return {"ping": {}}


def frame_end() -> dict[str, Any]:
    return {"end": {}}


def _block_update(op: str, block: dict[str, Any], mask: list[str] | None) -> dict[str, Any]:
    upd: dict[str, Any] = {"op": op, "block": block}
    if mask:
        # FieldMask 的 protojson 形态是逗号分隔串
        upd["mask"] = ",".join(mask)
    return {"block": upd}


def frame_text_new(block_id: str, content: str) -> dict[str, Any]:
    """新建文本块：op=set 且**不带 mask**（官方 answerBlockId 为空时的首帧）。"""
    return _block_update("set", {"id": str(block_id), "text": {"content": content}}, None)


def frame_text(block_id: str, content: str, *, append: bool = True) -> dict[str, Any]:
    """文本增量帧。append=True 走 op=append（追到块尾），False 走 op=set（整段纠正）。

    两种都要带 mask=block.text.content——mask 告诉服务端改的是这块的哪个字段。
    """
    op = "append" if append else "set"
    return _block_update(op, {"id": str(block_id), "text": {"content": content}},
                         ["block.text.content"])


def frame_think(block_id: str, content: str, *, append: bool = True) -> dict[str, Any]:
    """思考块：与文本块同构，mask 走 block.think.content。"""
    op = "append" if append else "set"
    return _block_update(op, {"id": str(block_id), "think": {"content": content}},
                         ["block.think.content"])


def frame_tool(
    block_id: str,
    *,
    tool_call_id: str,
    name: str,
    args: str = "",
    is_error: bool = False,
    status: str = "STATUS_RUNNING",
    contents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """工具块。官方 pushToolStartBlock/pushToolResultBlock 都是 op=set 且不带 mask。"""
    tool: dict[str, Any] = {
        "toolCallId": tool_call_id,
        "name": name,
        "args": args or "",
        "isError": bool(is_error),
        "contents": contents if contents is not None else [],
        "status": status,
    }
    return _block_update("set", {"id": str(block_id), "tool": tool}, None)


def frame_resource_link(block_id: str, *, title: str, uri: str) -> dict[str, Any]:
    return _block_update(
        "set",
        {"id": str(block_id),
         "resourceLink": {"title": title, "uri": uri, "downloadUrl": uri,
                          "etag": "", "sizeBytes": 0}},
        None,
    )


def text_block(content: str, block_id: str = "0") -> dict[str, Any]:
    """单次 SendMessage 用的文本块。"""
    return {"id": str(block_id), "text": {"content": content}}


def resource_link_block(title: str, uri: str, block_id: str) -> dict[str, Any]:
    return {
        "id": str(block_id),
        "resourceLink": {"title": title, "uri": uri, "downloadUrl": uri,
                         "etag": "", "sizeBytes": 0},
    }


# --------------------------------------------------------------------------- #
# 错误
# --------------------------------------------------------------------------- #

class KimiError(RuntimeError):
    """协议层统一错误：带方法名/HTTP 状态/响应体片段，一眼看出哪一步坏了。"""

    def __init__(self, msg: str, *, method: str = "", status: int = 0, body: str = "") -> None:
        super().__init__(msg)
        self.method = method
        self.status = status
        self.body = body


class SubscriptionClosed(KimiError):
    """订阅流正常结束（对端关流）。上层重连，不当成致命错误。"""


class SubscriptionIdle(SubscriptionClosed):
    """超时窗口内一帧未到（含 ping）。官方同款判定：ping timeout forcing reconnect。"""


# --------------------------------------------------------------------------- #
# 裸 WebSocket 客户端（stdlib）
# --------------------------------------------------------------------------- #

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


@dataclass
class WsFrame:
    opcode: int
    payload: bytes

    @property
    def text(self) -> str:
        return self.payload.decode("utf-8", "replace")


def ws_accept_key(key_b64: str) -> str:
    """RFC 6455 握手校验值。自检用官方例子定值断言。"""
    return base64.b64encode(hashlib.sha1((key_b64 + _WS_GUID).encode()).digest()).decode()


def build_frame(opcode: int, payload: bytes, *, mask: bool = True, fin: bool = True) -> bytes:
    """构造一个 WS 帧。客户端->服务端必须掩码（RFC 6455 5.3）。

    注：head 必须是 **字节序列**（bytearray([v])）。写成 bytearray(v) 会拿到 v 个零字节，
    帧头变成全零——服务端会报 "continuation after FIN, bad MASK" 然直接断开（实测踩过）。
    """
    head = bytearray([0x80 | opcode if fin else opcode])
    n = len(payload)
    mb = 0x80 if mask else 0x00
    if n < 126:
        head.append(mb | n)
    elif n < 65536:
        head.append(mb | 126)
        head += struct.pack(">H", n)
    else:
        head.append(mb | 127)
        head += struct.pack(">Q", n)
    if mask:
        key = os.urandom(4)
        head += key
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return bytes(head) + payload


class FrameParser:
    """字节流 -> 帧序列；支持分片（continuation）与服务端掩码帧。"""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._frag_op = -1
        self._frag = bytearray()

    def feed(self, data: bytes) -> list[WsFrame]:
        self._buf.extend(data)
        out: list[WsFrame] = []
        while True:
            f = self._one()
            if f is None:
                return out
            out.append(f)

    def _one(self):
        buf = self._buf
        if len(buf) < 2:
            return None
        b0, b1 = buf[0], buf[1]
        fin, opcode = bool(b0 & 0x80), b0 & 0x0F
        masked = bool(b1 & 0x80)
        n = b1 & 0x7F
        need = 2
        if n == 126:
            need = 4
        elif n == 127:
            need = 10
        if len(buf) < need:
            return None
        ext = bytes(buf[2:need])
        if n == 126:
            (n,) = struct.unpack(">H", ext)
        elif n == 127:
            (n,) = struct.unpack(">Q", ext)
            if n > 64 * 1024 * 1024:
                raise ValueError(f"WS 帧过大：{n}")
        head = need
        key = b""
        if masked:
            if len(buf) < head + 4:
                return None
            key = bytes(buf[head : head + 4])
            head += 4
        if len(buf) < head + n:
            return None
        payload = bytes(buf[head : head + n])
        if masked:
            payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
        del buf[: head + n]
        if opcode == OP_CONT:
            self._frag.extend(payload)
            if fin:
                op, data = self._frag_op, bytes(self._frag)
                self._frag_op, self._frag = -1, bytearray()
                return WsFrame(op, data)
            return None
        if not fin:
            self._frag_op, self._frag = opcode, bytearray(payload)
            return None
        return WsFrame(opcode, payload)


def _tls_context(insecure: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _connect(host: str, port: int, secure: bool, timeout: float,
             insecure: bool = False) -> socket.socket:
    raw = socket.create_connection((host, port), timeout=timeout)
    if secure:
        raw = _tls_context(insecure).wrap_socket(raw, server_hostname=host)
    raw.settimeout(timeout)
    return raw


class WsConn:
    """最小 WS 客户端：握手 + 文本帧收发 + ping/pong + close。

    只覆盖本项目用得上的子集：不做扩展协商（所以也不会接受 permessage-deflate）、
    单协议、不做分片下的二进制流控。Octop 侧 ws:// 与 Kimi 侧 wss:// 共用这一套。
    """

    def __init__(self, url: str, *, headers: dict[str, str] | None = None,
                 timeout: float = 20.0, insecure: bool = False) -> None:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("ws", "wss"):
            raise ValueError(f"不是 ws(s) 地址：{url}")
        self.url = url
        self.secure = parts.scheme == "wss"
        self.host = parts.hostname or ""
        self.port = parts.port or (443 if self.secure else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        self.path = path
        self._headers = dict(headers or {})
        self._timeout = timeout
        self._insecure = insecure
        self._sock: socket.socket | None = None
        self._parser = FrameParser()
        self._write_lock = threading.Lock()
        self.closed = False

    def connect(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [
            f"GET {self.path} HTTP/1.1",
            f"Host: {self.host}:{self.port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        for k, v in self._headers.items():
            lines.append(f"{k}: {v}")
        self._sock = _connect(self.host, self.port, self.secure, self._timeout, self._insecure)
        self._sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        self._handshake(key)

    def _handshake(self, key: str) -> None:
        assert self._sock is not None
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise KimiError("WS 握手被对端关闭（地址或凭据不对）")
            buf.extend(chunk)
            if len(buf) > 65536:
                raise KimiError("WS 握手响应头过大")
        head, rest = bytes(buf).split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if len(lines) < 1 or " 101 " not in lines[0] + " ":
            raise KimiError(f"WS 握手失败：{lines[0] if lines else '空响应'}")
        hdrs: dict[str, str] = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            hdrs[k.strip().lower()] = v.strip()
        if hdrs.get("sec-websocket-accept") != ws_accept_key(key):
            raise KimiError("WS 握手 Sec-WebSocket-Accept 不匹配")
        self._parser.feed(rest)  # 握手包后面紧跟的数据先入解析器

    # ---- 写（全部串行）----
    def send_text(self, data: str) -> None:
        self._send(build_frame(OP_TEXT, data.encode("utf-8")))

    def send_ping(self, data: bytes = b"") -> None:
        self._send(build_frame(OP_PING, data))

    def _send(self, raw: bytes) -> None:
        if self._sock is None:
            raise KimiError("WS 未连接")
        with self._write_lock:
            if self.closed:
                raise KimiError("WS 已关闭")
            try:
                self._sock.sendall(raw)
            except OSError as exc:
                self.closed = True
                raise KimiError(f"WS 写失败：{exc}") from exc

    # ---- 读 ----
    def recv(self, timeout: float | None = None) -> WsFrame | None:
        """收一个业务帧（控制帧就地处理：ping 回 pong、close 判断）。

        返回 None 表示「超时没等到业务帧」或「连接已断」；调用方看 self.closed 区分。
        注意 deadline 语义：ping/pong 轮不到业务帧时不能无限等下去，否则会吞掉调用方
        给的超时窗口。
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.closed:
            if deadline is None:
                left: float | None = None
            else:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                left = max(0.01, left)
            frames = self._pull(left)
            if frames is None:
                self.closed = True
                return None
            for f in frames:
                if f.opcode == OP_PING:
                    try:
                        self._send(build_frame(OP_PONG, f.payload))
                    except KimiError:
                        return None
                elif f.opcode == OP_CLOSE:
                    self.closed = True
                    return None
                elif f.opcode in (OP_TEXT, OP_BINARY):
                    return f
        return None

    def _pull(self, timeout: float | None):
        assert self._sock is not None
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            data = self._sock.recv(65536)
        except (socket.timeout, TimeoutError):
            return []
        except OSError:
            return None
        finally:
            try:
                self._sock.settimeout(self._timeout)
            except OSError:
                pass
        if not data:
            return None
        return self._parser.feed(data)

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._send(build_frame(OP_CLOSE, struct.pack(">H", 1000)))
        except Exception:  # noqa: BLE001
            pass
        self.closed = True
        try:
            self._sock.close()
        finally:
            self._sock = None


# --------------------------------------------------------------------------- #
# 流式 HTTP（订阅专用，绕开 http.client 的「凑满才返回」）
# --------------------------------------------------------------------------- #

class _RespStream:
    """HTTP 响应体：自带缓冲，把 chunked / identity 统一成「要一点就给一点」的读。

    为什么不用 sock.makefile('rb')：CPython 的 SocketIO 一旦在某次读上超时，就把内部
    _readable 标记置假，之后任何读都抛 OSError("cannot read from timed out object")——
    等于「超时一次，这个文件对象就废了」。而长连接事件流必须能反复超时再继续（既要短轮询
    让 stop() 及时生效，又要 30s 空闲判定）。所以这里自己拿字节缓冲，recv 超时后缓冲区
    完好无损，下一轮接着用。
    """

    def __init__(self, sock: socket.socket, *, chunked: bool, remaining: int | None) -> None:
        self._s = sock
        self._buf = bytearray()
        self._chunked = chunked
        self._remaining = remaining      # identity 模式的剩余字节
        self._in_chunk = 0               # chunked 模式当前 chunk 剩余
        self._eof = False

    # ---- 底层填充 ----
    def _fill(self) -> bool:
        """True = 拿到了新字节；False = 对端结束。超时异常原样冒泡（缓冲区不受影响）。"""
        if self._eof:
            return False
        data = self._s.recv(65536)
        if not data:
            self._eof = True
            return False
        self._buf.extend(data)
        return True

    def readline(self) -> bytes:
        while True:
            i = self._buf.find(b"\n")
            if i >= 0:
                line = bytes(self._buf[: i + 1])
                del self._buf[: i + 1]
                return line
            if not self._fill():
                line = bytes(self._buf)
                del self._buf[:]
                return line

    def read(self, amt: int) -> bytes:
        """返回至少 1 字节；b'' 表示流结束。超时异常由调用方处理。

        注意 EOF 分支：`_fill()` 返回 False 表示对端已收尾，此时**必须**结束，
        否则 `_eof` 置真后 `_fill` 会永远立刻返回 False，这个循环就变成空转
        （实测代价：优雅停止变成 25s 后被 SIGKILL，且白烧 25s CPU）。
        """
        while True:
            got = self._take(amt)
            if got:
                return got
            if self._done:
                return b""
            if not self._fill():
                self._done = True
                return self._take(amt)   # 缓冲里也许还剩没被标 done 的字节

    _done = False

    def _take(self, amt: int) -> bytes:
        if self._chunked:
            return self._take_chunked(amt)
        if self._remaining is not None:
            if self._remaining <= 0:
                self._done = True
                return b""
            amt = min(amt, self._remaining)
        n = min(amt, len(self._buf))
        if n <= 0:
            if not self._chunked and self._remaining is None and self._eof:
                self._done = True
            return b""
        data = bytes(self._buf[:n])
        del self._buf[:n]
        if self._remaining is not None:
            self._remaining -= n
            if self._remaining <= 0:
                self._done = True
        return data

    def _take_chunked(self, amt: int) -> bytes:
        if self._in_chunk <= 0:
            i = self._buf.find(b"\n")
            if i < 0:
                return b""                      # 长度行还没到齐
            line = bytes(self._buf[: i + 1]).decode("latin-1").strip()
            del self._buf[: i + 1]
            try:
                self._in_chunk = int(line.split(";")[0].strip() or "0", 16)
            except ValueError as exc:
                raise KimiError(f"chunked 长度行非法：{line[:40]!r}") from exc
            if self._in_chunk == 0:
                while True:                      # 吃掉 trailer 与结尾 CRLF
                    j = self._buf.find(b"\n")
                    if j < 0:
                        if not self._buf:
                            self._done = True
                            return b""
                        break
                    line = bytes(self._buf[: j + 1])
                    del self._buf[: j + 1]
                    if line in (b"\r\n", b"\n"):
                        break
                self._done = True
                return b""
        n = min(amt, self._in_chunk, len(self._buf))
        if n <= 0:
            return b""
        data = bytes(self._buf[:n])
        del self._buf[:n]
        self._in_chunk -= n
        if self._in_chunk == 0:
            self._eat_crlf()
        return data

    def _eat_crlf(self) -> None:
        """chunk 数据后紧跟的 CRLF 必须吃掉，否则下一轮把它当长度行。"""
        while self._buf[:2] == b"\r\n" or (self._buf[:1] == b"\n"):
            n = 2 if self._buf[:2] == b"\r\n" else 1
            del self._buf[:n]
            return
        if len(self._buf) < 2 and not self._eof:
            try:
                self._fill()
            except (socket.timeout, TimeoutError, OSError):
                return
            while self._buf[:2] == b"\r\n" or (self._buf[:1] == b"\n"):
                n = 2 if self._buf[:2] == b"\r\n" else 1
                del self._buf[:n]
                return


class _RawStream:
    """手工 HTTP/1.1 客户端，只用于服务器流（见 ImClient.subscribe 的注释）。"""

    def __init__(self, url: str, *, timeout: float) -> None:
        parts = urllib.parse.urlsplit(url)
        self.secure = parts.scheme == "https"
        self.host = parts.hostname or ""
        self.port = parts.port or (443 if self.secure else 80)
        self.path = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def request(self, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, str], _RespStream]:
        lines = [f"POST {self.path} HTTP/1.1", f"Host: {self.host}", "Accept-Encoding: identity"]
        for k, v in headers.items():
            lines.append(f"{k}: {v}")
        lines.append(f"Content-Length: {len(body)}")
        self._sock = _connect(self.host, self.port, self.secure, self.timeout)
        self._sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + body)
        st = _RespStream(self._sock, chunked=False, remaining=None)
        status_line = st.readline()
        if not status_line:
            self.close()
            raise KimiError("订阅流：连接被对端关闭（未收到状态行）")
        bits = status_line.decode("latin-1").split()
        status = int(bits[1]) if len(bits) >= 2 else 0
        hdrs: dict[str, str] = {}
        while True:
            line = st.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            k, _, v = line.decode("latin-1").partition(":")
            hdrs[k.strip().lower()] = v.strip()
        chunked = "chunked" in hdrs.get("transfer-encoding", "").lower()
        remaining: int | None = None
        if not chunked and "content-length" in hdrs:
            try:
                remaining = int(hdrs["content-length"])
            except ValueError:
                remaining = None
        if status >= 400:
            text = ""
            try:
                st2 = _RespStream(self._sock, chunked=chunked, remaining=remaining)
                text = st2.read(600).decode("utf-8", "replace") if (remaining or chunked) else ""
            except (OSError, KimiError):
                pass
            self.close()
            raise KimiError(f"Subscribe 失败 status={status} body={text[:300]}",
                            method="Subscribe", status=status, body=text)
        st = _RespStream(self._sock, chunked=chunked, remaining=remaining)
        return status, hdrs, st

    def set_read_timeout(self, sec: float) -> None:
        """握手完成后把读超时改小：stop() 才不用等满一个 ping 周期。"""
        if self._sock is not None:
            try:
                self._sock.settimeout(sec)
            except OSError:
                pass

    def close(self) -> None:
        s, self._sock = self._sock, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# 门面
# --------------------------------------------------------------------------- #

@dataclass
class SubscribeEvent:
    """订阅流里的一帧（Event 的 protojson 形态）。"""

    payload: dict[str, Any]
    raw: str
    default_chat_id: str = ""
    bot_region: str = ""

    @property
    def id(self) -> str:
        return str(self.payload.get("id") or "")

    @property
    def case(self) -> str:
        for k in ("ping", "chatMessage", "reconnect", "typing", "disband", "botReport"):
            if k in self.payload:
                return k
        return "unknown"

    @property
    def chat_message(self) -> dict[str, Any] | None:
        v = self.payload.get("chatMessage")
        return v if isinstance(v, dict) else None

    @property
    def status(self) -> str:
        cm = self.chat_message
        return str((cm or {}).get("status") or "")

    def is_completed_message(self) -> bool:
        """只有 STATUS_COMPLETED 才该处理。

        官方同规则：im/event-filter.js 里 status!=COMPLETED 一律 shouldDispatch=false
        （STATUS_GENERATING 是「正在生成中的半截消息」，直接跳过）。
        """
        return self.case == "chatMessage" and self.status == "STATUS_COMPLETED"


class Subscription:
    """一条订阅：既能 for ev in sub 迭代，也能随时 close() 掐断阻塞中的读。"""

    def __init__(self, raw: "_RawStream", gen: Iterator[SubscribeEvent]) -> None:
        self._raw = raw
        self._gen = gen
        self.closed = False

    def __iter__(self) -> Iterator[SubscribeEvent]:
        return self._gen

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._raw.close()
        try:
            self._gen.close()      # 触发生成器里的 finally，两边都收
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class ImClient:
    """Kimi Claw 的 IM 门面：订阅 / 单次调用 / 流式出站。"""

    def __init__(self, bot_token: str, *, kimiapi_host: str = DEFAULT_KIMIAPI_HOST,
                 claw_version: str = "0.27.1", openclaw_version: str = "2026.4.14",
                 timeout: float = 30.0, on_log: Callable[[str], None] | None = None) -> None:
        if not bot_token:
            raise ValueError("缺少 bot token：请用 --token-file 或 config.json 提供")
        self.token = bot_token
        self.im_base = im_base_from(kimiapi_host)
        self.claw_version = claw_version
        self.openclaw_version = openclaw_version
        self.timeout = timeout
        self._log = on_log or (lambda m: None)
        parts = urllib.parse.urlsplit(self.im_base)
        self._host = parts.netloc
        self._prefix = parts.path.rstrip("/")  # 基址里的 /api-ws 必须跟着进请求路径，否则 nginx 404 到根

    # ---- 头 ----
    def headers(self, streaming: bool, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            AUTH_HEADER: self.token,
            CLAW_VERSION_HEADER: self.claw_version,
            OPENCLAW_VERSION_HEADER: self.openclaw_version,
        }
        if streaming:
            h["content-type"] = CONNECT_STREAMING_JSON_CT
            h["accept"] = CONNECT_JSON
            h["connect-protocol-version"] = CONNECT_PROTOCOL_VERSION
        else:
            h["content-type"] = JSON_CT
        h.update(extra or {})
        return h

    # ---- 单次调用 ----
    def call(self, method: str, payload: dict[str, Any] | None = None, *,
             timeout: float | None = None) -> dict[str, Any]:
        path = self._prefix + METHODS.get(method, f"/{SERVICE_NAME}/{method}")
        cls = HTTPSConnection if self.im_base.startswith("https") else HTTPConnection
        host = self._host
        if ":" in host:
            h, _, p = host.partition(":")
            conn: HTTPConnection = cls(h, int(p), timeout=timeout or self.timeout)
        else:
            conn = cls(host, timeout=timeout or self.timeout)
        body = json.dumps(drop_empty(payload or {}), ensure_ascii=False).encode("utf-8")
        try:
            conn.request("POST", path, body=body, headers=self.headers(False))
            resp = conn.getresponse()
            text = resp.read().decode("utf-8", "replace")
            if resp.status >= 400:
                raise KimiError(f"{method} 失败 status={resp.status} body={text[:300]}",
                                method=method, status=resp.status, body=text)
            try:
                return json.loads(text or "{}")
            except ValueError as exc:
                raise KimiError(f"{method} 返回不是合法 JSON：{text[:200]}",
                                method=method, status=resp.status, body=text) from exc
        except (OSError, ssl.SSLError) as exc:
            raise KimiError(f"{method} 请求失败：{type(exc).__name__}: {exc}", method=method) from exc
        finally:
            conn.close()

    def get_me(self) -> dict[str, Any]:
        """机器人自己的身份（id/shortId/name/type）——过滤自己发的消息要用。"""
        return self.call("GetMe", {})

    def list_messages(self, chat_id: str, *, page_size: int = 20,
                      start_message_id: str = "", end_message_id: str = "",
                      include_start: bool = True, include_end: bool = True,
                      page_token: str = "", backward: bool = True) -> list[dict[str, Any]]:
        """按窗口取会话消息。官方 im/inbound-message.js 就是靠它把事件变成正文。"""
        out = self.call("ListMessages", {
            "chatId": chat_id,
            "pageSize": page_size,
            "pageToken": page_token,
            "direction": "DIRECTION_BACKWARD" if backward else "DIRECTION_FORWARD",
            "startMessageId": start_message_id,
            "endMessageId": end_message_id,
            "includeStartMessage": include_start,
            "includeEndMessage": include_end,
        })
        return out.get("messages") or []

    def send_message(self, chat_id: str, blocks: list[dict[str, Any]]) -> str:
        """单次（非流式）发一条，返回 messageId——流式通道坏了时的兜底。"""
        out = self.call("SendMessage", {"chatId": chat_id, "blocks": blocks})
        return str(out.get("messageId") or "")

    def update_bot_meta(self, *, skills: Iterable[str] = (), platform: str = "") -> dict[str, Any]:
        uname = os.uname()
        return self.call("UpdateBotMeta", {
            "pluginVersion": self.claw_version,
            "openclawVersion": self.openclaw_version,
            "skills": list(skills),
            "platform": platform or f"kimi-claw-py/{uname.sysname.lower()}",
        })

    # ---- 订阅流 ----
    def subscribe(self, *, since_id: str = "", stop: threading.Event | None = None,
                  idle_timeout: float = SUBSCRIBE_PING_TIMEOUT_SEC,
                  extra_headers: dict[str, str] | None = None) -> "Subscription":
        """开一条订阅。返回 Subscription（可迭代、可 close）。

        为什么不是裸生成器：调用方要能在**正阻塞在读的时候**把它掐断。只置标志位的话，
        最坏要等满 idle_timeout（30s）才回到判定点，而那 30s 里订阅锁还被这条"已经不该
        存在的"连接占着——实测后果是面板停用插件后立刻起独立服务会启动失败。
        """
        url = self.im_base + METHODS["Subscribe"]
        raw = _RawStream(url, timeout=idle_timeout)
        body = encode_envelope({"sinceId": since_id} if since_id else {})
        return Subscription(raw, self._subscribe(raw, url, body, stop, idle_timeout, extra_headers))

    def _subscribe(self, raw: "_RawStream", url: str, body: bytes,
                   stop: threading.Event | None, idle_timeout: float,
                   extra_headers: dict[str, str] | None) -> Iterator[SubscribeEvent]:
        """服务器流生成器： yield SubscribeEvent；流断/哑连接抛 SubscriptionClosed。

        与官方 ImSubscribeRuntime 等价的三件事：
          1. 每个事件都带 id，要把它当游标持久化，重连时用 sinceId 续传（不丢消息）；
          2. 收到 reconnect 分支 => 服务端要求重连（本生成器直接结束，上层重开一条）；
          3. idle_timeout 内没有任何帧（含 ping）=> 哑连接，主动断开重连。
        """
        try:
            _status, hdrs, reader = raw.request(body, self.headers(True, extra_headers))
        except Exception:
            raw.close()
            raise
        default_chat = (hdrs.get(SUBSCRIBE_HEADER_DEFAULT_CHAT) or "").strip()
        region = (hdrs.get(SUBSCRIBE_HEADER_BOT_REGION) or "").strip()
        self._log(f"subscribe 已连接 default_chat_id={default_chat or '无'} region={region or '无'}")

        # 读超时用短轮询（2s 一档），空闲判定在 Python 侧按 last_rx 算。
        # 为什么不在 socket 上直接设 30s：那条 read 会一直阻塞到超时或有数据，
        # 于是 stop() 要等到下一个 ping 周期（约 10s）才被看见——实测优雅停止要 7.5s。
        poll = min(2.0, max(0.5, idle_timeout / 4.0))
        raw.set_read_timeout(poll)
        box = {"last_rx": time.monotonic()}

        def read(n: int) -> bytes:
            while True:
                if stop is not None and stop.is_set():
                    return b""
                try:
                    data = reader.read(n)
                except (socket.timeout, TimeoutError):
                    if time.monotonic() - box["last_rx"] > idle_timeout:
                        raise SubscriptionIdle(
                            f"{idle_timeout:.0f}s 内没有任何订阅帧（含 ping），按哑连接重连",
                            method="Subscribe")
                    continue
                except OSError as exc:
                    raise SubscriptionClosed(f"订阅流读失败：{type(exc).__name__}: {exc}",
                                             method="Subscribe") from exc
                if data:
                    box["last_rx"] = time.monotonic()
                return data

        try:
            for flags, payload, text in EnvelopeStream(read):
                if flags & FLAG_END_STREAM:
                    err = payload.get("error") if isinstance(payload, dict) else None
                    if isinstance(err, dict):
                        raise SubscriptionClosed(
                            "订阅流结束 code=%s message=%s" % (err.get("code"), err.get("message")),
                            method="Subscribe")
                    raise SubscriptionClosed("订阅流正常结束（end-of-stream）", method="Subscribe")
                if not isinstance(payload, dict):
                    continue
                ev = SubscribeEvent(payload=payload, raw=text,
                                    default_chat_id=default_chat, bot_region=region)
                yield ev
                if ev.case == "reconnect":
                    raise SubscriptionClosed("服务端下发 reconnect，需重连续传", method="Subscribe")
        finally:
            raw.close()

    # ---- 出站流式 ----
    def outbound(self, chat_id: str, *, connect_timeout: float = 20.0) -> "OutboundStream":
        return OutboundStream(self, chat_id, connect_timeout=connect_timeout)


# --------------------------------------------------------------------------- #
# 出站流式发送器
# --------------------------------------------------------------------------- #

class OutboundStream:
    """一次回复 = 一条 WS 连接。

    帧序：{"chatId":id} -> 若干 block -> {"end":{}}，期间每 WS_KEEPALIVE_SEC 一个 {"ping":{}}。
    块 id 从 "0" 递增（官方 send-message-stream.js: blockSeq=0 + nextBlockId()），
    答案块与思考块各自复用同一个 id 做 append。
    """

    def __init__(self, client: ImClient, chat_id: str, *,
                 connect_timeout: float = 20.0, wait_close_sec: float = 6.0) -> None:
        self.client = client
        self.chat_id = chat_id
        self._ws = WsConn(ws_url_from(client.im_base),
                          headers={AUTH_HEADER: client.token,
                                   CLAW_VERSION_HEADER: client.claw_version,
                                   OPENCLAW_VERSION_HEADER: client.openclaw_version},
                          timeout=connect_timeout)
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._pinger: threading.Thread | None = None
        self._seq = 0
        self._wait_close = wait_close_sec
        self.answer_block_id: str | None = None
        self.think_block_id: str | None = None
        self._tool_ids: dict[str, str] = {}
        self._started = False
        self.message_id = ""
        self.frames_sent = 0
        self.last_error = ""

    # ---- 生命周期 ----
    def __enter__(self) -> "OutboundStream":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.finish()

    def start(self) -> None:
        if self._started:
            return
        self._ws.connect()
        self._send(frame_chat_start(self.chat_id))
        self._started = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="kimi-ws-reader")
        self._reader.start()
        self._pinger = threading.Thread(target=self._ping_loop, daemon=True, name="kimi-ws-ping")
        self._pinger.start()

    def next_block_id(self) -> str:
        v = str(self._seq)
        self._seq += 1
        return v

    def finish(self) -> None:
        if not self._started:
            return
        try:
            self._send(frame_end())
        except KimiError as exc:
            self.last_error = str(exc)
        self._stop.set()
        deadline = time.time() + self._wait_close
        while time.time() < deadline and not self._ws.closed:
            time.sleep(0.05)
        self._ws.close()
        if self._reader:
            self._reader.join(timeout=1.0)

    # ---- 写 ----
    def _send(self, payload: dict[str, Any]) -> None:
        self._ws.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self.frames_sent += 1

    def push_text(self, piece: str) -> None:
        """流式追加正文：第一帧建块（op=set 无 mask），之后 op=append。"""
        if not piece:
            return
        if self.answer_block_id is None:
            self.answer_block_id = self.next_block_id()
            self._send(frame_text_new(self.answer_block_id, piece))
        else:
            self._send(frame_text(self.answer_block_id, piece, append=True))

    def rewrite_text(self, full: str) -> None:
        """整段纠正正文（op=set + mask）——分段攒够一起发时用。"""
        if self.answer_block_id is None:
            self.answer_block_id = self.next_block_id()
            self._send(frame_text_new(self.answer_block_id, full))
        else:
            self._send(frame_text(self.answer_block_id, full, append=False))

    def push_think(self, piece: str) -> None:
        if not piece:
            return
        if self.think_block_id is None:
            self.think_block_id = self.next_block_id()
        self._send(frame_think(self.think_block_id, piece, append=True))

    def push_tool(self, key: str, *, name: str, args: str = "", is_error: bool = False,
                  status: str = "STATUS_RUNNING",
                  contents: list[dict[str, Any]] | None = None) -> None:
        """工具过程块。同一个 key 复用块 id（官方 ensureToolBlockId 的做法）。"""
        bid = self._tool_ids.get(key)
        if bid is None:
            bid = self.next_block_id()
            self._tool_ids[key] = bid
        self._send(frame_tool(bid, tool_call_id=key, name=name, args=args, is_error=is_error,
                              status=status, contents=contents))

    # ---- 读与心跳 ----
    def _read_loop(self) -> None:
        while not self._stop.is_set() and not self._ws.closed:
            try:
                f = self._ws.recv(timeout=1.0)
            except KimiError as exc:
                self.last_error = str(exc)
                return
            if f is None:
                return
            if f.opcode != OP_TEXT:
                continue
            try:
                obj = json.loads(f.text)
            except ValueError:
                continue
            if isinstance(obj, dict):
                mid = obj.get("messageId")
                if mid:
                    self.message_id = str(mid)

    def _ping_loop(self) -> None:
        while not self._stop.wait(WS_KEEPALIVE_SEC):
            if self._ws.closed:
                return
            try:
                self._send(frame_ping())
            except KimiError as exc:
                self.last_error = str(exc)
                return


# --------------------------------------------------------------------------- #
# 入站解析辅助
# --------------------------------------------------------------------------- #

def message_text_of(msg: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """从一条 ChatMessage 取纯文本 + 附件链接。

    对应官方 mapImBlockToPromptBlock 的 text / resourceLink / file / image 四条分支；
    本桥只把文本交给 Octop，附件以链接提示的形式附在正文后（下载要另走 files 接口）。
    """
    inner = msg.get("message") if isinstance(msg.get("message"), dict) else msg
    texts: list[str] = []
    links: list[dict[str, Any]] = []
    for b in (inner or {}).get("blocks") or []:
        if not isinstance(b, dict):
            continue
        if "text" in b:
            t = str((b.get("text") or {}).get("content") or "").strip()
            if t:
                texts.append(t)
        elif "resourceLink" in b:
            rl = b.get("resourceLink") or {}
            links.append({"title": str(rl.get("title") or ""),
                          "uri": str(rl.get("uri") or rl.get("downloadUrl") or "")})
        elif "file" in b:
            fv = b.get("file") or {}
            links.append({"title": str(fv.get("name") or "文件"),
                          "uri": f"kimi-file://{fv.get('id')}" if fv.get("id")
                          else str(fv.get("uri") or fv.get("downloadUrl") or "")})
        elif "image" in b:
            iv = b.get("image") or {}
            links.append({"title": "图片", "uri": str(iv.get("uri") or iv.get("url") or "")})
    return "\n".join(texts).strip(), links


def message_role(msg: dict[str, Any]) -> str:
    inner = msg.get("message") if isinstance(msg.get("message"), dict) else msg
    return str((inner or {}).get("role") or "")


def strip_textual_mentions(text: str) -> str:
    """去掉 <@短id|昵称> 形态的行内 at（官方 normalizeImInlineText 同款正则）。"""
    return _MENTION_RE.sub(" ", text).strip()
