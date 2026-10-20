"""Tests for M2 candidate / atom / entity / alias / journal persistence in SqliteMemoryBackend.

Schema-only behaviour (dataclass instantiation) is in ``test_candidate_schema.py``.
This module exercises the actual SQLite round-trip: insert → select → assert
fields, plus FTS, supersession, alias resolution, and journal append-only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import (
    Alias,
    AtomCard,
    Candidate,
    Entity,
    JournalEntry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _make_candidate(**overrides: object) -> Candidate:
    base = {
        "id": "cand-1",
        "raw_event_ids": ["raw-1"],
        "candidate_type": "Decision",
        "status": "pending",
        "title": "Octop Memory mode",
        "assertion": "先做 Augment 模式，不做 Replace",
        "verbatim_quote": "先做 Augment 模式，不做 Replace",
        "quote_event_id": "raw-1",
        "subject_name": "Octop Memory",
        "subject_entity_type": "Project",
        "target_entity_id": None,
        "confidence": "high",
        "importance": "high",
        "recommended_action": "promote",
        "promotion_reason": "explicit decision",
        "extractor_version": "v2.0",
        "created_at": _now(),
        "session_id": "sess-1",
    }
    base.update(overrides)
    return Candidate(**base)  # type: ignore[arg-type]


def _make_atom(**overrides: object) -> AtomCard:
    base = {
        "id": "atom-1",
        "entity_id": "ent-1",
        "candidate_id": "cand-1",
        "raw_event_ids": ["raw-1"],
        "assertion": "先做 Augment 模式，不做 Replace",
        "verbatim_quote": "先做 Augment 模式，不做 Replace",
        "quote_event_id": "raw-1",
        "search_terms": ["harness", "augment", "replace"],
        "occurred_at": _now(),
        "confidence": "high",
        "importance": "high",
        "created_at": _now(),
    }
    base.update(overrides)
    return AtomCard(**base)  # type: ignore[arg-type]


def _make_entity(**overrides: object) -> Entity:
    base = {
        "id": "ent-1",
        "entity_type": "Project",
        "canonical_name": "Octop Memory",
        "aliases": ["LCM"],
        "atom_count": 0,
        "created_at": _now(),
    }
    base.update(overrides)
    return Entity(**base)  # type: ignore[arg-type]


@pytest.fixture
def backend(tmp_path: Path) -> SqliteMemoryBackend:
    return SqliteMemoryBackend(namespace="test", db_path=tmp_path / "m2.sqlite")


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


class TestCandidates:
    def test_save_and_get_round_trip(self, backend: SqliteMemoryBackend) -> None:
        cand = _make_candidate()
        backend.save_candidate(cand)

        loaded = backend.get_candidate("cand-1")
        assert loaded is not None
        assert loaded.id == cand.id
        assert loaded.assertion == cand.assertion
        assert loaded.verbatim_quote == cand.verbatim_quote
        assert loaded.raw_event_ids == cand.raw_event_ids
        assert loaded.session_id == "sess-1"
        assert loaded.confidence == "high"
        assert loaded.importance == "high"
        assert loaded.decided_at is None
        assert loaded.payload == {}

    def test_get_missing_returns_none(self, backend: SqliteMemoryBackend) -> None:
        assert backend.get_candidate("nope") is None

    def test_duplicate_id_raises(self, backend: SqliteMemoryBackend) -> None:
        import sqlite3

        backend.save_candidate(_make_candidate())
        with pytest.raises(sqlite3.IntegrityError):
            backend.save_candidate(_make_candidate())

    def test_list_filter_by_status(self, backend: SqliteMemoryBackend) -> None:
        backend.save_candidate(_make_candidate(id="c1", status="pending"))
        backend.save_candidate(_make_candidate(id="c2", status="promoted"))
        backend.save_candidate(_make_candidate(id="c3", status="rejected"))

        pending = backend.list_candidates(status="pending")
        assert len(pending) == 1
        assert pending[0].id == "c1"

    def test_list_filter_by_session(self, backend: SqliteMemoryBackend) -> None:
        backend.save_candidate(_make_candidate(id="c1", session_id="s1"))
        backend.save_candidate(_make_candidate(id="c2", session_id="s2"))

        s1_only = backend.list_candidates(session_id="s1")
        assert {c.id for c in s1_only} == {"c1"}

    def test_list_filter_by_target_entity(self, backend: SqliteMemoryBackend) -> None:
        backend.save_candidate(_make_candidate(id="c1", target_entity_id="ent-A"))
        backend.save_candidate(_make_candidate(id="c2", target_entity_id="ent-B"))

        a_only = backend.list_candidates(target_entity_id="ent-A")
        assert [c.id for c in a_only] == ["c1"]

    def test_list_time_range(self, backend: SqliteMemoryBackend) -> None:
        old = _now() - timedelta(days=2)
        new = _now()
        backend.save_candidate(_make_candidate(id="c1", created_at=old))
        backend.save_candidate(_make_candidate(id="c2", created_at=new))

        cutoff = _now() - timedelta(days=1)
        recent = backend.list_candidates(after=cutoff)
        assert {c.id for c in recent} == {"c2"}

    def test_update_status_records_decision(self, backend: SqliteMemoryBackend) -> None:
        backend.save_candidate(_make_candidate())
        decided = _now()
        ok = backend.update_candidate_status(
            "cand-1",
            status="promoted",
            decided_by="auto",
            decided_at=decided,
            target_entity_id="ent-1",
            promotion_reason="passed all 5 checks",
        )
        assert ok is True

        loaded = backend.get_candidate("cand-1")
        assert loaded is not None
        assert loaded.status == "promoted"
        assert loaded.decided_by == "auto"
        assert loaded.decided_at is not None
        assert abs((loaded.decided_at - decided).total_seconds()) < 1e-3
        assert loaded.target_entity_id == "ent-1"
        assert loaded.promotion_reason == "passed all 5 checks"

    def test_update_missing_returns_false(self, backend: SqliteMemoryBackend) -> None:
        assert backend.update_candidate_status("nope", status="rejected") is False

    def test_search_finds_assertion_text(self, backend: SqliteMemoryBackend) -> None:
        backend.save_candidate(_make_candidate(id="c1", assertion="default backend uses SQLite"))
        backend.save_candidate(_make_candidate(id="c2", assertion="we use Postgres for prod"))

        hits = backend.search_candidates("SQLite")
        assert {c.id for c in hits} == {"c1"}

    def test_search_finds_verbatim_quote(self, backend: SqliteMemoryBackend) -> None:
        backend.save_candidate(
            _make_candidate(
                id="c1",
                assertion="paraphrased version",
                verbatim_quote="user said exact phrase: alpha-beta-gamma",
            )
        )
        hits = backend.search_candidates("alpha-beta-gamma")
        assert {c.id for c in hits} == {"c1"}

    def test_namespace_isolation(self, tmp_path: Path) -> None:
        ns_a = SqliteMemoryBackend(namespace="ns_a", db_path=tmp_path / "iso.sqlite")
        ns_b = SqliteMemoryBackend(namespace="ns_b", db_path=tmp_path / "iso.sqlite")
        ns_a.save_candidate(_make_candidate(id="cand-A"))
        assert ns_b.get_candidate("cand-A") is None
        assert ns_a.get_candidate("cand-A") is not None


# ---------------------------------------------------------------------------
# Atoms
# ---------------------------------------------------------------------------


class TestAtoms:
    def test_save_and_get_round_trip(self, backend: SqliteMemoryBackend) -> None:
        atom = _make_atom()
        backend.save_atom(atom)

        loaded = backend.get_atom("atom-1")
        assert loaded is not None
        assert loaded.assertion == atom.assertion
        assert loaded.search_terms == atom.search_terms
        assert loaded.superseded_by is None
        assert loaded.deprecated_at is None

    def test_list_filter_by_entity(self, backend: SqliteMemoryBackend) -> None:
        backend.save_atom(_make_atom(id="a1", entity_id="ent-X"))
        backend.save_atom(_make_atom(id="a2", entity_id="ent-Y"))
        only_x = backend.list_atoms(entity_id="ent-X")
        assert {a.id for a in only_x} == {"a1"}

    def test_list_filter_by_importance(self, backend: SqliteMemoryBackend) -> None:
        backend.save_atom(_make_atom(id="a-low", importance="low"))
        backend.save_atom(_make_atom(id="a-high", importance="high"))
        high = backend.list_atoms(importance="high")
        assert {a.id for a in high} == {"a-high"}

    def test_list_excludes_deprecated_by_default(self, backend: SqliteMemoryBackend) -> None:
        backend.save_atom(_make_atom(id="a1"))
        backend.save_atom(_make_atom(id="a2"))
        backend.supersede_atom("a1", new_atom_id="a2", deprecated_at=_now())

        active = backend.list_atoms()
        assert {a.id for a in active} == {"a2"}

        all_atoms = backend.list_atoms(include_deprecated=True)
        assert {a.id for a in all_atoms} == {"a1", "a2"}

    def test_supersede_records_chain(self, backend: SqliteMemoryBackend) -> None:
        backend.save_atom(_make_atom(id="old"))
        backend.save_atom(_make_atom(id="new"))
        when = _now()
        ok = backend.supersede_atom("old", new_atom_id="new", deprecated_at=when)
        assert ok is True

        old_loaded = backend.get_atom("old")
        assert old_loaded is not None
        assert old_loaded.superseded_by == "new"
        assert old_loaded.deprecated_at is not None

    def test_supersede_missing_returns_false(self, backend: SqliteMemoryBackend) -> None:
        assert backend.supersede_atom("nope", new_atom_id="x", deprecated_at=_now()) is False

    def test_search_finds_search_terms(self, backend: SqliteMemoryBackend) -> None:
        backend.save_atom(
            _make_atom(
                id="a1",
                assertion="some text",
                search_terms=["augment", "supplement", "harness"],
            )
        )
        hits = backend.search_atoms("supplement")
        assert {a.id for a in hits} == {"a1"}

    def test_search_excludes_deprecated_by_default(self, backend: SqliteMemoryBackend) -> None:
        backend.save_atom(_make_atom(id="a1", search_terms=["unique-term-zzz"]))
        backend.save_atom(_make_atom(id="a2", search_terms=["unique-term-zzz"]))
        backend.supersede_atom("a1", new_atom_id="a2", deprecated_at=_now())

        active_hits = backend.search_atoms("unique-term-zzz")
        assert {a.id for a in active_hits} == {"a2"}

        all_hits = backend.search_atoms("unique-term-zzz", include_deprecated=True)
        assert {a.id for a in all_hits} == {"a1", "a2"}


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class TestEntities:
    def test_save_and_get(self, backend: SqliteMemoryBackend) -> None:
        ent = _make_entity()
        backend.save_entity(ent)

        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.canonical_name == "Octop Memory"
        assert loaded.aliases == ["LCM"]
        assert loaded.atom_count == 0

    def test_find_by_name_case_insensitive(self, backend: SqliteMemoryBackend) -> None:
        backend.save_entity(_make_entity(canonical_name="Octop Memory"))
        # COLLATE NOCASE should match regardless of casing.
        hit = backend.find_entity_by_name("octop memory")
        assert hit is not None
        assert hit.id == "ent-1"

    def test_find_by_name_with_type_filter(self, backend: SqliteMemoryBackend) -> None:
        backend.save_entity(_make_entity(id="proj", entity_type="Project", canonical_name="Foo"))
        backend.save_entity(_make_entity(id="task", entity_type="Task", canonical_name="Foo"))

        proj = backend.find_entity_by_name("Foo", entity_type="Project")
        assert proj is not None
        assert proj.id == "proj"

    def test_bump_atom_count_with_timestamp(self, backend: SqliteMemoryBackend) -> None:
        backend.save_entity(_make_entity())
        when = _now()
        ok = backend.bump_entity_atom_count("ent-1", delta=1, last_promoted_at=when)
        assert ok is True

        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.atom_count == 1
        assert loaded.last_promoted_at is not None

    def test_bump_atom_count_negative(self, backend: SqliteMemoryBackend) -> None:
        backend.save_entity(_make_entity(atom_count=5))
        backend.bump_entity_atom_count("ent-1", delta=-2)
        loaded = backend.get_entity("ent-1")
        assert loaded is not None
        assert loaded.atom_count == 3


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------


class TestAliases:
    def test_save_and_resolve(self, backend: SqliteMemoryBackend) -> None:
        backend.save_entity(_make_entity())
        alias = Alias(
            alias="lcm",
            entity_id="ent-1",
            entity_type="Project",
            created_by="rule",
            created_at=_now(),
        )
        backend.save_alias(alias)

        ent = backend.find_entity_by_alias("lcm")
        assert ent is not None
        assert ent.id == "ent-1"

    def test_resolve_unknown_returns_none(self, backend: SqliteMemoryBackend) -> None:
        assert backend.find_entity_by_alias("nope") is None

    def test_duplicate_alias_is_no_op(self, backend: SqliteMemoryBackend) -> None:
        backend.save_entity(_make_entity())
        alias = Alias(
            alias="lcm",
            entity_id="ent-1",
            entity_type="Project",
            created_by="rule",
            created_at=_now(),
        )
        backend.save_alias(alias)
        # Saving the same alias again should not raise.
        backend.save_alias(alias)

        listed = backend.list_aliases(entity_id="ent-1")
        assert len(listed) == 1


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


class TestJournal:
    def test_append_and_list(self, backend: SqliteMemoryBackend) -> None:
        entry = JournalEntry(
            id="j1",
            timestamp=_now(),
            action="promote",
            actor="auto",
            target_atom_id="atom-1",
            target_candidate_id="cand-1",
            after={"id": "atom-1", "assertion": "x"},
            note="auto promotion",
        )
        backend.append_journal(entry)

        listed = backend.list_journal()
        assert len(listed) == 1
        assert listed[0].id == "j1"
        assert listed[0].action == "promote"
        assert listed[0].actor == "auto"
        assert listed[0].after == {"id": "atom-1", "assertion": "x"}
        assert listed[0].before is None

    def test_filter_by_action(self, backend: SqliteMemoryBackend) -> None:
        for i, action in enumerate(["promote", "reject", "promote"]):
            backend.append_journal(
                JournalEntry(
                    id=f"j{i}",
                    timestamp=_now(),
                    action=action,  # type: ignore[arg-type]
                    actor="auto",
                )
            )
        promotes = backend.list_journal(action="promote")
        assert len(promotes) == 2

    def test_filter_by_target_atom(self, backend: SqliteMemoryBackend) -> None:
        backend.append_journal(
            JournalEntry(id="j1", timestamp=_now(), action="promote", actor="auto", target_atom_id="atom-A")
        )
        backend.append_journal(
            JournalEntry(id="j2", timestamp=_now(), action="deprecate", actor="auto", target_atom_id="atom-B")
        )
        a = backend.list_journal(target_atom_id="atom-A")
        assert {j.id for j in a} == {"j1"}

    def test_diff_payload_round_trip(self, backend: SqliteMemoryBackend) -> None:
        before = {"assertion": "old text"}
        after = {"assertion": "new text"}
        backend.append_journal(
            JournalEntry(
                id="j1",
                timestamp=_now(),
                action="update",
                actor="user",
                target_atom_id="atom-1",
                before=before,
                after=after,
            )
        )
        listed = backend.list_journal()
        assert listed[0].before == before
        assert listed[0].after == after
