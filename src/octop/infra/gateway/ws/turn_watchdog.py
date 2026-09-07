"""TurnWatchdog — detect stalled Dashboard turns and recover them.

Octop 的流式链路（WS user_turn → gateway worker → iter_turn_chunks →
agent.stream → LLM provider）本身没有超时：LLM 上游请求挂起（连接黑洞、
200 无字节、慢流）、或工具执行静默挂起（bash 卡死、网络 IO 悬挂）时，
turn 会永久卡住——前端无回帧、session lock 被永久持有、同一会话后续
消息全部排队等待一把永远不释放的锁。

看门狗周期性扫描 WebSocketHub 登记的 active turns：
- 无进展超时（``OCTOP_TURN_STALL_SECONDS``，默认 300）：模型阶段自最后
  一个 chunk 起无任何产出 → 判定卡死；
- 工具阶段无进展超时（``OCTOP_TURN_TOOL_STALL_SECONDS``，默认 900）：
  工具执行中不产 chunk 是正常态（bash 跑 10 分钟无中间帧），阈值放宽；
- 模型阶段总时长超时（``OCTOP_TURN_MAX_SECONDS``，默认 1800）：只累计
  模型阶段时间（工具段不计入），防模型死循环，不误杀长工具链。

触发后执行恢复（顺序很重要）：
1. 标记 notified + 从 hub 活登记表摘除（后续 chunk 不再更新进展，重复
   触发被 mark_turn_active 的 notified 分支挡住）；
2. 向 thread 订阅者推送 error + done 帧——客户端立刻回到可交互态，不再
   无限等待；
3. cancel_stream —— harness 的 cancel 是可靠的（``_iter_until_cancelled``
   能打断被阻塞的 ``__anext__``，即 LLM 请求挂起也能打断），取消后正常
   链路收尾、session lock 释放，排队的后续消息继续处理。

notified 记录由 harness 收尾 finally 的 mark_turn_idle 删除；若极端情况
下 harness 收尾不了（进程内卡死），``OCTOP_TURN_NOTIFIED_GRACE_SECONDS``
（默认 120）后强制清理，避免该 thread 永久无法登记新 turn。

参数全部环境变量可配（对齐 OCTOP_BROWSER_IDLE_TIMEOUT_MINUTES 惯例）：
- ``OCTOP_TURN_STALL_SECONDS`` 模型阶段无进展超时（秒，默认 300）
- ``OCTOP_TURN_TOOL_STALL_SECONDS`` 工具阶段无进展超时（秒，默认 900）
- ``OCTOP_TURN_MAX_SECONDS`` 模型阶段总时长上限（秒，默认 1800）
- ``OCTOP_TURN_NOTIFIED_GRACE_SECONDS`` 收尾宽限（秒，默认 120）
- ``OCTOP_TURN_WATCHDOG_INTERVAL_SECONDS`` 扫描间隔（秒，默认 15）
- ``OCTOP_TURN_WATCHDOG_DISABLED=1`` 逃生阀，彻底关闭
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Any

from octop.infra.gateway.ws.ws_hub import WebSocketHub

logger = logging.getLogger(__name__)

DEFAULT_STALL_SECONDS = 300
DEFAULT_TOOL_STALL_SECONDS = 900
DEFAULT_MAX_SECONDS = 1800
DEFAULT_NOTIFIED_GRACE_SECONDS = 120
DEFAULT_INTERVAL_SECONDS = 15


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("invalid %s=%r, falling back to %d", name, raw, default)
        return default


def watchdog_disabled() -> bool:
    return os.environ.get("OCTOP_TURN_WATCHDOG_DISABLED", "").strip() == "1"


class TurnWatchdog:
    """Background task that scans active dashboard turns for stalls."""

    def __init__(
        self,
        *,
        hub: WebSocketHub,
        agent_manager: Any,
        audit_repo: Any | None = None,
        gateway: Any | None = None,
        stall_seconds: int | None = None,
        tool_stall_seconds: int | None = None,
        max_seconds: int | None = None,
        notified_grace_seconds: int | None = None,
        interval_seconds: int | None = None,
    ) -> None:
        self._hub = hub
        self._agent_manager = agent_manager
        self._audit_repo = audit_repo
        self._gateway = gateway
        self._stall_seconds = (
            stall_seconds
            if stall_seconds is not None
            else _env_int("OCTOP_TURN_STALL_SECONDS", DEFAULT_STALL_SECONDS)
        )
        self._tool_stall_seconds = (
            tool_stall_seconds
            if tool_stall_seconds is not None
            else _env_int("OCTOP_TURN_TOOL_STALL_SECONDS", DEFAULT_TOOL_STALL_SECONDS)
        )
        self._max_seconds = (
            max_seconds
            if max_seconds is not None
            else _env_int("OCTOP_TURN_MAX_SECONDS", DEFAULT_MAX_SECONDS)
        )
        self._notified_grace = (
            notified_grace_seconds
            if notified_grace_seconds is not None
            else _env_int("OCTOP_TURN_NOTIFIED_GRACE_SECONDS", DEFAULT_NOTIFIED_GRACE_SECONDS)
        )
        self._interval = (
            interval_seconds
            if interval_seconds is not None
            else _env_int("OCTOP_TURN_WATCHDOG_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)
        )
        self._task: asyncio.Task[None] | None = None
        self._started_at: float | None = None

    def start(self) -> None:
        """Launch the scan loop (idempotent)."""
        if self._task is not None and not self._task.done():
            return
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self._scan_loop(), name="turn-watchdog")
        logger.info(
            "TurnWatchdog started: stall=%ss tool_stall=%ss model_max=%ss "
            "notified_grace=%ss interval=%ss",
            self._stall_seconds,
            self._tool_stall_seconds,
            self._max_seconds,
            self._notified_grace,
            self._interval,
        )

    async def stop(self) -> None:
        """Cancel the scan loop (idempotent)."""
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _scan_loop(self) -> None:
        try:
            while True:
                try:
                    self._scan_once()
                except Exception:  # noqa: BLE001 - watchdog must never die
                    logger.exception("TurnWatchdog scan failed")
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.info("TurnWatchdog stopped")
            raise

    def _scan_once(self) -> None:
        now = time.monotonic()
        self._sweep_notified(now)
        for thread_id, record in self._hub.snapshot_active_turns().items():
            if record.notified:
                continue
            stalled_for = now - record.last_progress_at
            stall_limit = self._tool_stall_seconds if record.in_tool else self._stall_seconds
            model_time = record.model_time(now)
            if stalled_for < stall_limit and model_time < self._max_seconds:
                continue
            if stalled_for >= stall_limit:
                reason = (
                    f"no output for {stalled_for:.0f}s "
                    f"({'tool' if record.in_tool else 'model'} threshold {stall_limit}s)"
                )
            else:
                reason = (
                    f"model phase exceeded {model_time:.0f}s "
                    f"(limit {self._max_seconds}s)"
                )
            self._recover(thread_id, record, reason)

    def _sweep_notified(self, now: float) -> None:
        """Force-remove notified records whose harness never wound down.

        Normally the cancelled stream's finally-path calls mark_turn_idle and
        deletes the record within a second. If the harness is itself wedged
        (no finally, no cancellation response), the notified record would
        otherwise block this thread from registering a new turn forever.
        """
        for thread_id, record in self._hub.snapshot_notified_turns().items():
            if record.notified_at is None:
                record.notified_at = now
                continue
            if now - record.notified_at <= self._notified_grace:
                continue
            logger.warning(
                "TurnWatchdog force-cleared zombie turn record: agent=%s thread=%s "
                "(harness wind-down exceeded %ss grace)",
                record.agent_id or "?",
                thread_id,
                self._notified_grace,
            )
            self._hub.mark_turn_idle(thread_id)

    def _recover(self, thread_id: str, record: Any, reason: str) -> None:
        """Declare a turn dead: notify client, cancel stream, release slot.

        The record stays in the hub table with ``notified=True`` so a racing
        ``mark_turn_active`` (user retry) cannot resurrect the zombie; the
        harness finally-path removes it via ``mark_turn_idle`` once the
        cancelled stream winds down (or _sweep_notified force-clears it).
        """
        record.notified = True
        record.notified_at = time.monotonic()
        agent_id = record.agent_id or "?"
        logger.warning(
            "TurnWatchdog recovered stalled turn: agent=%s thread=%s %s",
            agent_id,
            thread_id,
            reason,
        )
        self._audit_stall(agent_id, thread_id, reason)
        asyncio.ensure_future(
            self._notify_and_cancel(thread_id, agent_id, reason, record.session_key or "")
        )

    async def _notify_and_cancel(
        self,
        thread_id: str,
        agent_id: str,
        reason: str,
        session_key: str = "",
    ) -> None:
        message = (
            f"Turn watchdog aborted a stalled turn ({reason}). "
            "The request may still be running server-side; please retry."
        )
        try:
            await self._hub.push_to_thread(thread_id, {"type": "error", "message": message})
            await self._hub.push_to_thread(thread_id, {"type": "done"})
        except Exception:  # noqa: BLE001 - notify failure must not block cancel
            logger.exception("TurnWatchdog notify failed thread=%s", thread_id)
        # IM turns have no WS subscribers; push a plain-text notice to the
        # channel the message came from so the user is not left hanging.
        if session_key and self._gateway is not None:
            try:
                session = self._gateway.thread_registry.get_session(session_key)
                if session is not None and session.channel_id:
                    await self._gateway.push_text(
                        session.channel_type,
                        session.channel_id,
                        session.to_channel_subject(),
                        "[回复超时] 已自动取消，请重试。",
                    )
            except Exception:  # noqa: BLE001
                logger.exception("TurnWatchdog IM notify failed session=%s", session_key)
        try:
            if self._agent_manager is not None and agent_id != "?":
                self._agent_manager.cancel_stream(agent_id, thread_id)
        except Exception:  # noqa: BLE001
            logger.exception("TurnWatchdog cancel_stream failed agent=%s", agent_id)

    def _audit_stall(self, agent_id: str, thread_id: str, reason: str) -> None:
        if self._audit_repo is None:
            return
        try:
            self._audit_repo.write(
                actor="turn-watchdog",
                action="turn.stall.recovered",
                target=thread_id,
                payload=f"agent={agent_id} {reason}",
            )
        except Exception:  # noqa: BLE001 - audit must never crash the watchdog
            logger.warning("TurnWatchdog audit write failed", exc_info=True)

    @property
    def started_at(self) -> float | None:
        return self._started_at


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_MAX_SECONDS",
    "DEFAULT_NOTIFIED_GRACE_SECONDS",
    "DEFAULT_STALL_SECONDS",
    "DEFAULT_TOOL_STALL_SECONDS",
    "TurnWatchdog",
]
