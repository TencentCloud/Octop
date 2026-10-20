"""Tests for M2 Candidate / AtomCard / Entity / Alias / JournalEntry dataclasses.

This test file covers schema-only behaviour: instantiation, field defaults,
literal type constraints (compile-time only — mypy enforces those), and
mutation isolation. Backend persistence behaviour lives in
``test_candidate_backend.py``.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime

from octop_memory.types import (
    Alias,
    AtomCard,
    Candidate,
    Entity,
    JournalEntry,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


def test_candidate_minimal_construction() -> None:
    cand = Candidate(
        id="cand-1",
        raw_event_ids=["raw-1"],
        candidate_type="Fact",
        status="pending",
        title="Octop Memory mode decision",
        assertion="先做 Augment 模式，不做 Replace",
        verbatim_quote="先做 Augment 模式，不做 Replace",
        quote_event_id="raw-1",
        subject_name="Octop Memory",
        subject_entity_type="Project",
        target_entity_id=None,
        confidence="high",
        importance="high",
        recommended_action="promote",
        promotion_reason="explicit decision keyword",
        extractor_version="v2.0",
        created_at=_now(),
    )

    assert cand.decided_at is None
    assert cand.decided_by is None
    assert cand.session_id is None
    assert cand.payload == {}
    # Anti-dilution rule: high importance => assertion == verbatim_quote.
    # The dataclass itself does not enforce this; the extractor / promotion
    # worker does. But we verify the data layout supports it.
    assert cand.assertion == cand.verbatim_quote


def test_candidate_payload_isolation() -> None:
    """Each Candidate should get its own payload dict, not a shared one."""
    a = Candidate(
        id="a",
        raw_event_ids=["r"],
        candidate_type="Fact",
        status="pending",
        title="t",
        assertion="x",
        verbatim_quote="x",
        quote_event_id="r",
        subject_name="s",
        subject_entity_type="Fact",
        target_entity_id=None,
        confidence="low",
        importance="low",
        recommended_action="promote",
        promotion_reason="r",
        extractor_version="v",
        created_at=_now(),
    )
    b = Candidate(
        id="b",
        raw_event_ids=["r"],
        candidate_type="Fact",
        status="pending",
        title="t",
        assertion="y",
        verbatim_quote="y",
        quote_event_id="r",
        subject_name="s",
        subject_entity_type="Fact",
        target_entity_id=None,
        confidence="low",
        importance="low",
        recommended_action="promote",
        promotion_reason="r",
        extractor_version="v",
        created_at=_now(),
    )
    a.payload["foo"] = 1
    assert b.payload == {}


def test_candidate_field_count_locked() -> None:
    """Adding fields silently is dangerous (migration / serialization).
    This test fails when a field is added — forcing an explicit review.
    """
    assert {f.name for f in fields(Candidate)} == {
        "id",
        "raw_event_ids",
        "candidate_type",
        "status",
        "title",
        "assertion",
        "verbatim_quote",
        "quote_event_id",
        "subject_name",
        "subject_entity_type",
        "target_entity_id",
        "confidence",
        "importance",
        "recommended_action",
        "promotion_reason",
        "extractor_version",
        "created_at",
        "decided_at",
        "decided_by",
        "session_id",
        "payload",
    }


# ---------------------------------------------------------------------------
# AtomCard
# ---------------------------------------------------------------------------


def test_atom_minimal_construction() -> None:
    atom = AtomCard(
        id="atom-1",
        entity_id="ent-1",
        candidate_id="cand-1",
        raw_event_ids=["raw-1"],
        assertion="先做 Augment 模式，不做 Replace",
        verbatim_quote="先做 Augment 模式，不做 Replace",
        quote_event_id="raw-1",
        search_terms=["harness", "augment", "replace"],
        occurred_at=_now(),
        confidence="high",
        importance="high",
        created_at=_now(),
    )

    assert atom.superseded_by is None
    assert atom.deprecated_at is None


def test_atom_supersession_chain() -> None:
    """When a fact is updated, a new atom is created and the old one points
    to it via ``superseded_by``. Recall filters out deprecated atoms.
    """
    old = AtomCard(
        id="atom-old",
        entity_id="ent-1",
        candidate_id="cand-old",
        raw_event_ids=["raw-1"],
        assertion="default backend = SQLite",
        verbatim_quote="default backend = SQLite",
        quote_event_id="raw-1",
        search_terms=["sqlite"],
        occurred_at=_now(),
        confidence="high",
        importance="high",
        created_at=_now(),
    )
    new_atom = AtomCard(
        id="atom-new",
        entity_id="ent-1",
        candidate_id="cand-new",
        raw_event_ids=["raw-2"],
        assertion="default backend = Postgres",
        verbatim_quote="default backend = Postgres",
        quote_event_id="raw-2",
        search_terms=["postgres"],
        occurred_at=_now(),
        confidence="high",
        importance="high",
        created_at=_now(),
    )
    # External code (promotion worker) sets these:
    old.superseded_by = new_atom.id
    old.deprecated_at = _now()
    assert old.superseded_by == new_atom.id
    assert old.deprecated_at is not None
    assert new_atom.superseded_by is None


# ---------------------------------------------------------------------------
# Entity (M2 minimal)
# ---------------------------------------------------------------------------


def test_entity_minimal_no_summary_fields() -> None:
    """M2 entity is minimal — no ``summary_markdown`` / ``summary_version``
    / ``last_user_edit_at``. Those come in M3 (D28).
    """
    ent = Entity(
        id="ent-1",
        entity_type="Project",
        canonical_name="Octop Memory",
        aliases=["octop memory", "LCM"],
        atom_count=0,
        created_at=_now(),
    )
    assert ent.last_promoted_at is None

    field_names = {f.name for f in fields(Entity)}
    # M3 will add these — assert they are NOT here so we notice migration.
    assert "summary_markdown" not in field_names
    assert "summary_version" not in field_names
    assert "last_user_edit_at" not in field_names


def test_entity_aliases_isolation() -> None:
    a = Entity(
        id="a",
        entity_type="Project",
        canonical_name="A",
        aliases=[],
        atom_count=0,
        created_at=_now(),
    )
    b = Entity(
        id="b",
        entity_type="Project",
        canonical_name="B",
        aliases=[],
        atom_count=0,
        created_at=_now(),
    )
    a.aliases.append("x")
    assert b.aliases == []


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------


def test_alias_construction() -> None:
    alias = Alias(
        alias="octop memory",
        entity_id="ent-1",
        entity_type="Project",
        created_by="rule",
        created_at=_now(),
    )
    assert alias.alias == "octop memory"
    assert alias.created_by == "rule"


# ---------------------------------------------------------------------------
# JournalEntry
# ---------------------------------------------------------------------------


def test_journal_minimal() -> None:
    j = JournalEntry(
        id="j-1",
        timestamp=_now(),
        action="promote",
        actor="auto",
    )
    assert j.target_entity_id is None
    assert j.target_atom_id is None
    assert j.target_candidate_id is None
    assert j.before is None
    assert j.after is None
    assert j.note == ""


def test_journal_diff_payload() -> None:
    before = {"assertion": "old"}
    after = {"assertion": "new"}
    j = JournalEntry(
        id="j-2",
        timestamp=_now(),
        action="update",
        actor="user",
        target_atom_id="atom-1",
        before=before,
        after=after,
        note="user edited via review CLI",
    )
    assert j.before == before
    assert j.after == after
    # Mutating original dicts should not poison the journal entry — but
    # JournalEntry holds a reference, so that's the caller's responsibility.
    # We just verify the field shape here.
    assert j.note == "user edited via review CLI"
