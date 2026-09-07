"""In-process registry of Dashboard WebSocket connections."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ActiveTurn:
    """One in-flight dashboard turn, tracked for the TURN watchdog.

    ``last_progress_at`` advances on every chunk the turn produces, so the
    watchdog can distinguish "model still thinking/tool still running" from
    "turn is stuck with no output at all".

    Tool phases are tracked separately so a long-running tool (bash fetching
    pages for 10 minutes emits no chunk) is not treated as a stall: the
    watchdog uses ``tool_stall_seconds`` while ``in_tool`` is True, and the
    total-turn cap only counts model-phase time (tool time is excluded).
    """

    agent_id: str
    thread_id: str
    session_key: str = ""
    started_at: float = field(default_factory=time.monotonic)
    last_progress_at: float = field(default_factory=time.monotonic)
    notified: bool = False
    notified_at: float | None = None
    in_tool: bool = False
    tool_segment_started_at: float | None = None
    tool_budget_spent: float = 0.0
    # 2026-09-07 修复：同一 thread 多并发 WS 连接（多标签页）各自开启 turn 时，
    # 先结束的一方不能把登记删掉（另一 turn 仍在跑）——引用计数，最后一个结束才置 idle。
    refcount: int = 1

    def __post_init__(self) -> None:
        if self.started_at == self.last_progress_at:
            self.last_progress_at = self.started_at

    def model_time(self, now: float | None = None) -> float:
        """Accumulated model-phase time (total minus tool segments)."""
        now = now if now is not None else time.monotonic()
        total = now - self.started_at
        spent = self.tool_budget_spent
        if self.in_tool and self.tool_segment_started_at is not None:
            spent += now - self.tool_segment_started_at
        return max(0.0, total - spent)

SendFn = Callable[[dict[str, Any]], Awaitable[None]]


def stamp_thread_id(frame: dict[str, Any], thread_id: str) -> dict[str, Any]:
    """Return *frame* with ``thread_id`` set so clients can drop cross-talk."""
    tid = thread_id.strip()
    if not tid or frame.get("thread_id") == tid:
        return frame
    stamped = dict(frame)
    stamped["thread_id"] = tid
    return stamped


class WebSocketHub:
    """Maps connection ids to async send callbacks for Dashboard sockets.

    Tracks per-thread subscriptions (chat) and optional per-user bindings
    (dashboard-wide toasts). Reconnecting clients resume live chunks via
    in-memory "turn active" flags. Each connection is bound to at most one
    thread at a time.
    """

    def __init__(self) -> None:
        self._connections: dict[str, SendFn] = {}
        self._thread_subscribers: dict[str, set[str]] = {}
        self._conn_thread: dict[str, str] = {}
        self._user_conns: dict[int, set[str]] = {}
        self._conn_user: dict[str, int] = {}
        self._active_turns: dict[str, ActiveTurn] = {}

    def register(
        self,
        connection_id: str,
        send_fn: SendFn,
        *,
        user_id: int | None = None,
    ) -> None:
        self._unbind_user(connection_id)
        self._connections[connection_id] = send_fn
        if user_id is None:
            return
        self._conn_user[connection_id] = user_id
        self._user_conns.setdefault(user_id, set()).add(connection_id)

    def unregister(self, connection_id: str) -> None:
        self.unsubscribe_connection(connection_id)
        self._unbind_user(connection_id)
        self._connections.pop(connection_id, None)

    def _unbind_user(self, connection_id: str) -> None:
        user_id = self._conn_user.pop(connection_id, None)
        if user_id is None:
            return
        conns = self._user_conns.get(user_id)
        if conns is None:
            return
        conns.discard(connection_id)
        if not conns:
            self._user_conns.pop(user_id, None)

    def subscribe(self, thread_id: str, connection_id: str) -> None:
        """Add *connection_id* as a subscriber for *thread_id*.

        Switching threads unsubscribes this connection from the previous
        thread. Other connections on the same thread keep receiving.
        """
        tid = thread_id.strip()
        if not tid or connection_id not in self._connections:
            return
        prev = self._conn_thread.get(connection_id)
        if prev == tid:
            return
        if prev is not None:
            self._drop_subscriber(prev, connection_id)
        self._thread_subscribers.setdefault(tid, set()).add(connection_id)
        self._conn_thread[connection_id] = tid

    def unsubscribe_connection(self, connection_id: str) -> None:
        tid = self._conn_thread.pop(connection_id, None)
        if tid is not None:
            self._drop_subscriber(tid, connection_id)

    def _drop_subscriber(self, thread_id: str, connection_id: str) -> None:
        conns = self._thread_subscribers.get(thread_id)
        if conns is None:
            return
        conns.discard(connection_id)
        if not conns:
            self._thread_subscribers.pop(thread_id, None)

    def mark_turn_active(self, thread_id: str, agent_id: str = "", session_key: str = "") -> None:
        tid = thread_id.strip()
        if not tid:
            return
        existing = self._active_turns.get(tid)
        if existing is not None and existing.notified:
            # Watchdog already declared this turn dead and the harness is
            # winding down; refuse to resurrect the zombie registration.
            # The old turn's finally-path will mark_turn_idle soon, after
            # which a retry registers fresh.
            return
        if existing is not None:
            # 并发 turn（同 thread 多连接）：递增引用计数，不覆盖既有登记。
            existing.refcount += 1
            return
        self._active_turns[tid] = ActiveTurn(
            agent_id=agent_id,
            thread_id=tid,
            session_key=session_key,
        )

    def mark_turn_progress(self, thread_id: str) -> None:
        """Advance the last-progress timestamp for an active turn."""
        tid = thread_id.strip()
        if tid:
            rec = self._active_turns.get(tid)
            if rec is not None:
                rec.last_progress_at = time.monotonic()

    def mark_tool_state(self, thread_id: str, in_tool: bool) -> None:
        """Track model vs tool phase so long tools are not treated as stalls."""
        tid = thread_id.strip()
        if not tid:
            return
        rec = self._active_turns.get(tid)
        if rec is None:
            return
        now = time.monotonic()
        if in_tool and not rec.in_tool:
            rec.in_tool = True
            rec.tool_segment_started_at = now
            rec.last_progress_at = now
        elif not in_tool and rec.in_tool:
            if rec.tool_segment_started_at is not None:
                rec.tool_budget_spent += now - rec.tool_segment_started_at
            rec.in_tool = False
            rec.tool_segment_started_at = None
            rec.last_progress_at = now

    def mark_turn_idle(self, thread_id: str) -> None:
        tid = thread_id.strip()
        rec = self._active_turns.get(tid)
        if rec is None:
            return
        rec.refcount -= 1
        if rec.refcount <= 0:
            self._active_turns.pop(tid, None)

    def is_turn_active(self, thread_id: str) -> bool:
        rec = self._active_turns.get(thread_id.strip())
        # A notified (watchdog-declared-dead) turn is no longer "active" for
        # subscribers, even though its record lingers until the harness winds
        # down.
        return rec is not None and not rec.notified

    def get_active_turn(self, thread_id: str) -> ActiveTurn | None:
        return self._active_turns.get(thread_id.strip())

    def snapshot_active_turns(self) -> dict[str, ActiveTurn]:
        """Copy of live (non-notified) turn records for the TURN watchdog."""
        return {
            tid: rec
            for tid, rec in self._active_turns.items()
            if not rec.notified
        }

    def snapshot_notified_turns(self) -> dict[str, ActiveTurn]:
        """Copy of watchdog-declared-dead records still awaiting wind-down."""
        return {tid: rec for tid, rec in self._active_turns.items() if rec.notified}

    async def push(self, connection_id: str, frame: dict[str, Any]) -> None:
        send_fn = self._connections.get(connection_id)
        if send_fn is None:
            logger.debug("ws hub: connection %s not found", connection_id)
            return
        try:
            await send_fn(frame)
        except Exception:
            logger.exception("ws hub: push failed for %s", connection_id)

    async def push_to_thread(self, thread_id: str, frame: dict[str, Any]) -> None:
        tid = thread_id.strip()
        conns = self._thread_subscribers.get(tid)
        if not conns:
            logger.debug("ws hub: no subscriber for thread %s", thread_id)
            return
        outbound = stamp_thread_id(frame, tid)
        targets = list(conns)
        if len(targets) == 1:
            await self.push(targets[0], outbound)
            return
        await asyncio.gather(*(self.push(conn_id, outbound) for conn_id in targets))

    async def push_to_user(self, user_id: int, frame: dict[str, Any]) -> None:
        conns = self._user_conns.get(user_id)
        if not conns:
            logger.debug("ws hub: no subscriber for user %s", user_id)
            return
        targets = list(conns)
        if len(targets) == 1:
            await self.push(targets[0], frame)
            return
        await asyncio.gather(*(self.push(conn_id, frame) for conn_id in targets))

    async def push_json(self, connection_id: str, payload: str) -> None:
        try:
            frame = json.loads(payload)
        except (TypeError, ValueError):
            logger.warning("ws hub: invalid json for %s", connection_id)
            return
        if isinstance(frame, dict):
            await self.push(connection_id, frame)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


__all__ = ["SendFn", "WebSocketHub", "stamp_thread_id"]
