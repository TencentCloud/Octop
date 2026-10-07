"""Asynchronous batching sink for Code Console agent events (S3).

Design:
- ``submit`` never blocks the ACP turn / SSE loop: it does a non-blocking
  ``put_nowait`` on a bounded queue; overflow is counted and dropped.
- A single worker drains the queue, assigns per-session monotonic ``seq``
  (baselines lazily from the repo), redacts registered secret fragments,
  and batch-inserts rows with bounded retries.
- Persistence failures degrade to logged + counted drops; they never
  propagate back into a turn.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from octop.infra.db.repos.agent_events import AgentEventRepo, AgentEventRow

logger = logging.getLogger(__name__)

_SENTINEL: dict[str, Any] = {"__sink_stop__": True}
_MIN_SECRET_LEN = 8
_REDACTED = "***REDACTED***"


class EventSink:
    def __init__(
        self,
        repo: AgentEventRepo,
        *,
        max_queue: int = 2000,
        flush_interval: float = 0.2,
        max_batch: int = 50,
        max_retries: int = 3,
    ) -> None:
        self._repo = repo
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)
        self._flush_interval = flush_interval
        self._max_batch = max_batch
        self._max_retries = max_retries
        self._worker: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._seq_base: dict[str, int] = {}
        self._secrets: set[str] = set()
        self.dropped_queue = 0
        self.dropped_failed = 0
        self.redacted_hits = 0
        self.written = 0

    # ----- lifecycle -----

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="coding-event-sink")

    async def aclose(self, *, flush_timeout: float = 2.0) -> None:
        if self._worker is None:
            return
        await self._queue.put(_SENTINEL)
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=flush_timeout)
        except TimeoutError:
            logger.warning("event sink flush timed out after %.1fs", flush_timeout)
            self._worker.cancel()

    # ----- public API -----

    def register_secret(self, fragment: str | None) -> None:
        if fragment and len(fragment) >= _MIN_SECRET_LEN:
            self._secrets.add(fragment)

    def submit(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        turn_id: str = "",
        is_error: bool = False,
        ts: float | None = None,
    ) -> None:
        """Non-blocking enqueue. Never raises to the caller."""
        if self._worker is None:
            self.start()
        item = {
            "event_id": uuid.uuid4().hex,
            "session_id": session_id,
            "kind": kind,
            "payload": payload if isinstance(payload, dict) else {"text": str(payload)},
            "turn_id": turn_id,
            "is_error": 1 if is_error else 0,
            "ts": ts if ts is not None else time.time(),
        }
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self.dropped_queue += 1
            logger.error("event sink queue full; dropping %s for %s", kind, session_id)

    async def flush_idle(self) -> None:
        """Wait until the queue is drained (tests / explicit flush points)."""
        await self._queue.join()

    def stats(self) -> dict[str, int]:
        return {
            "written": self.written,
            "dropped_queue": self.dropped_queue,
            "dropped_failed": self.dropped_failed,
            "redacted_hits": self.redacted_hits,
            "queued": self._queue.qsize(),
        }

    # ----- internals -----

    def _next_seq(self, session_id: str) -> int:
        if session_id not in self._seq_base:
            try:
                self._seq_base[session_id] = self._repo.max_seq(session_id)
            except Exception:  # noqa: BLE001 - baseline failure retries from 0 w/ ON CONFLICT
                logger.exception("failed to load seq baseline for %s", session_id)
                self._seq_base[session_id] = 0
        self._seq_base[session_id] += 1
        return self._seq_base[session_id]

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            out = value
            for secret in self._secrets:
                if secret in out:
                    out = out.replace(secret, _REDACTED)
                    self.redacted_hits += 1
            return out
        if isinstance(value, dict):
            return {k: self._redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        return value

    async def _drain_batch(self) -> list[dict[str, Any]]:
        first = await self._queue.get()
        if first is _SENTINEL:
            return [_SENTINEL]
        batch = [first]
        deadline = time.monotonic() + self._flush_interval
        while len(batch) < self._max_batch:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except TimeoutError:
                break
            if item is _SENTINEL:
                batch.append(_SENTINEL)
                break
            batch.append(item)
        return batch

    async def _write_batch(self, items: list[dict[str, Any]]) -> bool:
        rows = []
        for item in items:
            rows.append(
                AgentEventRow(
                    event_id=item["event_id"],
                    session_id=item["session_id"],
                    seq=self._next_seq(item["session_id"]),
                    ts=item["ts"],
                    kind=item["kind"],
                    payload=self._redact(item["payload"]),
                    turn_id=item.get("turn_id", ""),
                    is_error=bool(item.get("is_error")),
                )
            )
        delay = 0.05
        for attempt in range(self._max_retries):
            try:
                self._repo.insert_many(rows)
                self.written += len(rows)
                return True
            except Exception:  # noqa: BLE001
                if attempt == self._max_retries - 1:
                    logger.exception("event sink batch write failed permanently")
                    return False
                time.sleep(delay)  # tiny synchronous backoff; pool is sync anyway
                delay *= 2
        return False

    async def _run(self) -> None:
        try:
            while True:
                batch = await self._drain_batch()
                if batch and batch[-1] is _SENTINEL:
                    items = [b for b in batch if b is not _SENTINEL]
                    if items:
                        await self._write_batch(items)
                        for _ in items:
                            self._queue.task_done()
                    break
                ok = await self._write_batch(batch)
                for _ in batch:
                    self._queue.task_done()
                if not ok:
                    self.dropped_failed += len(batch)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - worker must never die silently
            logger.exception("event sink worker crashed")
        finally:
            self._worker = None
            self._stopped.set()
