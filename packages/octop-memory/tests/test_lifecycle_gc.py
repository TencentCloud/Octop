"""Tests for lifecycle GC (M5.6, D47-C)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle import run_gc
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, Candidate, JournalEntry, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="gc", db_path=tmp_path / "gc.sqlite")
    return Memory(namespace="gc", backend=backend)


# ---------------------------------------------------------------------------
# Rejected candidates pass
# ---------------------------------------------------------------------------


class TestRejectedCandidatesPass:
    def test_old_rejected_deleted(self, memory: Memory) -> None:
        old = _now() - timedelta(days=60)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-old",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="x",
                    payload={},
                )
            ]
        )
        memory.add_candidate(
            Candidate(
                id="c-old",
                raw_event_ids=["r-old"],
                candidate_type="Fact",
                status="rejected",
                title="t",
                assertion="x",
                verbatim_quote="x",
                quote_event_id="r-old",
                subject_name="x",
                subject_entity_type="Fact",
                target_entity_id=None,
                confidence="low",
                importance="low",
                recommended_action="reject",
                promotion_reason="",
                extractor_version="v2.1",
                created_at=old,
                session_id="s",
                decided_at=old,
            )
        )

        before = memory.list_candidates(limit=100)
        assert len(before) == 1

        stats = run_gc(memory, rejected_candidate_days=30)
        assert stats.rejected_candidates_deleted == 1
        assert memory.list_candidates(limit=100) == []
        # GC no longer journals each delete (ADR-028).
        assert memory.list_journal(action="gc_rejected_candidate", limit=10) == []

    def test_recent_rejected_kept(self, memory: Memory) -> None:
        recent = _now()
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-recent",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=recent,
                    event_type="user_message",
                    content="y",
                    payload={},
                )
            ]
        )
        memory.add_candidate(
            Candidate(
                id="c-recent",
                raw_event_ids=["r-recent"],
                candidate_type="Fact",
                status="rejected",
                title="t",
                assertion="y",
                verbatim_quote="y",
                quote_event_id="r-recent",
                subject_name="y",
                subject_entity_type="Fact",
                target_entity_id=None,
                confidence="low",
                importance="low",
                recommended_action="reject",
                promotion_reason="",
                extractor_version="v2.1",
                created_at=recent,
                session_id="s",
                decided_at=recent,
            )
        )

        stats = run_gc(memory, rejected_candidate_days=30)
        assert stats.rejected_candidates_deleted == 0
        assert len(memory.list_candidates(limit=100)) == 1


# ---------------------------------------------------------------------------
# Deprecated atoms pass
# ---------------------------------------------------------------------------


class TestDeprecatedAtomsPass:
    def test_old_deprecated_deleted(self, memory: Memory) -> None:
        old = _now() - timedelta(days=120)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-old-atom",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="z",
                    payload={},
                )
            ]
        )
        atom = AtomCard(
            id="a-deprecated",
            entity_id="e1",
            candidate_id="c1",
            raw_event_ids=["r-old-atom"],
            assertion="old fact",
            verbatim_quote="old fact",
            quote_event_id="r-old-atom",
            search_terms=[],
            occurred_at=old,
            confidence="medium",
            importance="medium",
            created_at=old,
            superseded_by="newer-atom",
            deprecated_at=old,
        )
        memory.add_atom(atom)

        stats = run_gc(memory, deprecated_atom_days=90)
        assert stats.deprecated_atoms_deleted == 1
        assert memory.get_atom("a-deprecated") is None


# ---------------------------------------------------------------------------
# Orphan raw events pass
# ---------------------------------------------------------------------------


class TestOrphanRawPass:
    def test_orphan_raw_old_deleted(self, memory: Memory) -> None:
        old = _now() - timedelta(days=200)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-orphan",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="forgotten",
                    payload={},
                )
            ]
        )
        # No atom or candidate references r-orphan → orphan.

        stats = run_gc(memory, orphan_raw_days=180)
        assert stats.orphan_raw_events_deleted == 1
        assert memory.get_raw("r-orphan") is None

    def test_referenced_raw_kept(self, memory: Memory) -> None:
        old = _now() - timedelta(days=200)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-ref",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="referenced",
                    payload={},
                )
            ]
        )
        # Cite the raw via an atom so it's NOT an orphan.
        memory.add_atom(
            AtomCard(
                id="a-keep",
                entity_id="e1",
                candidate_id="c1",
                raw_event_ids=["r-ref"],
                assertion="x",
                verbatim_quote="x",
                quote_event_id="r-ref",
                search_terms=[],
                occurred_at=old,
                confidence="high",
                importance="high",
                created_at=old,
            )
        )

        stats = run_gc(memory, orphan_raw_days=180)
        assert stats.orphan_raw_events_deleted == 0
        assert memory.get_raw("r-ref") is not None

    def test_include_orphan_raw_false_skips_pass(self, memory: Memory) -> None:
        old = _now() - timedelta(days=200)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-skip",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="leave me",
                    payload={},
                )
            ]
        )
        stats = run_gc(memory, orphan_raw_days=180, include_orphan_raw=False)
        assert stats.orphan_raw_events_deleted == 0
        assert memory.get_raw("r-skip") is not None

    def test_orphan_gc_does_not_hydrate_raw_rows(self, memory: Memory, monkeypatch: pytest.MonkeyPatch) -> None:
        old = _now() - timedelta(days=200)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r-sql",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="x" * 1000,
                    payload={"blob": "y" * 1000},
                )
            ]
        )

        def boom(*_args: object, **_kwargs: object) -> list[object]:
            raise AssertionError("orphan GC must not hydrate full rows")

        monkeypatch.setattr(memory, "list_raw", boom)
        stats = run_gc(memory, orphan_raw_days=180)
        assert stats.orphan_raw_events_deleted == 1
        assert memory.get_raw("r-sql") is None


# ---------------------------------------------------------------------------
# Dry-run + counters
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_delete(self, memory: Memory) -> None:
        old = _now() - timedelta(days=100)
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r1",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=old,
                    event_type="user_message",
                    content="x",
                    payload={},
                )
            ]
        )
        memory.add_candidate(
            Candidate(
                id="c1",
                raw_event_ids=["r1"],
                candidate_type="Fact",
                status="rejected",
                title="t",
                assertion="x",
                verbatim_quote="x",
                quote_event_id="r1",
                subject_name="x",
                subject_entity_type="Fact",
                target_entity_id=None,
                confidence="low",
                importance="low",
                recommended_action="reject",
                promotion_reason="",
                extractor_version="v2.1",
                created_at=old,
                session_id="s",
                decided_at=old,
            )
        )

        stats = run_gc(memory, dry_run=True)
        assert stats.dry_run is True
        # Counter says 1 but actual table still has 1 row.
        assert stats.rejected_candidates_deleted == 1
        assert len(memory.list_candidates(limit=10)) == 1
        assert memory.list_journal(action="gc_rejected_candidate", limit=10) == []


class TestRetentionWindowOverrides:
    def test_zero_day_window_deletes_everything_decided(self, memory: Memory) -> None:
        when = _now()
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r1",
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=when,
                    event_type="user_message",
                    content="x",
                    payload={},
                )
            ]
        )
        memory.add_candidate(
            Candidate(
                id="c1",
                raw_event_ids=["r1"],
                candidate_type="Fact",
                status="rejected",
                title="t",
                assertion="x",
                verbatim_quote="x",
                quote_event_id="r1",
                subject_name="x",
                subject_entity_type="Fact",
                target_entity_id=None,
                confidence="low",
                importance="low",
                recommended_action="reject",
                promotion_reason="",
                extractor_version="v2.1",
                created_at=when,
                session_id="s",
                decided_at=when - timedelta(seconds=10),
            )
        )
        stats = run_gc(memory, rejected_candidate_days=0)
        assert stats.rejected_candidates_deleted == 1


# ---------------------------------------------------------------------------
# Journal retention (ADR-028)
# ---------------------------------------------------------------------------


def _journal(
    memory: Memory,
    *,
    action: str,
    when: datetime,
    note: str = "",
) -> None:
    memory.append_journal(
        JournalEntry(
            id=f"{action}-{when.isoformat()}-{note}",
            timestamp=when,
            action=action,  # type: ignore[arg-type]
            actor="auto",
            note=note,
        )
    )


class TestJournalRetention:
    def test_old_pipeline_rows_deleted_decisions_kept(self, memory: Memory) -> None:
        old = _now() - timedelta(days=30)
        recent = _now() - timedelta(days=1)
        _journal(memory, action="extract_run", when=old, note="old-run")
        _journal(memory, action="page_regen", when=old, note="old-page")
        _journal(memory, action="gc_rejected_candidate", when=old, note="legacy-gc")
        _journal(memory, action="extract_run", when=recent, note="fresh-run")
        _journal(memory, action="promote", when=old, note="keep-me")

        stats = run_gc(memory, journal_pipeline_days=14)
        assert stats.journal_rows_deleted == 3
        left = {row.note for row in memory.list_journal(limit=20)}
        assert left == {"fresh-run", "keep-me"}

    def test_dry_run_does_not_delete_journal(self, memory: Memory) -> None:
        old = _now() - timedelta(days=30)
        _journal(memory, action="extract_run", when=old, note="old")
        stats = run_gc(memory, journal_pipeline_days=14, dry_run=True)
        assert stats.journal_rows_deleted == 1
        assert len(memory.list_journal(action="extract_run", limit=10)) == 1

    def test_max_rows_caps_journal_pass(self, memory: Memory) -> None:
        old = _now() - timedelta(days=30)
        for i in range(5):
            _journal(memory, action="extract_run", when=old + timedelta(seconds=i), note=f"r{i}")
        stats = run_gc(memory, journal_pipeline_days=14, max_rows_per_pass=2)
        assert stats.journal_rows_deleted == 2
        assert len(memory.list_journal(action="extract_run", limit=10)) == 3


class TestBackendGuard:
    """GC is SQLite-only; non-SQLite backends must no-op before any SQL.

    Duck-typing on ``_conn`` / ``_ns`` used to let the Postgres backend through,
    which then ran ``{ns}_atoms`` SQL against Postgres. The resulting
    ``UndefinedTable`` aborted the shared transaction and every later memory
    write failed with ``InFailedSqlTransaction``.
    """

    def test_non_sqlite_backend_is_noop_without_touching_connection(self, memory: Memory) -> None:
        class FakePostgresBackend:
            """Exposes ``_conn`` / ``_ns`` like the real Postgres backend.

            The read methods return nothing so that, without the type check,
            GC walks past the candidate and atom passes into the orphan-raw
            pass — the one that issues ``{ns}_atoms`` SQL unconditionally.
            """

            _ns = "agent_hhzc5h"

            def __init__(self) -> None:
                self.executed: list[str] = []

            @property
            def _conn(self) -> FakePostgresBackend:
                return self

            def list_candidates(self, **_kwargs: object) -> list[object]:
                return []

            def list_atoms(self, **_kwargs: object) -> list[object]:
                return []

            def execute(self, sql: str, *_args: object) -> list[object]:
                self.executed.append(sql)
                return []

        backend = FakePostgresBackend()
        memory._backend = backend  # type: ignore[assignment]

        stats = run_gc(memory)

        assert stats.total_deleted == 0
        assert backend.executed == []
