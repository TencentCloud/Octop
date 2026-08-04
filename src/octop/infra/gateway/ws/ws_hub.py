"""In-process registry of Dashboard WebSocket connections."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

SendFn = Callable[[dict[str, Any]], Awaitable[None]]


class WebSocketHub:
    """Maps connection ids to async send callbacks for Dashboard chat.

    Also tracks per-thread subscriptions (one connection slot per thread) and
    in-memory "turn active" flags so reconnecting clients can resume live chunks.
    """

    def __init__(self) -> None:
        self._connections: dict[str, SendFn] = {}
        self._thread_subscriber: dict[str, str] = {}
        self._conn_thread: dict[str, str] = {}
        self._active_turns: set[str] = set()

    def register(self, connection_id: str, send_fn: SendFn) -> None:
        self._connections[connection_id] = send_fn

    def unregister(self, connection_id: str) -> None:
        self.unsubscribe_connection(connection_id)
        self._connections.pop(connection_id, None)

    def subscribe(self, thread_id: str, connection_id: str) -> None:
        """Bind *connection_id* as the sole subscriber for *thread_id*."""
        tid = thread_id.strip()
        if not tid or connection_id not in self._connections:
            return
        prev = self._conn_thread.pop(connection_id, None)
        if prev is not None and self._thread_subscriber.get(prev) == connection_id:
            self._thread_subscriber.pop(prev, None)
        existing = self._thread_subscriber.get(tid)
        if existing is not None and existing != connection_id:
            self._conn_thread.pop(existing, None)
        self._thread_subscriber[tid] = connection_id
        self._conn_thread[connection_id] = tid

    def unsubscribe_connection(self, connection_id: str) -> None:
        tid = self._conn_thread.pop(connection_id, None)
        if tid is not None and self._thread_subscriber.get(tid) == connection_id:
            self._thread_subscriber.pop(tid, None)

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
            await send_fn(frame)
        except Exception:
            logger.exception("ws hub: push failed for %s", connection_id)

    async def push_to_thread(self, thread_id: str, frame: dict[str, Any]) -> None:
        conn_id = self._thread_subscriber.get(thread_id.strip())
        if conn_id is None:
            logger.debug("ws hub: no subscriber for thread %s", thread_id)
            return
        await self.push(conn_id, frame)

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


__all__ = ["SendFn", "WebSocketHub"]
