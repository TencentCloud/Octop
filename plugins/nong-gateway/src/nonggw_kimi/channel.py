"""Kimi Claw 通道——把 kimi-claw-py 的自实现协议挂到 harness-gateway 的通道契约上。

移植原则（与 kcp 行为逐条对应，改哪条都要说明为什么）：

1. **同步泵 + 事件循环桥接**：订阅是阻塞式流（手写 WS / Connect 流式），所以放在
   专职线程里泵；每处理完一条，用 ``run_coroutine_threadsafe`` 回到事件循环等它跑完。
2. **游标在处理之后才记**（至少一次）：崩在中间宁可重投——重投由事件级/消息级去重兜住，
   反过来（处理前记游标）就是至多一次，崩一下就永久丢一条。
3. **正文不在订阅帧里**：订阅给的是通知，正文要 ``ListMessages`` 取；取不到就明说并跳过
   （消息可能已过期），不假装成功。
4. **群/私聊以 roomType 为准**：私聊的 roomId 与 chatId 相同且非空，只看 roomId 会把每条私聊
   当群处理（kcp 真帧踩过）。
5. **单消费者用 flock**：平台不拒绝第二个订阅，两个进程同时订阅会各自吃掉一部分消息。
6. **原始帧留证有上限**：ping 帧不落盘，超限轮转且只留一份——排障要原文，但不能把磁盘吃穿。
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from harness_gateway.channel import BaseChannel, ChannelCredentialsError
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from . import protocol as kc
from .config import KimiConfig


# --------------------------------------------------------------------------- #
# 状态：游标 + 订阅锁
# --------------------------------------------------------------------------- #


class Cursor:
    """订阅游标 + 会话路由 + 自己的身份，落一个 JSON（0600）。

    为什么要落盘：``sinceId`` 是断线期间消息不丢的唯一保证；路由表让重启后仍能主动推送；
    身份存下来是给 GetMe 偶发失败时兜底（拿不到身份就没法挡自答）。
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data = loaded
            except (OSError, ValueError):
                pass

    @property
    def last_event_id(self) -> str:
        return str(self.data.get("lastEventId") or "")

    @property
    def default_chat_id(self) -> str:
        return str(self.data.get("defaultChatId") or "")

    def remember(self, *, event_id: str = "", default_chat_id: str = "") -> None:
        with self._lock:
            changed = False
            if event_id and event_id != self.data.get("lastEventId"):
                self.data["lastEventId"] = event_id
                changed = True
            if default_chat_id and default_chat_id != self.data.get("defaultChatId"):
                self.data["defaultChatId"] = default_chat_id
                changed = True
            if changed:
                self._flush()

    def routes(self) -> dict[str, str]:
        out = self.data.get("routes")
        return out if isinstance(out, dict) else {}

    def set_route(self, session_key: str, chat_id: str) -> None:
        if not session_key or not chat_id:
            return
        with self._lock:
            routes = self.data.setdefault("routes", {})
            if routes.get(session_key) == chat_id:
                return
            routes[session_key] = chat_id
            self._flush()

    def set_self_identity(self, bot_id: str, ids: set[str], name: str = "") -> None:
        with self._lock:
            changed = False
            if bot_id and self.data.get("selfId") != bot_id:
                self.data["selfId"] = bot_id
                changed = True
            if name and self.data.get("selfName") != name:
                self.data["selfName"] = name
                changed = True
            known = set(self.data.get("selfIds") or []) | {i for i in ids if i}
            if known != set(self.data.get("selfIds") or []):
                self.data["selfIds"] = sorted(known)
                changed = True
            if changed:
                self._flush()

    def self_ids(self) -> set[str]:
        return {str(x) for x in (self.data.get("selfIds") or []) if x}

    def self_name(self) -> str:
        return str(self.data.get("selfName") or "")

    def _flush(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self.path)
        except OSError:
            # 游标写不进去不能静默：下次重连会从头开始，可能重放一批消息
            raise


