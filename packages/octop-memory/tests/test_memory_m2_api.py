"""Tests for ``Memory`` public API additions in M2.

Exercises the thin delegation layer: each ``Memory.add_xxx`` /
``Memory.list_xxx`` / etc. method must round-trip data through the SQLite
backend correctly. Because the backend layer already has dedicated tests
(``test_candidate_backend.py``), these tests focus on:

- public API method existence / signature compatibility
- the few methods that add value beyond pure delegation (e.g.
  ``supersede_atom`` defaulting ``deprecated_at`` to ``now``)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import (
    Alias,
    AtomCard,
    Candidate,
    Entity,
    JournalEntry,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _make_candidate(cid: str = "c1", **overrides: object) -> Candidate:
    base: dict[str, object] = {
        "id": cid,
        "raw_event_ids": ["raw-1"],
        "candidate_type": "Decision",
        "status": "pending",
        "title": "t",
        "assertion": "a",
        "verbatim_quote": "a",
        "quote_event_id": "raw-1",
        "subject_name": "s",
        "subject_entity_type": "Project",
        "target_entity_id": None,
        "confidence": "high",
        "importance": "high",
        "recommended_action": "promote",
        "promotion_reason": "",
        "extractor_version": "v2.0",
        "created_at": _now(),
    }
    base.update(overrides)
    return Candidate(**base)  # type: ignore[arg-type]


def _make_atom(aid: str = "a1", entity_id: str = "e1", **overrides: object) -> AtomCard:
    base: dict[str, object] = {
        "id": aid,
        "entity_id": entity_id,
        "candidate_id": "c1",
        "raw_event_ids": ["raw-1"],
        "assertion": "x",
        "verbatim_quote": "x",
        "quote_event_id": "raw-1",
        "search_terms": ["x"],
        "occurred_at": _now(),
        "confidence": "high",
        "importance": "high",
        "created_at": _now(),
    }
    base.update(overrides)
    return AtomCard(**base)  # type: ignore[arg-type]


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="m2", db_path=tmp_path / "m2_api.sqlite")
    return Memory(namespace="m2", backend=backend)


class TestCandidatePublicAPI:
    def test_round_trip_single(self, memory: Memory) -> None:
        cand = _make_candidate()
        memory.add_candidate(cand)
        loaded = memory.get_candidate("c1")
        assert loaded is not None
        assert loaded.id == "c1"

    def test_add_candidates_batch(self, memory: Memory) -> None:
        memory.add_candidates([_make_candidate("c1"), _make_candidate("c2")])
        assert {c.id for c in memory.list_candidates()} == {"c1", "c2"}

    def test_list_filters_status(self, memory: Memory) -> None:
        memory.add_candidate(_make_candidate("c1", status="pending"))
        memory.add_candidate(_make_candidate("c2", status="promoted"))
        assert {c.id for c in memory.list_candidates(status="pending")} == {"c1"}

    def test_list_filters_session(self, memory: Memory) -> None:
        memory.add_candidate(_make_candidate("c1", session_id="s1"))
        memory.add_candidate(_make_candidate("c2", session_id="s2"))
        assert {c.id for c in memory.list_candidates(session_id="s1")} == {"c1"}

    def test_update_status_with_decision_metadata(self, memory: Memory) -> None:
        memory.add_candidate(_make_candidate())
        decided = _now()
        ok = memory.update_candidate_status(
            "c1",
            status="promoted",
            decided_by="auto",
            decided_at=decided,
            target_entity_id="ent-1",
            promotion_reason="passed",
        )
        assert ok is True
        loaded = memory.get_candidate("c1")
        assert loaded is not None
        assert loaded.status == "promoted"
        assert loaded.target_entity_id == "ent-1"

    def test_search_finds_assertion(self, memory: Memory) -> None:
        memory.add_candidate(_make_candidate("c1", title="alpha", assertion="beta-token"))
        memory.add_candidate(_make_candidate("c2", title="x", assertion="other"))
        hits = memory.search_candidates("beta-token")
        assert {c.id for c in hits} == {"c1"}


class TestAtomPublicAPI:
    def test_round_trip_and_list(self, memory: Memory) -> None:
        memory.add_atom(_make_atom("a1"))
        memory.add_atom(_make_atom("a2"))
        assert {a.id for a in memory.list_atoms()} == {"a1", "a2"}

    def test_supersede_default_deprecated_at_is_now(self, memory: Memory) -> None:
        memory.add_atom(_make_atom("old"))
        memory.add_atom(_make_atom("new"))

        before = _now()
        ok = memory.supersede_atom("old", new_atom_id="new")  # no deprecated_at
        after = _now()
        assert ok is True

        loaded = memory.get_atom("old")
        assert loaded is not None
        assert loaded.deprecated_at is not None
        assert before - timedelta(seconds=1) <= loaded.deprecated_at <= after + timedelta(seconds=1)

    def test_search_excludes_deprecated_by_default(self, memory: Memory) -> None:
        memory.add_atom(_make_atom("a1", search_terms=["zztest-marker"]))
        memory.add_atom(_make_atom("a2", search_terms=["zztest-marker"]))
        memory.supersede_atom("a1", new_atom_id="a2")
        active = memory.search_atoms("zztest-marker")
        assert {a.id for a in active} == {"a2"}


class TestEntityAndAliasPublicAPI:
    def test_entity_lookup_by_name_and_alias(self, memory: Memory) -> None:
        ent = Entity(
            id="e1",
            entity_type="Project",
            canonical_name="Octop Memory",
            aliases=["LCM"],
            atom_count=0,
            created_at=_now(),
        )
        memory.add_entity(ent)
        memory.add_alias(
            Alias(
                alias="lcm",
                entity_id="e1",
                entity_type="Project",
                created_by="rule",
                created_at=_now(),
            )
        )

        by_name = memory.find_entity_by_name("octop memory")
        assert by_name is not None
        assert by_name.id == "e1"

        by_alias = memory.find_entity_by_alias("lcm")
        assert by_alias is not None
        assert by_alias.id == "e1"

    def test_bump_atom_count(self, memory: Memory) -> None:
        memory.add_entity(
            Entity(
                id="e1",
                entity_type="Project",
                canonical_name="X",
                aliases=[],
                atom_count=0,
                created_at=_now(),
            )
        )
        when = _now()
        memory.bump_entity_atom_count("e1", delta=3, last_promoted_at=when)
        loaded = memory.get_entity("e1")
        assert loaded is not None
        assert loaded.atom_count == 3
        assert loaded.last_promoted_at is not None


class TestJournalPublicAPI:
    def test_append_and_filter(self, memory: Memory) -> None:
        memory.append_journal(
            JournalEntry(id="j1", timestamp=_now(), action="promote", actor="auto", target_atom_id="a1")
        )
        memory.append_journal(
            JournalEntry(id="j2", timestamp=_now(), action="reject", actor="user", target_candidate_id="c1")
        )
        promotes = memory.list_journal(action="promote")
        assert {j.id for j in promotes} == {"j1"}
