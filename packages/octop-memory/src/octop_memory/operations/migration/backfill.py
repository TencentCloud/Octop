"""``memory backfill`` — replay extractor on historical raw events (5.5).

Workflow::

    raw_events table (since cutoff)
      ↓ group by session_id
      ↓
    for each session: extract_session(...)  ← M2 helper
      ↓ candidates table
      ↓
    promote_candidates(...)                  ← M2 promotion
      ↓ atoms + entities + journal

D48-B rate limiting: cap LLM calls per minute via a sliding-window
counter. Each ``extract_session`` makes exactly **1 LLM call**, so the
effective cap = sessions/minute. Default 30/min — well below typical
host LLM hard caps (60/min for OpenAI tier-1, 100/min for Anthropic).

Resumability: a ``--resume-from <session_id>`` flag lets the user
pick up from an interrupted run; we sort sessions by their earliest
raw event timestamp and skip everything before the resume point.

Out of scope for M5:
- Backfill from external host files (USER.md / MEMORY.md). Tracked
  as M5.5+ feature when M1.W3 host index lands.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from octop_memory.pipeline.extractor import CandidateExtractor, extract_session
from octop_memory.pipeline.promotion import promote_candidates
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

if TYPE_CHECKING:
    from octop_memory.core import Memory


_LOG = logging.getLogger(__name__)


DEFAULT_RATE_LIMIT_PER_MINUTE = 30
"""D48-B: max LLM calls per 60-second sliding window. Override via
:func:`backfill_namespace`'s ``rate_limit_per_minute`` argument."""


@dataclass
class SessionResult:
    """Outcome of backfilling one session."""

    session_id: str
    raw_event_count: int
    candidate_count: int = 0
    promoted_atom_count: int = 0
    skipped_reason: str | None = None
    """If non-None, the session was skipped (e.g. already had
    candidates, or extractor failed). Successful runs leave this
    None."""


