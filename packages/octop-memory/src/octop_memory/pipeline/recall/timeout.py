"""Latency timeout primitives (D43-A — 100ms soft / 200ms hard).

The recall pipeline is on the user's per-turn critical path. Default
budgets:

- **atom FTS** ≤ 50ms
- **page lookup** ≤ 30ms
- **raw FTS** ≤ 30ms
- **total recall** ≤ 200ms (hard kill — return whatever's accumulated)

We expose two helpers:

- :func:`with_deadline` — context manager that runs a callable inside
  a thread and aborts if it doesn't return within ``budget_ms``. The
  thread is allowed to finish in the background (we can't kill native
  SQLite calls cleanly), but we don't wait for it.
- :class:`Stopwatch` — start / split timer to track elapsed budget
  across the pipeline so each stage knows the remaining slice.

Implementation note: we explicitly avoid ``signal.alarm`` because it
breaks under threading and on Windows. ``concurrent.futures.Future.result(timeout)``
is the simplest correct primitive.
"""

from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Callable
from dataclasses import dataclass, field

DEFAULT_TOTAL_BUDGET_MS = 200
"""Hard wall on the entire recall call."""

DEFAULT_ATOM_BUDGET_MS = 50
DEFAULT_PAGE_BUDGET_MS = 30
DEFAULT_RAW_BUDGET_MS = 30


class TimeoutExceededError(Exception):
    """Raised when one recall stage exceeds its time budget.

    Raised when a stage exceeds its individual budget. The caller
    typically catches and skips to the next source rather than
    propagating to the user."""

    def __init__(self, stage: str, budget_ms: int):
        super().__init__(f"stage {stage!r} exceeded {budget_ms}ms budget")
        self.stage = stage
        self.budget_ms = budget_ms


def with_deadline[T](
    fn: Callable[[], T],
    *,
    stage: str,
    budget_ms: int,
) -> T:
    """Run ``fn()`` in a worker thread, abort if it exceeds ``budget_ms``.

    Returns ``fn()``'s value on success. Raises :class:`TimeoutExceededError`
    on timeout. The worker thread is left running in the background;
    callers MUST tolerate the duplicate work (idempotent reads only).

    Single-shot per call: this allocates a fresh executor each time,
    which is ~50us overhead — fine for the per-turn recall path.
    """
    if budget_ms <= 0:
        # Caller has already burned the budget — short-circuit.
        raise TimeoutExceededError(stage=stage, budget_ms=budget_ms)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=budget_ms / 1000.0)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutExceededError(stage=stage, budget_ms=budget_ms) from exc


@dataclass
class Stopwatch:
    """Tracks elapsed time so each stage knows the remaining global budget.

    Usage::

        sw = Stopwatch(total_budget_ms=200)
        try:
            atoms = with_deadline(fetch_atoms, stage="atom",
                                  budget_ms=min(50, sw.remaining_ms))
        finally:
            sw.split("atom")
        # ...continue, each stage clamps to remaining...
    """

    total_budget_ms: int = DEFAULT_TOTAL_BUDGET_MS
    started_at: float = field(default_factory=time.monotonic)
    splits: dict[str, float] = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000.0)

    @property
    def remaining_ms(self) -> int:
        return max(0, self.total_budget_ms - self.elapsed_ms)

    @property
    def expired(self) -> bool:
        return self.remaining_ms <= 0

    def split(self, label: str) -> None:
        """Record a stage boundary for diagnostics."""
        self.splits[label] = (time.monotonic() - self.started_at) * 1000.0


__all__ = [
    "DEFAULT_ATOM_BUDGET_MS",
    "DEFAULT_PAGE_BUDGET_MS",
    "DEFAULT_RAW_BUDGET_MS",
    "DEFAULT_TOTAL_BUDGET_MS",
    "Stopwatch",
    "TimeoutExceededError",
    "with_deadline",
]
