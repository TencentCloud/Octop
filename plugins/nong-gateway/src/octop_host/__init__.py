"""Octop 宿主：一轮对话交给 Octop 面板的 agent（官方 WS 会话接口）。

为什么要有它：nong_gateway 业务层在 2026-09-15 的 P2a 里删掉了 octop 宿主（当时桥的
形态是独立服务 + "octop 已定调永不再装"）。本插件形态下桥跑在 Octop 进程里，
群里说话的"脑子"就是面板上的专家——所以宿主接缝回来了，实现从 yuanbao-bridge-py
的 `_ask_octop` 语义恢复，协议按 2026-09-17 实读的 octop/api/routers/chat/ws.py：

连接：ws://127.0.0.1:<port>/api/agents/<agent_id>/chat/ws?token=<JWT>
出站：{"type":"user_turn","text":...,"session_key":...}
入站帧：turn_status / delta / done / error（hub 按订阅的 thread_id 广播）

关键语义（与面板同一条路）：
- session_key：一个群/私聊 = 一个 thread（get_or_create_by_key），跨重启连续；
  本宿主用 "nonggw:<agent_id>:<subject>" 做键，绝不与面板用户的 dashboard 键撞车。
- thread 是 agent 私有的——A 机器人的轮次永远落在 A 的 agent 上，与 B 无关
  （多 agent 同群互不污染的第一道墙在业务层，第二道墙在这：各走各的 WS 连接）。
- JWT 用 octop.db secrets.jwt 的 HMAC 现签（skill 的取token.py 同款，stdlib 零依赖）。

纪律（与 pi 宿主一致）：一个会话一次只跑一轮（排队）；超时/断连收敛成可读文本，
不让异常穿到 IM 变沉默。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from .turn import TurnOutcome

log = logging.getLogger("nonggw.octop_host")


# ---------------------------------------------------------------- JWT 现签 ----
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def load_jwt_secret(octop_home: str) -> bytes:
    """从 octop.db 的 secrets 表取 jwt secret（原始 bytes，绝不 decode）。"""
    db = Path(octop_home) / "octop.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        row = con.execute("SELECT v FROM secrets WHERE k='jwt'").fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        raise RuntimeError(f"octop.db secrets 表没有 jwt 项（{db}）——Octop 未初始化？")
    v = row[0]
    return v if isinstance(v, bytes) else str(v).encode("utf-8")


def sign_jwt(secret: bytes, user_id: int, hours: float = 1.0) -> str:
    """与 Octop 同款 HS256 JWT：sub/uname/role 由插件形态进程内直接可得。"""
    now = int(time.time())
    payload = {"sub": str(user_id), "uname": "nong-gateway", "role": "admin",
               "iat": now, "exp": now + int(hours * 3600)}
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (_b64u(json.dumps(header, separators=(",", ":")).encode()) + "." +
                     _b64u(json.dumps(payload, separators=(",", ":")).encode()))
    sig = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64u(sig)}"


class OctopHost:
    """每个 agent 一个实例（业务层按 agent_id 派发，天然 per-agent 隔离）。"""

    name = "octop"

    def __init__(self, cfg, agent_id: str, log_fn: Callable[..., None],
                 user_id: int = 2, session_dir_base=None) -> None:
        self.cfg = cfg
        self.agent_id = agent_id
        self._log = log_fn
        self.user_id = user_id
        self.port = int(getattr(cfg, "octop_port", 8088) or 8088)
        self._secret = load_jwt_secret(getattr(cfg, "octop_home", "/data/wwlst/octop"))
        self._token = sign_jwt(self._secret, user_id)
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, session: str) -> asyncio.Lock:
        if session not in self._locks:
            self._locks[session] = asyncio.Lock()
        return self._locks[session]

    def _url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/api/agents/{self.agent_id}/chat/ws?token={self._token}"

    async def ask(self, req, timeout: int = 900, on_delta=None, on_event=None,
                  on_late=None, defer_on_timeout: bool = False,
                  **_: Any) -> TurnOutcome:
        """跑一轮。成功返回 TurnOutcome(ok=True, text)；失败返回 ok=False + 原因。

        defer_on_timeout=True（业务层 deferredDelivery 缺省开）：内部等待到期**不杀轮次**，
        交后台继续收帧，跑完调 on_late(outcome) 补发（长任务不以"超时失败"收场——
        与 PiRpcHost 同语义）。会话锁保持到后台轮结束，防交错。
        """
        session = req.session
        async with self._lock(session):                      # 同会话串行（含后台段）
            try:
                outcome = await asyncio.wait_for(self._ask_once(req), timeout=timeout)
            except (asyncio.TimeoutError, TimeoutError):
                outcome = TurnOutcome(ok=False, text="", error=f"等待回复超时（{self.agent_id}）")
            # defer 判定看结果不看异常：_ask_once 内部有 120s 首帧 deadline，超时是**正常 return**
            # （ok=False + "等待回复超时"），不会抛 TimeoutError——之前的 defer 分支等异常永远等不到，
            # 表现就是"超时报错发群 + 后台轮完成不补发"（2026-09-17 20:31 实测）。
            if outcome.ok or not (defer_on_timeout and on_late is not None):
                return outcome
            if "超时" not in outcome.error:
                return outcome                                # 真失败（429 文案等）照旧返回
            # 转后台：继续收帧到自然完成，完成后回调补发。锁由本 with 管辖，自然保持。
            task = asyncio.ensure_future(self._ask_until_done(req))
            def _on_done(fut):
                try:
                    on_late(fut.result())
                except Exception as exc:                      # noqa: BLE001
                    log.warning("octop 宿主 on_late 异常: %s", exc)
            task.add_done_callback(_on_done)
            # 转后台**不算失败**：ok=True + 空 text，业务层不会把错误文本发去群里。
            # 用专门的标记让业务层知道"别等这条了"，后台完成时 on_late 补发。
            return TurnOutcome(ok=True, text="", error="deferred")

    async def _ask_until_done(self, req) -> TurnOutcome:
        """后台收帧直到 done/error/自然静默。与 _ask_once 同帧协议，无 deadline 上限。"""
        import aiohttp
        session_key = f"nonggw:{self.agent_id}:{req.session}"
        chunks: list[str] = []
        try:
            async with aiohttp.ClientSession() as http:
                async with http.ws_connect(self._url(), heartbeat=30) as ws:
                    await ws.send_str(json.dumps({
                        "type": "user_turn", "text": req.text,
                        "session_key": session_key}, ensure_ascii=False))
                    idle = time.monotonic()
                    while True:
                        remaining = 180 - (time.monotonic() - idle)
                        if remaining <= 0:
                            break                        # 180s 无产出即认为完成
                        try:
                            frame = json.loads(
                                (await asyncio.wait_for(ws.receive(), timeout=remaining)).data)
                        except asyncio.TimeoutError:
                            break
                        except Exception:                 # noqa: BLE001
                            break
                        t = str(frame.get("type") or "")
                        if t == "token":
                            c = str(frame.get("content") or "")
                            if c:
                                chunks.append(c)
                                idle = time.monotonic()
                        elif t == "done":
                            break
                        elif t == "error":
                            out = "".join(chunks).strip()
                            return TurnOutcome(ok=bool(out), text=out,
                                               error="" if out else str(frame.get("message") or ""))
        except Exception as exc:                              # noqa: BLE001
            out = "".join(chunks).strip()
            return TurnOutcome(ok=bool(out), text=out,
                               error="" if out else f"octop 宿主后台异常 {type(exc).__name__}: {exc}")
        out = "".join(chunks).strip()
        return TurnOutcome(ok=bool(out), text=out, error="" if out else "后台轮无输出")

    async def _ask_once(self, req) -> TurnOutcome:
        import aiohttp
        session_key = f"nonggw:{self.agent_id}:{req.session}"
        text = req.text
        try:
            async with aiohttp.ClientSession() as http:
                async with http.ws_connect(self._url(), heartbeat=30) as ws:
                    await ws.send_str(json.dumps({
                        "type": "user_turn",
                        "text": text,
                        "session_key": session_key,
                    }, ensure_ascii=False))
                    chunks: list[str] = []
                    deadline = time.monotonic() + 120        # 首帧等待：面板前奏长（skills/memory/PPI 中间件逐个广播），拿足
                    got_any = False
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            out = "".join(chunks).strip()
                            return TurnOutcome(ok=bool(out), text=out,
                                               error="" if out else f"等待回复超时（{self.agent_id}）")
                        try:
                            frame = json.loads(
                                (await asyncio.wait_for(ws.receive(), timeout=remaining)).data)
                        except asyncio.TimeoutError:
                            continue                      # deadline 统一判，不在这里直接退
                        except Exception as exc:              # noqa: BLE001
                            out = "".join(chunks).strip()
                            return TurnOutcome(ok=bool(out), text=out,
                                               error="" if out else f"WS 断开: {exc}")
                        t = str(frame.get("type") or "")
                        if t == "token":                      # 官方流式文本帧（ws_channel._send_text）
                            c = str(frame.get("content") or "")
                            if c:
                                chunks.append(c)
                                got_any = True
                                deadline = time.monotonic() + 120   # 有产出就续
                        elif t == "state_update" or t == "state_snapshot":
                            if not got_any:
                                deadline = max(deadline, time.monotonic() + 90)  # 前奏帧也续期，但比 token 短
                        elif t == "done":                     # 收尾帧（官方类型）
                            out = "".join(chunks).strip()
                            if out:
                                return TurnOutcome(ok=True, text=out)
                            # done 但没内容：可能 error 帧还没到，再等一拍（收到 error 或超时统一处理）
                        elif t == "error":
                            return TurnOutcome(ok=False, text="".join(chunks),
                                               error=str(frame.get("message") or "unknown"))
        except Exception as exc:                                  # noqa: BLE001
            return TurnOutcome(ok=False, text="",
                               error=f"octop 宿主异常 {type(exc).__name__}: {exc}")

    async def stop(self) -> None:
        return None

    def describe(self) -> str:
        return f"octop:{self.agent_id}@127.0.0.1:{self.port}"