@dataclass
class BackfillSummary:
    """Aggregate counts for one namespace backfill."""

    sessions_seen: int = 0
    sessions_processed: int = 0
    sessions_skipped: int = 0
    total_candidates: int = 0
    total_promoted: int = 0
    llm_calls: int = 0
    """One LLM call per processed session under the current extractor;
    update if extractor calling pattern changes."""

    started_at: datetime | None = None
    finished_at: datetime | None = None
    sessions: list[SessionResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rate limiter (D48-B sliding window)
# ---------------------------------------------------------------------------


class _SlidingWindowLimiter:
    """At most ``cap`` events per ``window_seconds``.

    Single-threaded; we keep a deque of timestamps and pop expired
    entries before each ``acquire()``. If we'd breach the cap,
    ``acquire()`` sleeps for the residual time.

    No-op cap (``<= 0``) disables limiting entirely so unit tests can
    call without any clock dependency.
    """

    def __init__(self, *, cap: int, window_seconds: float = 60.0) -> None:
        self._cap = cap
        self._window = window_seconds
        self._events: deque[float] = deque()

    def acquire(self) -> float:
        """Block until a new call is allowed; return the slept time (s)."""
        if self._cap <= 0:
            return 0.0
        now = time.monotonic()
        cutoff = now - self._window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()
        slept = 0.0
        if len(self._events) >= self._cap:
            wait_until = self._events[0] + self._window
            slept = max(0.0, wait_until - now)
            time.sleep(slept)
            now = time.monotonic()
            cutoff = now - self._window
            while self._events and self._events[0] < cutoff:
                self._events.popleft()
        self._events.append(now)
        return slept


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def backfill_namespace(
    memory: Memory,
    *,
    extractor: CandidateExtractor,
    since: datetime | None = None,
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
    skip_sessions_with_existing_candidates: bool = True,
    resume_from: str | None = None,
    promote: bool = True,
) -> BackfillSummary:
    """Replay the candidate extractor over historical raw events.

    Args:
        memory: target backend.
        extractor: reused :class:`CandidateExtractor` (caller owns LLM
            client lifecycle).
        since: lower bound on raw event timestamps. ``None`` means
            "all sessions".
        rate_limit_per_minute: see :data:`DEFAULT_RATE_LIMIT_PER_MINUTE`.
            Set to 0 to disable.
        skip_sessions_with_existing_candidates: if True (the default),
            sessions that already have any candidate row are skipped to
            avoid duplicating work after partial runs.
        resume_from: skip every session up to and including this id.
        promote: if True, run :func:`promote_candidates` after extraction
            so atoms / entities / journal stay consistent. Disable if
            you want to inspect candidates before committing them.
    """
    summary = BackfillSummary(started_at=datetime.now(tz=UTC))
    limiter = _SlidingWindowLimiter(cap=rate_limit_per_minute)

    sessions = _collect_sessions(memory, since=since)
    if resume_from is not None:
        sessions = _drop_until_after(sessions, resume_from)
    summary.sessions_seen = len(sessions)

    existing_candidate_sessions: set[str] = set()
    if skip_sessions_with_existing_candidates:
        existing_candidate_sessions = _sessions_with_candidates(memory)

    for session_id in sessions:
        raw_count = _session_raw_count(memory, session_id)

        if session_id in existing_candidate_sessions:
            summary.sessions.append(
                SessionResult(
                    session_id=session_id,
                    raw_event_count=raw_count,
                    skipped_reason="already has candidates",
                )
            )
            summary.sessions_skipped += 1
            continue

        # Throttle BEFORE the LLM call so a burst of 100 sessions
        # doesn't all hit the host within 1 ms.
        slept = limiter.acquire()
        if slept > 0:
            _LOG.debug("rate-limit slept %.2fs before session %s", slept, session_id)

        try:
            result = extract_session(memory=memory, extractor=extractor, session_id=session_id)
        except REPORTABLE_ERRORS as exc:
            _LOG.warning("backfill: extractor failed for session %s: %s", session_id, exc)
            summary.sessions.append(
                SessionResult(
                    session_id=session_id,
                    raw_event_count=raw_count,
                    skipped_reason=f"extractor_error: {exc}",
                )
            )
            summary.sessions_skipped += 1
            continue

        summary.llm_calls += 1
        candidates = list(result.candidates)
        promoted = 0
        if promote and candidates:
            promo = promote_candidates(memory, candidates)
            promoted = promo.promoted
            summary.llm_calls += promo.llm_calls

        summary.sessions.append(
            SessionResult(
                session_id=session_id,
                raw_event_count=raw_count,
                candidate_count=len(candidates),
                promoted_atom_count=promoted,
            )
        )
        summary.sessions_processed += 1
        summary.total_candidates += len(candidates)
        summary.total_promoted += promoted

    summary.finished_at = datetime.now(tz=UTC)
    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_sessions(memory: Memory, *, since: datetime | None) -> list[str]:
    """Return session ids with raw events at or after ``since``.

    Return every session_id with raw events ≥ ``since``, ordered by
    earliest event timestamp ascending so resume-from is meaningful."""
    sessions: dict[str, datetime] = {}
    for event in memory.list_raw(limit=10**9):
        if since is not None and event.timestamp < since:
            continue
        if not event.session_id:
            continue
        prev = sessions.get(event.session_id)
        if prev is None or event.timestamp < prev:
            sessions[event.session_id] = event.timestamp
    return [sid for sid, _ in sorted(sessions.items(), key=lambda kv: kv[1])]


def _drop_until_after(sessions: list[str], pivot: str) -> list[str]:
    """Return the suffix of ``sessions`` after ``pivot``.

    Return the suffix of ``sessions`` AFTER ``pivot``. If ``pivot`` not
    found, returns the original list (defensive — better to over-replay
    than to silently skip everything)."""
    try:
        idx = sessions.index(pivot)
    except ValueError:
        return sessions
    return sessions[idx + 1 :]


def _session_raw_count(memory: Memory, session_id: str) -> int:
    return len(memory.list_raw(session_id=session_id, limit=10**9))


def _sessions_with_candidates(memory: Memory) -> set[str]:
    out: set[str] = set()
    for cand in memory.list_candidates(limit=10**9):
        if cand.session_id:
            out.add(cand.session_id)
    return out


__all__ = [
    "DEFAULT_RATE_LIMIT_PER_MINUTE",
    "BackfillSummary",
    "SessionResult",
    "backfill_namespace",
]
