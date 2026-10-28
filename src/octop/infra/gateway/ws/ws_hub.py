"""In-process registry of Dashboard WebSocket connections."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

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
        # thread_id -> time.monotonic() stamp of last pushed frame.
        # A turn whose caller task is dropped (client disconnect, process crash)
        # never reaches mark_turn_idle; evict_stale_turns prunes these orphans
        # so clients are not stuck seeing turn_active=true forever (issue #2456).
        self._active_turns: dict[str, float] = {}

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

    def mark_turn_active(self, thread_id: str) -> None:
        tid = thread_id.strip()
        if tid:
            self._active_turns[tid] = time.monotonic()

    def mark_turn_idle(self, thread_id: str) -> None:
        self._active_turns.pop(thread_id.strip(), None)

    def bump_turn_activity(self, thread_id: str) -> None:
        """Refresh the idle timer for *thread_id* if it is tracked as active."""
        tid = thread_id.strip()
        if tid and tid in self._active_turns:
            self._active_turns[tid] = time.monotonic()

    def evict_stale_turns(self, max_quiet_seconds: float = 30.0) -> int:
        """Prune active-turn entries that have had no frames pushed for *max_quiet_seconds*.

        A drop-frame (disconnect, process crash, task cancellation) leaves the
        ``finally`` block in ``WebSocketChannel.handle_inbound`` unreachable,
        so ``mark_turn_idle`` never runs. Repeated calls to this method (lazily
        from :meth:`is_turn_active`) heal the flag leak so that clients no
        longer see ``turn_active=true`` on a fully-idle thread (issue #2456).
        """
        if not self._active_turns:
            return 0
        now = time.monotonic()
        stale = [
            tid
            for tid, last_push in self._active_turns.items()
            if now - last_push > max_quiet_seconds
        ]
        for tid in stale:
            self._active_turns.pop(tid, None)
        if stale:
            logger.info(
                "ws hub: evicted %d stale active-turn entries (quiet >%.1fs): %s",
                len(stale),
                max_quiet_seconds,
                stale,
            )
        return len(stale)

    def is_turn_active(self, thread_id: str) -> bool:
        self.evict_stale_turns()
        tid = thread_id.strip()
        return tid in self._active_turns

    def has_subscribers(self, thread_id: str) -> bool:
        """True when at least one Dashboard socket is bound to *thread_id*."""
        tid = thread_id.strip()
        return bool(tid and self._thread_subscribers.get(tid))

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
        # Every frame delivered to the thread counts as activity; this keeps
        # live turns' TTL fresh so evict_stale_turns does not kill them while
        # the harness still emits chunks. Orphans (no subscriber → early
        # return here, or harness stalled) stop getting bumped and will be
        # pruned on the next is_turn_active() check.
        self.bump_turn_activity(tid)
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
