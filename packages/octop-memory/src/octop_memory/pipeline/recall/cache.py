"""Short-term recall result cache (M4.11).

Cache key = ``(thread_id, query_hash)``; value = the rendered
``RecallResult``. TTL defaults to 60 seconds — long enough to absorb
the common pattern of "user submits same query twice in a row by
accident" and short enough that stale results don't poison the
prompt after a new atom lands.

This is a process-local in-memory cache (we don't persist it). The
recall pipeline calls :meth:`RecallCache.get` before doing any
backend work and :meth:`RecallCache.set` after a successful run.
Cache misses are silent and free.

Cache invalidation is intentionally lazy:
- TTL handles staleness for cold queries.
- The promotion path **does NOT bust the cache** — a fresh atom
  flowing in mid-thread will be picked up at the next 60-second
  boundary. This is acceptable because the surrounding turn already
  used the prior recall.

If we ever need eager invalidation (e.g. evaluation harnesses), the
caller can pass ``cache=None`` to skip caching entirely.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

# Imported lazily-typed; avoid circular at runtime.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octop_memory.pipeline.recall import RecallResult


DEFAULT_TTL_SECONDS = 60.0
DEFAULT_MAX_ENTRIES = 256
"""Soft cap on the in-memory cache size. We evict oldest first when full."""


def hash_query(query: str) -> str:
    """Stable hex digest used as the second half of the cache key."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


@dataclass
class _Entry:
    value: RecallResult
    expires_at: float


@dataclass
class RecallCache:
    """In-memory TTL cache for ``recall_for_prompt`` results."""

    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_entries: int = DEFAULT_MAX_ENTRIES
    _store: dict[tuple[str, str], _Entry] = field(default_factory=dict)
    _now_fn: Callable[[], float] = field(default=time.monotonic)

    def get(self, *, thread_id: str, query: str) -> RecallResult | None:
        key = (thread_id, hash_query(query))
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now_fn():
            del self._store[key]
            return None
        return entry.value

    def set(self, *, thread_id: str, query: str, value: RecallResult) -> None:
        key = (thread_id, hash_query(query))
        self._store[key] = _Entry(
            value=value,
            expires_at=self._now_fn() + self.ttl_seconds,
        )
        self._evict_if_needed()

    def clear(self) -> None:
        self._store.clear()

    def stats(self) -> dict[str, int]:
        return {"size": len(self._store)}

    # --- internal -------------------------------------------------------

    def _evict_if_needed(self) -> None:
        if len(self._store) <= self.max_entries:
            return
        # Oldest expiration first.
        ordered = sorted(self._store.items(), key=lambda kv: kv[1].expires_at)
        # Drop until we're back under the cap.
        for key, _ in ordered[: len(self._store) - self.max_entries]:
            self._store.pop(key, None)


__all__ = ["DEFAULT_MAX_ENTRIES", "DEFAULT_TTL_SECONDS", "RecallCache", "hash_query"]
