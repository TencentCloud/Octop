"""Tests for backfill (M5.5) — rate limiter + session iteration."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.operations.migration.backfill import (
    _SlidingWindowLimiter,
    backfill_namespace,
)
from octop_memory.pipeline.extractor import ExtractionResult
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Candidate, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Sliding window limiter
# ---------------------------------------------------------------------------


class TestSlidingWindowLimiter:
    def test_no_cap_no_sleep(self) -> None:
        lim = _SlidingWindowLimiter(cap=0)
        slept = lim.acquire()
        assert slept == 0.0

    def test_within_cap_no_sleep(self) -> None:
        lim = _SlidingWindowLimiter(cap=10, window_seconds=60)
        for _ in range(5):
            assert lim.acquire() == 0.0

    def test_over_cap_sleeps(self) -> None:
        lim = _SlidingWindowLimiter(cap=2, window_seconds=0.1)
        # Burn the budget.
        lim.acquire()
        lim.acquire()
        # Third call must sleep until the oldest event ages out.
        start = time.monotonic()
        lim.acquire()
        elapsed = time.monotonic() - start
        # Sleep should be roughly the window duration.
        assert elapsed >= 0.05  # allow generous lower bound (timer jitter)


# ---------------------------------------------------------------------------
# Backfill orchestration
# ---------------------------------------------------------------------------


class _FakeExtractor:
    """Stand-in for :class:`CandidateExtractor` in tests.

    Tracks the sessions it was asked to process and emits one synthetic
    candidate per session so the rest of the pipeline (promotion, etc.)
    has something to work with.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, raw_events: list, *, session_id: str | None = None):  # type: ignore[override]
        self.calls.append(session_id or "")
        return ExtractionResult(candidates=[])


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="bf", db_path=tmp_path / "bf.sqlite")
    return Memory(namespace="bf", backend=backend)


def _add_session(memory: Memory, session_id: str, *, when: datetime) -> None:
    memory.add_raw_batch(
        [
            RawEvent(
                id=f"raw-{session_id}",
                host="t",
                session_id=session_id,
                thread_id=None,
                user=None,
                timestamp=when,
                event_type="user_message",
                content=f"hello {session_id}",
                payload={},
            )
        ]
    )


class TestBackfillIteration:
    def test_processes_each_session_once(self, memory: Memory) -> None:
        when = _now() - timedelta(days=10)
        for sid in ("s-a", "s-b", "s-c"):
            _add_session(memory, sid, when=when)

        fake = _FakeExtractor()
        summary = backfill_namespace(
            memory,
            extractor=fake,  # type: ignore[arg-type]
            rate_limit_per_minute=0,  # no throttling in tests
            promote=False,
        )
        assert summary.sessions_seen == 3
        assert summary.sessions_processed == 3
        assert sorted(fake.calls) == ["s-a", "s-b", "s-c"]

    def test_since_filter_excludes_old_sessions(self, memory: Memory) -> None:
        old = _now() - timedelta(days=200)
        recent = _now() - timedelta(days=2)
        _add_session(memory, "old", when=old)
        _add_session(memory, "recent", when=recent)

        fake = _FakeExtractor()
        summary = backfill_namespace(
            memory,
            extractor=fake,  # type: ignore[arg-type]
            since=_now() - timedelta(days=30),
            rate_limit_per_minute=0,
            promote=False,
        )
        assert summary.sessions_seen == 1
        assert fake.calls == ["recent"]

    def test_skip_sessions_with_existing_candidates(self, memory: Memory) -> None:
        when = _now() - timedelta(days=5)
        _add_session(memory, "s-with-cand", when=when)
        memory.add_candidate(
            Candidate(
                id="c1",
                raw_event_ids=["raw-s-with-cand"],
                candidate_type="Fact",
                status="pending",
                title="t",
                assertion="x",
                verbatim_quote="x",
                quote_event_id="raw-s-with-cand",
                subject_name="x",
                subject_entity_type="Fact",
                target_entity_id=None,
                confidence="medium",
                importance="medium",
                recommended_action="promote",
                promotion_reason="",
                extractor_version="v2.1",
                created_at=when,
                session_id="s-with-cand",
            )
        )
        _add_session(memory, "s-fresh", when=when)

        fake = _FakeExtractor()
        summary = backfill_namespace(
            memory,
            extractor=fake,  # type: ignore[arg-type]
            rate_limit_per_minute=0,
            promote=False,
        )
        assert summary.sessions_seen == 2
        assert summary.sessions_processed == 1
        assert summary.sessions_skipped == 1
        assert fake.calls == ["s-fresh"]

    def test_resume_from(self, memory: Memory) -> None:
        when = _now() - timedelta(days=10)
        for idx, sid in enumerate(("a", "b", "c")):
            _add_session(memory, sid, when=when + timedelta(seconds=idx))

        fake = _FakeExtractor()
        summary = backfill_namespace(
            memory,
            extractor=fake,  # type: ignore[arg-type]
            resume_from="a",
            rate_limit_per_minute=0,
            promote=False,
        )
        # Should have skipped 'a' (resume marker) and processed b, c.
        assert summary.sessions_seen == 2
        assert sorted(fake.calls) == ["b", "c"]

    def test_extractor_failure_skips_session(self, memory: Memory) -> None:
        when = _now() - timedelta(days=1)
        _add_session(memory, "boom", when=when)

        class _Boom:
            def extract(self, raw_events, *, session_id=None):
                raise RuntimeError("LLM timeout")

        summary = backfill_namespace(
            memory,
            extractor=_Boom(),  # type: ignore[arg-type]
            rate_limit_per_minute=0,
            promote=False,
        )
        assert summary.sessions_processed == 0
        assert summary.sessions_skipped == 1
        assert any("extractor_error" in (s.skipped_reason or "") for s in summary.sessions)
