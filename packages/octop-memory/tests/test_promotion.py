"""Tests for the M2.5 PromotionWorker (5-check rule path, no LLM)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.promotion import (
    CandidateDecision,
    PromotionResult,
    PromotionWorker,
    promote_candidates,
)
from octop_memory.pipeline.promotion.checks import (
    build_atom_from_candidate,
    check_conflict,
    check_duplicate,
    check_entity,
    check_evidence,
    check_value,
)
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, Candidate, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


def _raw(eid: str = "raw-1", content: str = "hi", session_id: str | None = "s1") -> RawEvent:
    return RawEvent(
        id=eid,
        host="dogfood",
        session_id=session_id,
        thread_id=None,
        user=None,
        timestamp=_now(),
        event_type="user_message",
        content=content,
        payload={},
    )


def _make_candidate(
    cid: str = "c1",
    *,
    subject_name: str = "陈立",
    subject_entity_type: str = "User",
    assertion: str = "我叫陈立",
    importance: str = "high",
    confidence: str = "high",
    raw_event_ids: list[str] | None = None,
    candidate_type: str = "Fact",
    quote_event_id: str = "raw-1",
) -> Candidate:
    return Candidate(
        id=cid,
        raw_event_ids=raw_event_ids if raw_event_ids is not None else ["raw-1"],
        candidate_type=candidate_type,  # type: ignore[arg-type]
        status="pending",
        title="t",
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id=quote_event_id,
        subject_name=subject_name,
        subject_entity_type=subject_entity_type,  # type: ignore[arg-type]
        target_entity_id=None,
        confidence=confidence,  # type: ignore[arg-type]
        importance=importance,  # type: ignore[arg-type]
        recommended_action="promote",
        promotion_reason="",
        extractor_version="v2.1",
        created_at=_now(),
        session_id="s1",
    )


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="m25", db_path=tmp_path / "m25.sqlite")
    return Memory(namespace="m25", backend=backend)


# ---------------------------------------------------------------------------
# Pure check-function tests (no DB)
# ---------------------------------------------------------------------------


class TestCheckValue:
    def test_low_low_drops(self) -> None:
        c = _make_candidate(importance="low", confidence="low")
        out = check_value(c)
        assert out is not None and out.kind == "drop"

    def test_low_medium_passes(self) -> None:
        c = _make_candidate(importance="low", confidence="medium")
        assert check_value(c) is None

    def test_high_high_passes(self) -> None:
        c = _make_candidate(importance="high", confidence="high")
        assert check_value(c) is None


class TestCheckEvidence:
    def test_empty_raw_event_ids_drops(self, memory: Memory) -> None:
        c = _make_candidate(raw_event_ids=[])
        out = check_evidence(c, evidence_store=memory)
        assert out is not None and out.kind == "drop"

    def test_missing_event_id_needs_review(self, memory: Memory) -> None:
        c = _make_candidate(raw_event_ids=["raw-missing"])
        out = check_evidence(c, evidence_store=memory)
        assert out is not None and out.kind == "needs_review"
        assert "raw-missing" in out.reason

    def test_all_events_present_passes(self, memory: Memory) -> None:
        memory.add_raw_batch([_raw("raw-1"), _raw("raw-2")])
        c = _make_candidate(raw_event_ids=["raw-1", "raw-2"])
        assert check_evidence(c, evidence_store=memory) is None


class TestCheckEntity:
    def test_alias_hit_returns_existing_id(self, memory: Memory) -> None:
        # Pre-seed entity + alias
        from octop_memory.types import Alias, Entity

        memory.add_entity(
            Entity(
                id="ent-1",
                entity_type="User",
                canonical_name="陈立",
                aliases=[],
                atom_count=0,
                created_at=_now(),
            )
        )
        memory.add_alias(
            Alias(
                alias="陈立",
                entity_id="ent-1",
                entity_type="User",
                created_by="rule",
                created_at=_now(),
            )
        )
        c = _make_candidate(subject_name="陈立")
        out = check_entity(c, resolver=memory)
        assert out.kind == "promote"
        assert out.entity_id == "ent-1"

    def test_canonical_name_hit_returns_existing_id(self, memory: Memory) -> None:
        from octop_memory.types import Entity

        memory.add_entity(
            Entity(
                id="ent-2",
                entity_type="Project",
                canonical_name="Octop Memory",
                aliases=[],
                atom_count=0,
                created_at=_now(),
            )
        )
        c = _make_candidate(subject_name="Octop Memory", subject_entity_type="Project")
        out = check_entity(c, resolver=memory)
        assert out.entity_id == "ent-2"

    def test_no_match_proposes_new_entity(self, memory: Memory) -> None:
        c = _make_candidate(subject_name="BrandNew", subject_entity_type="Project")
        out = check_entity(c, resolver=memory)
        assert out.kind == "promote"
        assert out.entity_id is None
        assert out.new_entity_canonical_name == "BrandNew"
        assert out.new_entity_type == "Project"

    def test_empty_subject_yields_needs_review(self, memory: Memory) -> None:
        c = _make_candidate(subject_name=" ")
        out = check_entity(c, resolver=memory)
        assert out.kind == "needs_review"


class TestCheckDuplicate:
    def test_exact_match_returns_merge(self, memory: Memory) -> None:
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-1",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="我用 PostgreSQL 16",
            verbatim_quote="我用 PostgreSQL 16",
            quote_event_id="raw-1",
            search_terms=["PostgreSQL"],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        c = _make_candidate(assertion="  我用 PostgreSQL 16  ")  # whitespace differences only
        out = check_duplicate(c, entity_id="ent-1", atom_lookup=memory)
        assert out is not None and out.kind == "merge"
        assert out.matched_atom_id == "atom-1"

    def test_different_assertion_passes(self, memory: Memory) -> None:
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-1",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="我用 PostgreSQL 16",
            verbatim_quote="我用 PostgreSQL 16",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        c = _make_candidate(assertion="我用 MySQL 8")
        assert check_duplicate(c, entity_id="ent-1", atom_lookup=memory) is None


class TestCheckDuplicateCrossEntity:
    """Tests for cross-entity exact-duplicate detection."""

    def test_same_entity_duplicate_still_detected(self, memory: Memory) -> None:
        """Regression: duplicates within the same entity are still correctly detected."""
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-1",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="用户喜欢喝咖啡",
            verbatim_quote="用户喜欢喝咖啡",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        c = _make_candidate(assertion="用户喜欢喝咖啡")
        out = check_duplicate(c, entity_id="ent-1", atom_lookup=memory)
        assert out is not None and out.kind == "merge"
        assert out.matched_atom_id == "atom-1"
        assert out.entity_id == "ent-1"

    def test_cross_entity_exact_duplicate_detected(self, memory: Memory) -> None:
        """A cross-entity exact duplicate is detected as merge, with entity_id
        pointing at the entity that already has the atom."""
        atom = AtomCard(
            id="atom-cross",
            entity_id="ent-A",  # exists under ent-A
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="用户喜欢喝咖啡",
            verbatim_quote="用户喜欢喝咖啡",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        # The candidate is routed to ent-B (a different entity), but its assertion
        # matches an atom under ent-A.
        c = _make_candidate(assertion="用户喜欢喝咖啡")
        out = check_duplicate(c, entity_id="ent-B", atom_lookup=memory)
        assert out is not None and out.kind == "merge"
        assert out.matched_atom_id == "atom-cross"
        assert out.entity_id == "ent-A"  # points at the entity that already has the atom

    def test_cross_entity_different_content_no_false_positive(self, memory: Memory) -> None:
        """Different content across entities should not produce a false positive."""
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-A",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="用户喜欢喝咖啡",
            verbatim_quote="用户喜欢喝咖啡",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        # Different content should not trigger a merge.
        c = _make_candidate(assertion="用户喜欢喝茶")
        out = check_duplicate(c, entity_id="ent-B", atom_lookup=memory)
        assert out is None

    def test_deprecated_atom_not_matched_cross_entity(self, memory: Memory) -> None:
        """A deprecated atom should not be matched by cross-entity duplicate detection."""

        atom = AtomCard(
            id="atom-dep",
            entity_id="ent-A",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="用户喜欢喝咖啡",
            verbatim_quote="用户喜欢喝咖啡",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        memory.deprecate_atom("atom-dep")  # Mark as deprecated.
        c = _make_candidate(assertion="用户喜欢喝咖啡")
        out = check_duplicate(c, entity_id="ent-B", atom_lookup=memory)
        assert out is None  # deprecated atom should not be matched


class TestCheckConflict:
    def test_negation_polarity_flip_is_conflict(self, memory: Memory) -> None:
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-1",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="项目用 PostgreSQL",
            verbatim_quote="项目用 PostgreSQL",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        c = _make_candidate(assertion="项目不用 PostgreSQL")
        out = check_conflict(c, entity_id="ent-1", atom_lookup=memory)
        assert out is not None and out.kind == "conflict"
        assert out.matched_atom_id == "atom-1"

    def test_same_polarity_no_conflict(self, memory: Memory) -> None:
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-1",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="项目用 PostgreSQL",
            verbatim_quote="项目用 PostgreSQL",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        c = _make_candidate(assertion="项目用 PostgreSQL 16")
        assert check_conflict(c, entity_id="ent-1", atom_lookup=memory) is None

    def test_unrelated_atom_ignored(self, memory: Memory) -> None:
        atom = AtomCard(
            id="atom-1",
            entity_id="ent-1",
            candidate_id="c0",
            raw_event_ids=["raw-1"],
            assertion="天气真好",
            verbatim_quote="天气真好",
            quote_event_id="raw-1",
            search_terms=[],
            occurred_at=_now(),
            confidence="high",
            importance="high",
            created_at=_now(),
        )
        memory.add_atom(atom)
        c = _make_candidate(assertion="项目不用 MongoDB")
        # No overlapping content tokens => conflict check should not fire
        # even though one is negated and the other isn't.
        assert check_conflict(c, entity_id="ent-1", atom_lookup=memory) is None


class TestBuildAtomFromCandidate:
    def test_field_mapping(self) -> None:
        c = _make_candidate(assertion="X", subject_name="陈立")
        when = _now()
        atom = build_atom_from_candidate(
            c,
            atom_id="atom-x",
            entity_id="ent-x",
            now=when,
        )
        assert atom.id == "atom-x"
        assert atom.entity_id == "ent-x"
        assert atom.candidate_id == c.id
        assert atom.raw_event_ids == c.raw_event_ids
        assert atom.assertion == c.assertion
        assert atom.verbatim_quote == c.verbatim_quote
        assert atom.quote_event_id == c.quote_event_id
        assert atom.search_terms == ["陈立"]
        assert atom.confidence == c.confidence
        assert atom.importance == c.importance
        assert atom.created_at == when


# ---------------------------------------------------------------------------
# Worker integration tests
# ---------------------------------------------------------------------------


class TestPromotionWorker:
    def test_happy_path_creates_entity_atom_alias_journal(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        # Override the auto-generated raw id to match candidate
        evs = memory.list_raw(limit=1)
        c = _make_candidate(raw_event_ids=[evs[0].id], quote_event_id=evs[0].id)
        memory.add_candidate(c)

        result = memory.promote_candidates([c])

        assert result.promoted == 1
        assert result.merged == 0
        assert result.dropped == 0
        decision = result.decisions[0]
        assert decision.outcome.kind == "promote"
        assert decision.atom is not None
        # Entity row exists
        ent = memory.get_entity(decision.outcome.entity_id or "")
        assert ent is not None and ent.canonical_name == "陈立"
        assert ent.atom_count == 1
        # Alias inserted
        from octop_memory.domain.alias import normalize_alias

        assert memory.find_entity_by_alias(normalize_alias("陈立")) is not None
        # Atom searchable
        atoms = memory.list_atoms(entity_id=ent.id, limit=10)
        assert len(atoms) == 1
        # Journal records promote
        journal = memory.list_journal(target_candidate_id=c.id, limit=10)
        assert len(journal) == 1
        assert journal[0].action == "promote"
        assert journal[0].actor == "auto"
        # Candidate status flipped
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "promoted"
        assert loaded.target_entity_id == ent.id

    def test_low_low_drops_with_reject_journal(self, memory: Memory) -> None:
        memory.add_raw(content="weather is nice", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        c = _make_candidate(
            cid="c-low",
            importance="low",
            confidence="low",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(c)

        result = memory.promote_candidates([c])

        assert result.dropped == 1
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "rejected"
        assert loaded.decided_by == "rule"
        # No atom was created
        assert memory.list_atoms(limit=10) == []
        # Journal recorded the rejection
        journal = memory.list_journal(target_candidate_id=c.id)
        assert len(journal) == 1
        assert journal[0].action == "reject"

    def test_missing_evidence_lands_needs_review_no_journal(self, memory: Memory) -> None:
        c = _make_candidate(raw_event_ids=["does-not-exist"], quote_event_id="does-not-exist")
        memory.add_candidate(c)

        result = memory.promote_candidates([c])

        assert result.needs_review == 1
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "needs_review"
        # needs_review is a queue, not a decision — journal must be empty.
        assert memory.list_journal(target_candidate_id=c.id) == []

    def test_second_candidate_reuses_entity_via_alias(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        first = _make_candidate(
            cid="c-1",
            assertion="我叫陈立",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        second = _make_candidate(
            cid="c-2",
            assertion="我是后端工程师",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(first)
        memory.add_candidate(second)

        result = memory.promote_candidates([first, second])

        assert result.promoted == 2
        # Both atoms hang off the same entity (only ONE entity row created).
        entities = memory.list_entities()
        assert len(entities) == 1
        ent = entities[0]
        assert ent.atom_count == 2

    def test_exact_duplicate_merges(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        first = _make_candidate(
            cid="c-1",
            assertion="项目用 PostgreSQL 16",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        dup = _make_candidate(
            cid="c-2",
            assertion="项目用 PostgreSQL 16",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(first)
        memory.add_candidate(dup)

        result = memory.promote_candidates([first, dup])

        assert result.promoted == 1
        assert result.merged == 1
        # Still only 1 atom row total.
        atoms = memory.list_atoms()
        assert len(atoms) == 1
        # Merge journal exists for the duplicate candidate.
        merge_entries = memory.list_journal(target_candidate_id=dup.id)
        assert len(merge_entries) == 1
        assert merge_entries[0].action == "merge"

    def test_polarity_flip_yields_conflict(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        first = _make_candidate(
            cid="c-1",
            assertion="项目用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        flip = _make_candidate(
            cid="c-2",
            assertion="项目不用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(first)
        memory.add_candidate(flip)

        result = memory.promote_candidates([first, flip])

        assert result.promoted == 1
        assert result.conflicts == 1
        loaded = memory.get_candidate(flip.id)
        assert loaded is not None and loaded.status == "conflict"
        # Conflict journal exists.
        conflict_entries = memory.list_journal(target_candidate_id=flip.id)
        assert len(conflict_entries) == 1
        assert conflict_entries[0].action == "conflict"

    def test_repromote_conflict_stays_conflict(self, memory: Memory) -> None:
        """Automatic worker must not silently accept a conflict on retry."""
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        first = _make_candidate(
            cid="c-1",
            assertion="项目用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        flip = _make_candidate(
            cid="c-2",
            assertion="项目不用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(first)
        memory.add_candidate(flip)
        memory.promote_candidates([first, flip])
        loaded = memory.get_candidate(flip.id)
        assert loaded is not None and loaded.status == "conflict"

        again = memory.promote_candidates([loaded])
        assert again.conflicts == 1
        assert again.promoted == 0
        assert memory.get_candidate(flip.id).status == "conflict"  # type: ignore[union-attr]

    def test_approve_conflict_supersedes_old_atom(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        first = _make_candidate(
            cid="c-1",
            assertion="项目用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        flip = _make_candidate(
            cid="c-2",
            assertion="项目不用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(first)
        memory.add_candidate(flip)
        memory.promote_candidates([first, flip])
        old = memory.list_atoms(include_deprecated=False)
        assert len(old) == 1
        old_id = old[0].id
        entity = memory.get_entity(old[0].entity_id)
        assert entity is not None
        assert entity.atom_count == 1

        loaded = memory.get_candidate(flip.id)
        assert loaded is not None
        decision = PromotionWorker(memory).approve(loaded)
        assert decision.outcome.kind == "promote"
        assert decision.atom is not None
        assert decision.atom.assertion == "项目不用 PostgreSQL"

        live = memory.list_atoms(include_deprecated=False)
        assert len(live) == 1
        assert live[0].id == decision.atom.id
        superseded = memory.get_atom(old_id)
        assert superseded is not None
        assert superseded.deprecated_at is not None
        assert superseded.superseded_by == decision.atom.id
        refreshed = memory.get_entity(live[0].entity_id)
        assert refreshed is not None
        assert refreshed.atom_count == 1
        cand = memory.get_candidate(flip.id)
        assert cand is not None and cand.status == "promoted"
        assert cand.decided_by == "user"

    def test_approve_needs_review_writes_atom(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        c = _make_candidate(
            cid="c-nr",
            assertion="用户喜欢早起",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(c)
        memory.update_candidate_status(c.id, status="needs_review", decided_by=None)
        loaded = memory.get_candidate(c.id)
        assert loaded is not None and loaded.status == "needs_review"

        decision = PromotionWorker(memory).approve(loaded)
        assert decision.outcome.kind == "promote"
        assert decision.atom is not None
        assert memory.get_candidate(c.id).status == "promoted"  # type: ignore[union-attr]
        assert len(memory.list_atoms()) == 1

    def test_already_promoted_candidates_are_skipped(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        c = _make_candidate(raw_event_ids=[evs[0].id], quote_event_id=evs[0].id)
        memory.add_candidate(c)
        memory.update_candidate_status(c.id, status="promoted", decided_by="auto")
        loaded = memory.get_candidate(c.id)
        assert loaded is not None

        # Re-running promote on already-promoted candidate should be a no-op.
        result = memory.promote_candidates([loaded])
        assert result.promoted == 0
        assert result.merged == 0
        assert result.decisions == []
        assert memory.list_atoms() == []

    def test_promote_pending_picks_up_pending_only(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        for i in range(3):
            memory.add_candidate(
                _make_candidate(
                    cid=f"c-{i}",
                    subject_name=f"S{i}",
                    assertion=f"我叫S{i}",  # distinct assertions to avoid duplicate merge
                    raw_event_ids=[evs[0].id],
                    quote_event_id=evs[0].id,
                )
            )
        # Mark one as already rejected
        memory.update_candidate_status("c-0", status="rejected", decided_by="user")

        worker = PromotionWorker(memory)
        result = worker.promote_pending(limit=10)
        # Only the 2 pending should have been processed.
        assert len(result.decisions) == 2
        assert result.promoted == 2

    def test_top_level_function_works(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        c = _make_candidate(raw_event_ids=[evs[0].id], quote_event_id=evs[0].id)
        memory.add_candidate(c)
        result = promote_candidates(memory, [c])
        assert isinstance(result, PromotionResult)
        assert result.promoted == 1


class TestCandidateDecisionShape:
    def test_decision_carries_atom_on_promote(self, memory: Memory) -> None:
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        c = _make_candidate(raw_event_ids=[evs[0].id], quote_event_id=evs[0].id)
        memory.add_candidate(c)
        result = memory.promote_candidates([c])
        d: CandidateDecision = result.decisions[0]
        assert d.atom is not None
        assert d.atom.candidate_id == c.id


# ---------------------------------------------------------------------------
# SQLite + Postgres: user-approve a conflict (dashboard 采纳 path)
# ---------------------------------------------------------------------------

_PG_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://localhost/octop_memory_test")


@pytest.fixture(params=["sqlite", "postgres"])
def memory_both(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Memory]:
    """Same approve path against each backend; Postgres skips when unreachable."""
    if request.param == "sqlite":
        yield Memory(namespace="promo_both", backend_config={"db_path": str(tmp_path / "both.sqlite")})
        return

    request.getfixturevalue("postgres_dsn")
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

    ns = f"promo_{uuid.uuid4().hex[:12]}"
    backend = PostgresMemoryBackend(namespace=ns, dsn=_PG_DSN)
    memory = Memory(namespace=ns, backend=backend)
    try:
        yield memory
    finally:
        if not backend._closed:
            backend.purge_namespace()
        backend.close()


class TestApproveConflictBothBackends:
    def test_approve_conflict_supersedes_on_both_backends(self, memory_both: Memory) -> None:
        memory = memory_both
        memory.add_raw(content="hi", event_type="user_message", host="t")
        evs = memory.list_raw(limit=1)
        first = _make_candidate(
            cid="c-1",
            assertion="项目用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        flip = _make_candidate(
            cid="c-2",
            assertion="项目不用 PostgreSQL",
            raw_event_ids=[evs[0].id],
            quote_event_id=evs[0].id,
        )
        memory.add_candidate(first)
        memory.add_candidate(flip)
        auto = memory.promote_candidates([first, flip])
        assert auto.promoted == 1
        assert auto.conflicts == 1
        old = memory.list_atoms(include_deprecated=False)
        assert len(old) == 1

        loaded = memory.get_candidate(flip.id)
        assert loaded is not None and loaded.status == "conflict"
        decision = PromotionWorker(memory).approve(loaded)
        assert decision.atom is not None
        live = memory.list_atoms(include_deprecated=False)
        assert [a.assertion for a in live] == ["项目不用 PostgreSQL"]
        superseded = memory.get_atom(old[0].id)
        assert superseded is not None
        assert superseded.deprecated_at is not None
        assert superseded.superseded_by == decision.atom.id
        entity = memory.get_entity(live[0].entity_id)
        assert entity is not None
        assert entity.atom_count == 1
