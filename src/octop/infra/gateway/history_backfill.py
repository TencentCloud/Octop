"""Bounded single-worker queue for legacy checkpoint history projection."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

BackfillWork = Callable[[], Awaitable[None]]
logger = logging.getLogger(__name__)


class HistoryBackfillQueue:
    """Deduplicate jobs and ensure only one huge checkpoint is decoded at once."""

    def __init__(self, *, max_pending: int = 100) -> None:
        self._max_pending = max_pending
        self._queue: asyncio.Queue[tuple[str, BackfillWork]] = asyncio.Queue(maxsize=max_pending)
        self._known: set[str] = set()
        self._worker: asyncio.Task[None] | None = None

    def enqueue(self, key: str, work: BackfillWork) -> bool:
        if key in self._known:
            return True
        if self._queue.full():
            return False
        self._known.add(key)
        self._queue.put_nowait((key, work))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="history-backfill")
        return True

    @property
    def available_slots(self) -> int:
        """Number of bounded waiting slots available to bulk migration."""
        return max(0, self._max_pending - self._queue.qsize())

    @property
    def active_jobs(self) -> int:
        """Queued plus currently running deduplicated jobs."""
        return len(self._known)

    def contains(self, key: str) -> bool:
        """Whether this process is actively responsible for a persisted job."""
        return key in self._known

    async def _run(self) -> None:
        while True:
            key, work = await self._queue.get()
            try:
                await work()
            except Exception:
                logger.exception("legacy history backfill job failed: %s", key)
            finally:
                self._known.discard(key)
                self._queue.task_done()

    async def close(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
