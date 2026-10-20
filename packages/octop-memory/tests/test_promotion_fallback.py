"""Tests for M2.8 fallback rules: 7-day stale promote + repeated-rejection escalate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory
from octop_memory.pipeline.promotion.fallback import (
    DEFAULT_REJECTION_THRESHOLD,
    DEFAULT_STALE_DAYS,
    run_fallback_pass,
)
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Candidate


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="m28", db_path=tmp_path / "m28.sqlite")
    return Memory(namespace="m28", backend=backend)


def _make_cand(
    cid: str,
    *,
    status: str = "needs_review",
    decided_at: datetime | None = None,
    created_at: datetime | None = None,
    assertion: str = "x",
    importance: str = "medium",
    confidence: str = "medium",
    subject_name: str = "Project",
    raw_event_id: str = "raw-1",
) -> Candidate:
    return Candidate(
        id=cid,
        raw_event_ids=[raw_event_id],
        candidate_type="Fact",
        status=status,  # type: ignore[arg-type]
        title="t",
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id=raw_event_id,
        subject_name=subject_name,
        subject_entity_type="Project",
        target_entity_id=None,
        confidence=confidence,  # type: ignore[arg-type]
        importance=importance,  # type: ignore[arg-type]
        recommended_action="needs_review",
        promotion_reason="",
        extractor_version="v2.1",
        created_at=created_at or _now(),
        decided_at=decided_at,
        session_id="s1",
    )


# ---------------------------------------------------------------------------
# Stale needs_review → auto-promote
# ---------------------------------------------------------------------------


class TestStalePromote:
    def test_stale_candidate_is_promoted_with_low_confidence(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        old_dt = _now() - timedelta(days=8)
        c = _make_cand(
            "c-old",
            status="needs_review",
            decided_at=old_dt,
            created_at=old_dt,
            raw_event_id=ev.id,
        )
        memory.add_candidate(c)

        result = run_fallback_pass(memory)

        assert c.id in result.stale_promoted
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "promoted"
        assert loaded.decided_by == "rule"
        # Atom written with confidence forced to low
        atoms = memory.list_atoms()
        assert len(atoms) == 1
        assert atoms[0].confidence == "low"
        # Journal: action=promote, actor=rule
        journal = memory.list_journal(target_candidate_id=c.id)
        assert any(j.action == "promote" and j.actor == "rule" for j in journal)

    def test_fresh_needs_review_left_alone(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        c = _make_cand(
            "c-fresh",
            status="needs_review",
            decided_at=_now(),
            raw_event_id=ev.id,
        )
        memory.add_candidate(c)
        result = run_fallback_pass(memory)
        assert c.id not in result.stale_promoted
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "needs_review"

    def test_threshold_is_configurable(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        # decided_at = 3d ago. Default 7d would skip; threshold=2 catches it.
        c = _make_cand(
            "c-3d",
            status="needs_review",
            decided_at=_now() - timedelta(days=3),
            raw_event_id=ev.id,
        )
        memory.add_candidate(c)
        result = run_fallback_pass(memory, stale_days=2)
        assert c.id in result.stale_promoted

    def test_idempotent_second_run_zero_action(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        old_dt = _now() - timedelta(days=10)
        c = _make_cand(
            "c-old",
            status="needs_review",
            decided_at=old_dt,
            created_at=old_dt,
            raw_event_id=ev.id,
        )
        memory.add_candidate(c)
        run_fallback_pass(memory)
        result2 = run_fallback_pass(memory)
        assert result2.stale_promoted == []


# ---------------------------------------------------------------------------
# Repeated rejection → escalate to needs_review
# ---------------------------------------------------------------------------


class TestRepeatedRejection:
    def test_pending_with_two_prior_rejections_escalates(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        # Two prior rejections of the same assertion
        for i in range(2):
            r = _make_cand(
                f"r-{i}",
                status="rejected",
                assertion="项目用 PostgreSQL",
                raw_event_id=ev.id,
            )
            memory.add_candidate(r)
        # New pending candidate with the same normalized assertion
        c = _make_cand(
            "c-pending",
            status="pending",
            assertion="  项目用  PostgreSQL ",  # whitespace differs, normalize collapses
            raw_event_id=ev.id,
        )
        memory.add_candidate(c)

        result = run_fallback_pass(memory)
        assert c.id in result.re_escalated
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "needs_review"
        # Journal records the conflict (re-escalation)
        journal = memory.list_journal(target_candidate_id=c.id)
        assert any(j.action == "conflict" and j.actor == "rule" for j in journal)

    def test_below_threshold_does_not_escalate(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        memory.add_candidate(_make_cand("r-1", status="rejected", assertion="X", raw_event_id=ev.id))
        c = _make_cand("c-1", status="pending", assertion="X", raw_event_id=ev.id)
        memory.add_candidate(c)
        # Threshold = 2; only 1 prior rejection
        result = run_fallback_pass(memory)
        assert c.id not in result.re_escalated
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "pending"

    def test_threshold_is_configurable(self, memory: Memory) -> None:
        ev = memory.add_raw(content="hi", event_type="user_message")
        memory.add_candidate(_make_cand("r-1", status="rejected", assertion="X", raw_event_id=ev.id))
        c = _make_cand("c-1", status="pending", assertion="X", raw_event_id=ev.id)
        memory.add_candidate(c)
        result = run_fallback_pass(memory, rejection_threshold=1)
        assert c.id in result.re_escalated


# ---------------------------------------------------------------------------
# Defaults sanity
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_defaults_match_design(self) -> None:
        assert DEFAULT_STALE_DAYS == 7
        assert DEFAULT_REJECTION_THRESHOLD == 2


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestFallbackCLI:
    def test_cli_runs_pass(self, tmp_path: Path) -> None:
        db = str(tmp_path / "fb.sqlite")
        # Seed a stale candidate
        backend = SqliteMemoryBackend(namespace="fb", db_path=db)
        m = Memory(namespace="fb", backend=backend)
        ev = m.add_raw(content="hi", event_type="user_message")
        old = _now() - timedelta(days=10)
        m.add_candidate(
            _make_cand(
                "c-old",
                status="needs_review",
                decided_at=old,
                created_at=old,
                raw_event_id=ev.id,
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db, "-n", "fb", "candidate", "fallback"],
        )
        assert result.exit_code == 0, result.output
        assert "stale_promoted=1" in result.output

    def test_cli_json_output(self, tmp_path: Path) -> None:
        db = str(tmp_path / "fb.sqlite")
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db, "-n", "fb", "--json", "candidate", "fallback"],
        )
        assert result.exit_code == 0, result.output
        import json

        payload = json.loads(result.output)
        assert "stale_promoted" in payload and "re_escalated" in payload
