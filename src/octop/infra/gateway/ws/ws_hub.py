"""In-process registry of Dashboard WebSocket connections."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

SendFn = Callable[[dict[str, Any]], Awaitable[None]]
CloseFn = Callable[[], Awaitable[None]]


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

    def __init__(self, *, send_timeout: float = 5.0, close_timeout: float = 1.0) -> None:
        self._send_timeout = send_timeout
        self._close_timeout = close_timeout
        self._connections: dict[str, SendFn] = {}
        self._close_callbacks: dict[str, CloseFn] = {}
        self._thread_subscribers: dict[str, set[str]] = {}
        self._conn_thread: dict[str, str] = {}
        self._user_conns: dict[int, set[str]] = {}
        self._conn_user: dict[str, int] = {}
        self._active_turns: set[str] = set()

    def register(
        self,
        connection_id: str,
        send_fn: SendFn,
        *,
        user_id: int | None = None,
        close_fn: CloseFn | None = None,
    ) -> None:
        self._unbind_user(connection_id)
        self._connections[connection_id] = send_fn
        self._close_callbacks.pop(connection_id, None)
        if close_fn is not None:
            self._close_callbacks[connection_id] = close_fn
        if user_id is None:
            return
        self._conn_user[connection_id] = user_id
        self._user_conns.setdefault(user_id, set()).add(connection_id)

    def unregister(self, connection_id: str) -> None:
        self.unsubscribe_connection(connection_id)
        self._unbind_user(connection_id)
        self._connections.pop(connection_id, None)
        self._close_callbacks.pop(connection_id, None)

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
            self._active_turns.add(tid)

    def mark_turn_idle(self, thread_id: str) -> None:
        self._active_turns.discard(thread_id.strip())

    def is_turn_active(self, thread_id: str) -> bool:
        return thread_id.strip() in self._active_turns

    async def push(self, connection_id: str, frame: dict[str, Any]) -> None:
        send_fn = self._connections.get(connection_id)
        if send_fn is None:
            logger.debug("ws hub: connection %s not found", connection_id)
            return
        try:
            # A browser that stops reading must not stall the turn iterator
            # indefinitely (including delivery to healthy subscribers).
            async with asyncio.timeout(self._send_timeout):
                await send_fn(frame)
        except TimeoutError:
            logger.warning("ws hub: send timed out for %s; disconnecting", connection_id)
        except Exception:
            logger.exception("ws hub: push failed for %s", connection_id)
        else:
            return

        # A callback may have been replaced while this send was in flight.
        if self._connections.get(connection_id) is not send_fn:
            return
        close_fn = self._close_callbacks.get(connection_id)
        self.unregister(connection_id)
        if close_fn is not None:
            try:
                # Closing a congested socket can also block. Bound cleanup,
                # while letting the client reconnect and recover turn status.
                async with asyncio.timeout(self._close_timeout):
                    await close_fn()
            except Exception:
                logger.warning("ws hub: close failed for %s", connection_id, exc_info=True)

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
