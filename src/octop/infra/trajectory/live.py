"""In-process pub/sub for trajectory live SSE fan-out."""

from __future__ import annotations

import asyncio
from typing import Any


class TrajectoryLiveBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, thread_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(thread_id, set()).add(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        queues = self._subscribers.get(thread_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            del self._subscribers[thread_id]

    def publish(self, thread_id: str, message: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(thread_id, ())):
            queue.put_nowait(message)