class SubscribeLock:
    """同一 bot 的订阅单消费者闸（flock）。

    平台侧不会拒绝第二个订阅，两边各吃一部分消息——这种故障的表现是"有时不回"，
    极难查。所以订阅前必须拿到锁；拿不到就明说退出（由上层决定重试）。
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None
        self._noted = False

    def acquire(self, wait: float = 0.0, note: Callable[[str], None] | None = None) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + max(0.0, float(wait or 0.0))
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                with contextlib.suppress(OSError):
                    os.ftruncate(fd, 0)
                    os.write(fd, f"{os.getpid()}\n".encode())
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    return False
                if note and not self._noted:
                    self._noted = True
                    note(f"订阅锁被另一个消费者持有（{self.path}），继续等待…")
                time.sleep(0.5)

    def release(self) -> None:
        if self._fd is None:
            return
        with contextlib.suppress(OSError):
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(self._fd)
        self._fd = None


# --------------------------------------------------------------------------- #
# 判定辅助（从 kcp bridge.py 照搬，语义见注释）
# --------------------------------------------------------------------------- #


def is_group_event(room_type: str, room_id: str, chat_id: str) -> bool:
    """群/私聊判定：优先 proto 的 roomType。

    真帧记录过：**私聊的 roomId 与 chatId 相同且非空**，所以"有 roomId 就是群"
    会把每条私聊都当群处理。
    """
    if room_type:
        return room_type == "ROOM_TYPE_GROUP"
    return bool(room_id) and room_id != chat_id


def mark_seen(bucket: dict[str, float], key: str, limit: int = 800) -> bool:
    """返回 True 表示第一次见。有状态判定只出现在这里。"""
    if not key:
        return True
    if key in bucket:
        return False
    bucket[key] = time.time()
    if len(bucket) > limit:
        for k, _t in sorted(bucket.items(), key=lambda kv: kv[1])[: limit // 4]:
            bucket.pop(k, None)
    return True


# --------------------------------------------------------------------------- #
# 通道
# --------------------------------------------------------------------------- #


class KimiChannel(BaseChannel):
    """Kimi Claw 通道（订阅长连接 + 流式出站）。"""

    channel_type = "kimi"

    def __init__(
        self,
        processor,
        *,
        config: KimiConfig,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints=None,
    ) -> None:
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            debounce_seconds=debounce_seconds,
            constraints=constraints,
            config=config,
        )
        self.cfg = config
        self._log_sink: Callable[[str], None] | None = None
        # 客户端延迟到 start() 才建：构造不碰网络，缺凭据要报「通道缺 token」这种
        # 调用方能处置的错，而不是协议层的 ValueError。
        self.client: kc.ImClient | None = None
        self.state_dir = Path(config.state_dir) if config.state_dir else None
        self.cursor = Cursor(self.state_dir / "cursor.json") if self.state_dir else None
        self.lock = SubscribeLock(self.state_dir / "subscribe.lock") if self.state_dir else None

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._seen_events: dict[str, float] = {}
        self._seen_msgs: dict[str, float] = {}
        self.my_id = ""
        self.my_name = ""
        self.me_ids: set[str] = set()

    # ---- 日志 ----

    def set_log_sink(self, sink: Callable[[str], None]) -> None:
        """由应用层注入日志出口（通道自己不决定去哪）。"""
        self._log_sink = sink

    def _log(self, msg: str, *, force: bool = True) -> None:
        if self._log_sink is not None:
            with contextlib.suppress(Exception):
                self._log_sink(msg if force else msg)
                return
        # 没有注入出口时不能静默吞：打到标准错误（systemd 会收进 journal）
        import sys

        print(f"[kimi] {msg}", file=sys.stderr, flush=True)

    # ---- 生命周期 ----

    async def start(self) -> None:
        missing = self.cfg.missing_credentials()
        if missing:
            raise ChannelCredentialsError(self.channel_type, missing)
        if self.state_dir is None:
            raise RuntimeError(
                "kimi 通道缺 state_dir：游标与订阅锁必须有独占目录（多 bot 各配一个），"
                "否则两个消费者会抢同一个 bot 的消息")
        if self.client is None:
            self.client = kc.ImClient(
                self.cfg.token,
                kimiapi_host=self.cfg.kimiapi_host or kc.DEFAULT_KIMIAPI_HOST,
                claw_version=self.cfg.claw_version,
                openclaw_version=self.cfg.openclaw_version,
                on_log=lambda m: self._log(f"[协议] {m}", force=False),
            )
        self._loop = asyncio.get_running_loop()
        assert self.lock is not None
        got = await asyncio.to_thread(self.lock.acquire, self.cfg.lock_wait_sec, self._log)
        if not got:
            raise RuntimeError(
                f"订阅锁被占用：{self.lock.path}（另一个消费者在跑？同一 bot 只能有一个订阅）")
        await asyncio.to_thread(self._resolve_me)
        self._stop.clear()
        self._thread = threading.Thread(target=self._pump, name="kimi-subscribe", daemon=True)
        self._thread.start()
        self._log(f"通道已启动（身份 {self.my_name or '未知'} id={self.my_id or '未知'}）")

    async def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            await asyncio.to_thread(thread.join, 10.0)
            if thread.is_alive():
                self._log("订阅线程 10s 未退出（已置停止位，交给进程退出回收）", force=False)
        if self.lock is not None:
            self.lock.release()
        self._log("通道已停止")

    # ---- 身份 ----

    def _client_or_raise(self) -> "kc.ImClient":
        if self.client is None:
            raise RuntimeError("kimi 通道还没启动（client 未创建）：先 await start()")
        return self.client

    def _resolve_me(self) -> None:
        """取自己的身份。失败不致命（用游标里存的上次身份兜底），但要说清。"""
        if self.cursor is not None:
            self.me_ids = self.cursor.self_ids()
            self.my_name = self.cursor.self_name()
        try:
            me = self._client_or_raise().get_me()
        except Exception as exc:  # noqa: BLE001  —— 身份拿不到不是致命错误
            self._log(f"GetMe 失败（自答保护退化为用游标里的身份）：{type(exc).__name__}: {str(exc)[:160]}")
            return
        self.my_id = str(me.get("id") or "")
        self.my_name = str(me.get("name") or "")
        if self.my_id:
            self.me_ids.add(self.my_id)
        short = str(me.get("shortId") or "")
        if short:
            self.me_ids.add(short)
        if self.cursor is not None:
            self.cursor.set_self_identity(self.my_id, self.me_ids, self.my_name)

    # ---- 订阅泵（线程） ----

    def _pump(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            since = self.cursor.last_event_id if self.cursor else ""
            sub = None
            try:
                sub = self.client.subscribe(since_id=since, stop=self._stop)
                for ev in sub:
                    if self._stop.is_set():
                        return
                    self._process_event(ev)
                backoff = 2.0
            except kc.SubscriptionClosed as exc:
                # reconnect 分支或流正常结束：立刻重连（不是错误）
                self._log(f"订阅断开，重连续传：{str(exc)[:160]}", force=False)
                if self._stop.wait(1.0):
                    return
            except kc.KimiError as exc:
                status = getattr(exc, "status", 0)
                if status in (401, 403):
                    self._log(f"订阅被拒（HTTP {status}）：token 无效或已停用，**停止重试**"
                              f"——检查 configure 里的 token。原文：{str(exc)[:160]}")
                    self._stop.set()
                    return
                self._log(f"订阅出错：{type(exc).__name__}: {str(exc)[:200]}，{backoff:.0f}s 后重连")
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, 60.0)
            except Exception as exc:  # noqa: BLE001  网络抖动不该杀死通道
                self._log(f"订阅异常：{type(exc).__name__}: {str(exc)[:200]}，{backoff:.0f}s 后重连")
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, 60.0)
            finally:
                if sub is not None:
                    with contextlib.suppress(Exception):
                        sub.close()

    def _process_event(self, ev: kc.SubscribeEvent) -> None:
        """一条事件的完整处理：处理 + 推进游标。

        两条规矩合在一起才成立：
        1. 游标**在处理之后**才记（至少一次；崩在中间宁可重投，重投由去重兜住）；
        2. 每条事件都推进（ping 也推进——官方 id 逐帧递增，续传点必须跟着走）。
        reconnect 从 _handle_event 抛出去，跳过推进，于是续传点停在那条事件之前：不丢。
        """
        self._handle_event(ev)
        self._remember(ev)

    def _handle_event(self, ev: kc.SubscribeEvent) -> None:
        """线程侧：过滤 → 取正文 → 交给事件循环处理 → **处理完才记游标**。"""
        if ev.case == "ping":
            return
        if ev.case == "reconnect":
            # 交回 _pump：抛出去就是重连（游标不前进，续传不丢）
            raise kc.SubscriptionClosed("服务端下发 reconnect", method="Subscribe")
        if ev.case != "chatMessage":
            self._log(f"忽略事件 case={ev.case} id={ev.id[:14]}", force=False)
            return
        if not ev.is_completed_message():
            # STATUS_GENERATING 之类是"正在生成中的半截"，官方也跳过
            self._log(f"跳过未完成消息 status={ev.status}", force=False)
            return

        cm = ev.chat_message or {}
        chat_id = str(cm.get("chatId") or "")
        room_id = str(cm.get("roomId") or "")
        room_type = str(cm.get("roomType") or "")
        message_id = str(cm.get("messageId") or "")
        event_id = ev.id
        if not message_id:
            self._log("事件缺 messageId，跳过")
            return
        if not mark_seen(self._seen_events, event_id) or not mark_seen(self._seen_msgs, message_id):
            self._log(f"跳过重复投递 event={event_id[:14]} message={message_id[:14]}", force=False)
            return

        key = room_id or chat_id
        if self.cursor is not None and chat_id:
            # 会话键 → chatId 的路由（主动推送要用）
            self.cursor.set_route(key, chat_id)
        fetched = self._fetch_window(chat_id, message_id)
        current = fetched.get(message_id)
        if current is None:
            self._log(f"取不到消息正文（可能已过期）message={message_id[:14]} chat={chat_id[:14]}")
            return
        text, links = kc.message_text_of(current)
        text = kc.strip_textual_mentions(text)
        role = kc.message_role(current)
        sender_id = str(cm.get("senderId") or "")
        payload = {
            "event_id": event_id,
            "message_id": message_id,
            "chat_id": chat_id,
            "room_id": room_id,
            "room_type": room_type,
            "sender_id": sender_id,
            "sender_short_id": str(cm.get("senderShortId") or ""),
            "mentioned": bool(cm.get("mentioned")),
            "summary": str(cm.get("summary") or ""),
            "text": text,
            "links": links,
            "role": role,
            "is_group": is_group_event(room_type, room_id, chat_id),
            "from_self": bool(sender_id and sender_id in self.me_ids),
            "default_chat_id": ev.default_chat_id,
        }
        loop = self._loop
        if loop is None or loop.is_closed():
            self._log("事件循环不可用，丢弃本条（通道正在停止？）")
            return
        try:
            # 等处理跑完（含回复发送）再回线程：这就是"处理之后才记游标"的落点
            fut = asyncio.run_coroutine_threadsafe(self.handle_inbound(payload), loop)
            fut.result()
        except Exception as exc:  # noqa: BLE001  单条失败不能拖死订阅
            self._log(f"处理失败 message={message_id[:14]}：{type(exc).__name__}: {str(exc)[:240]}")
            return

    def _remember(self, ev: kc.SubscribeEvent) -> None:
        if self.cursor is not None:
            with contextlib.suppress(OSError):
                self.cursor.remember(event_id=ev.id, default_chat_id=ev.default_chat_id)

    def _fetch_window(self, chat_id: str, message_id: str) -> dict[str, dict[str, Any]]:
        """取这条消息（外加同窗口近况）。取不到返回空表，由调用方明说并跳过。"""
        out: dict[str, dict[str, Any]] = {}
        if not chat_id:
            return out
        try:
            rows = self._client_or_raise().list_messages(
                chat_id,
                page_size=int(self.cfg.fetch_page_size or 20),
                start_message_id=message_id,
                end_message_id=message_id,
            )
        except kc.KimiError as exc:
            self._log(f"ListMessages 失败（改取近况窗口）：{str(exc)[:160]}")
            try:
                rows = self._client_or_raise().list_messages(chat_id, page_size=12)
            except kc.KimiError as exc2:
                self._log(f"ListMessages 仍失败：{str(exc2)[:160]}")
                return {}
        for m in rows:
            mid = str(((m.get("message") or {}).get("id")) or m.get("messageId") or "")
            if mid:
                out[mid] = m
        self._dump_raw(rows)
        return out

    def _dump_raw(self, rows: list[dict[str, Any]]) -> None:
        """原始帧留证（默认关）。上限 + 轮转 + 0600：排障要原文，但不能吃穿磁盘。"""
        cap_mb = int(self.cfg.raw_dump_mb or 0)
        if cap_mb <= 0 or self.state_dir is None:
            return
        d = self.state_dir / "raw"
        fp = d / "inbound.jsonl"
        try:
            d.mkdir(parents=True, exist_ok=True)
            if fp.is_file() and fp.stat().st_size > cap_mb * 1024 * 1024:
                fp.replace(d / "inbound.jsonl.1")
            with open(fp, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": time.time(), "rows": rows}, ensure_ascii=False) + "\n")
            os.chmod(fp, 0o600)
        except OSError as exc:
            self._log(f"原始帧落盘失败（不影响收消息）：{exc}", force=False)

    # ---- 入站解析 ----

    def parse_inbound(self, raw_payload: object) -> InboundMessage:
        """把泵线程解析好的载荷变成 InboundMessage（**纯映射，不碰网络**）。"""
        data = raw_payload if isinstance(raw_payload, dict) else {}
        chat_id = str(data.get("chat_id") or "")
        room_id = str(data.get("room_id") or "")
        text = str(data.get("text") or "")
        is_group = bool(data.get("is_group"))
        key = room_id or chat_id
        metadata = {
            "chat_id": chat_id,
            "room_id": room_id,
            "room_type": data.get("room_type") or "",
            "message_id": data.get("message_id") or "",
            "event_id": data.get("event_id") or "",
            "sender_id": data.get("sender_id") or "",
            "sender_short_id": data.get("sender_short_id") or "",
            "sender_name": "",
            "mentioned": bool(data.get("mentioned")),
            "summary": data.get("summary") or "",
            "links": data.get("links") or [],
            "role": data.get("role") or "",
            "from_self": bool(data.get("from_self")),
            "is_group": is_group,
            "subject_key": key,
        }
        return InboundMessage(
            channel_id=self._channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=key,
                display_name="",
                chat_type="group" if is_group else "direct",
                metadata=metadata,
            ),
            channel_session_id=key,
            content=[TextContent(text=text)] if text else [],
            metadata=metadata,
        )

    # ---- 出站 ----

    def _chat_id_of(self, subject: ChannelSubject) -> str:
        meta = getattr(subject, "metadata", None) or {}
        chat_id = str(meta.get("chat_id") or "")
        if chat_id:
            return chat_id
        # 兜底：用游标里学到的路由（重启后主动推送走这条）
        if self.cursor is not None:
            routed = self.cursor.routes().get(str(getattr(subject, "subject_id", "") or ""))
            if routed:
                return str(routed)
        return ""

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        if not (text or "").strip():
            return
        chat_id = self._chat_id_of(subject)
        if not chat_id:
            raise RuntimeError(
                f"kimi 发送缺 chatId（subject={getattr(subject, 'subject_id', '')}）："
                "该会话还没收到过入站消息，也没有历史路由")

        def _do() -> None:
            with kc.OutboundStream(self._client_or_raise(), chat_id) as stream:
                stream.push_text(text)

        await asyncio.to_thread(_do)

    async def _send_content(self, subject: ChannelSubject, parts: list) -> None:
        texts = [p.text for p in parts if isinstance(p, TextContent) and p.text]
        others = [type(p).__name__ for p in parts if not isinstance(p, TextContent)]
        if others:
            # 如实声明：kcp 从来没有出站媒体，不假装支持
            raise NotImplementedError(
                f"kimi 通道暂不支持出站 {others}（协议层只有文本块与资源链接；"
                "有需求先补协议再放开）")
        if texts:
            await self._send_text(subject, "\n".join(texts))

    async def _send_media(self, subject: ChannelSubject, media) -> None:
        raise NotImplementedError(
            f"kimi 通道暂不支持出站媒体（{type(media).__name__}）：协议层未实现上传")

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        """kimi 没有出站 typing 帧（订阅流里的 typing 是入站的），保持无操作。"""
        return None
