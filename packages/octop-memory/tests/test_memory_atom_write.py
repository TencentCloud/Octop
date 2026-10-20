"""Manual create_atom / replace_atom — dashboard write path."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.types import AtomCard, Candidate, Entity

PG_DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://localhost/octop_memory_test")


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(params=["sqlite", "postgres"])
def memory(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Memory]:
    """Run the same public write assertions against both production backends."""
    if request.param == "sqlite":
        mem = Memory(namespace="atom-write", backend_config={"db_path": str(tmp_path / "write.sqlite")})
        try:
            yield mem
        finally:
            mem.backend.close()
        return

    request.getfixturevalue("postgres_dsn")
    namespace = f"atom_write_{uuid.uuid4().hex[:12]}"
    mem = Memory(namespace=namespace, backend="postgres", backend_config={"dsn": PG_DSN})
    try:
        yield mem
    finally:
        backend = mem.backend
        if not backend._closed:  # type: ignore[attr-defined]
            backend.purge_namespace()  # type: ignore[attr-defined]
        backend.close()


def _seed_entity(memory: Memory, entity_id: str = "ent-1", name: str = "User") -> Entity:
    entity = Entity(
        id=entity_id,
        entity_type="User",
        canonical_name=name,
        aliases=[name],
        atom_count=0,
        created_at=_now(),
    )
    memory.add_entity(entity)
    return entity


def _seed_atom(
    memory: Memory,
    *,
    atom_id: str = "a1",
    entity_id: str = "ent-1",
    assertion: str = "likes coffee",
) -> AtomCard:
    cand = Candidate(
        id=f"c-{atom_id}",
        raw_event_ids=[],
        candidate_type="Preference",
        status="promoted",
        title=assertion,
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id="",
        subject_name="User",
        subject_entity_type="User",
        target_entity_id=entity_id,
        confidence="high",
        importance="medium",
        recommended_action="promote",
        promotion_reason="seed",
        extractor_version="test",
        created_at=_now(),
        decided_at=_now(),
        decided_by="user",
    )
    memory.add_candidate(cand)
    atom = AtomCard(
        id=atom_id,
        entity_id=entity_id,
        candidate_id=cand.id,
        raw_event_ids=[],
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id="",
        search_terms=["coffee"],
        occurred_at=_now(),
        confidence="high",
        importance="medium",
        created_at=_now(),
    )
    memory.add_atom(atom)
    memory.bump_entity_atom_count(entity_id, delta=1)
    return atom


class TestCreateAtom:
    def test_creates_entity_and_atom(self, memory: Memory) -> None:
        atom, entity, created = memory.create_atom(
            "喜欢喝美式咖啡",
            entity_name="饮品偏好",
            entity_type="Fact",
            kind="Preference",
        )
        assert created is True
        assert entity.canonical_name == "饮品偏好"
        assert entity.atom_count == 1
        assert atom.assertion == "喜欢喝美式咖啡"
        assert atom.entity_id == entity.id
        assert atom.deprecated_at is None

        cand = memory.get_candidate(atom.candidate_id)
        assert cand is not None
        assert cand.candidate_type == "Preference"
        assert cand.decided_by == "user"

        leaf = memory.backend.get_node_by_atom_id(atom.id)
        assert leaf is not None
        assert leaf.level == "leaf"
        parent = memory.get(leaf.parent_id) if leaf.parent_id else None
        assert parent is not None
        assert parent.level == "branch"
        assert parent.metadata.get("entity_id") == entity.id

        journal = memory.list_journal(action="create")
        assert len(journal) == 1
        assert journal[0].target_atom_id == atom.id

    def test_attaches_to_existing_entity(self, memory: Memory) -> None:
        existing = _seed_entity(memory)
        atom, entity, created = memory.create_atom(
            "住在上海",
            entity_id=existing.id,
            kind="Fact",
        )
        assert created is False
        assert entity.id == existing.id
        assert atom.entity_id == existing.id
        refreshed = memory.get_entity(existing.id)
        assert refreshed is not None
        assert refreshed.atom_count == 1

    def test_user_singleton_reuses_existing(self, memory: Memory) -> None:
        _seed_entity(memory, entity_id="ent-user", name="User")
        atom, entity, created = memory.create_atom(
            "真名叫小陈",
            entity_name="小陈",
            entity_type="User",
        )
        assert created is False
        assert entity.id == "ent-user"
        assert atom.entity_id == "ent-user"

    def test_rejects_empty_assertion(self, memory: Memory) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            memory.create_atom("   ", entity_name="X")

    def test_rejects_missing_entity(self, memory: Memory) -> None:
        with pytest.raises(ValueError, match="entity_id or entity_name"):
            memory.create_atom("a fact")
        with pytest.raises(ValueError, match="not found"):
            memory.create_atom("a fact", entity_id="missing")

    def test_rejects_duplicate_assertion(self, memory: Memory) -> None:
        memory.create_atom("喜欢喝美式咖啡", entity_name="饮品")
        with pytest.raises(ValueError, match="duplicate"):
            memory.create_atom("喜欢喝美式咖啡", entity_name="饮品", entity_type="Fact")


class TestReplaceAtom:
    def test_supersedes_and_relinks_tree(self, memory: Memory) -> None:
        _seed_entity(memory)
        old = _seed_atom(memory)
        raw_before = memory.list_raw(limit=100)
        new = memory.replace_atom(old.id, assertion="喜欢喝拿铁")
        assert new is not None
        assert new.id != old.id
        assert new.assertion == "喜欢喝拿铁"
        assert new.verbatim_quote == old.verbatim_quote
        assert new.entity_id == old.entity_id
        assert new.candidate_id == old.candidate_id
        assert new.raw_event_ids == old.raw_event_ids
        assert memory.list_raw(limit=100) == raw_before

        loaded_old = memory.get_atom(old.id)
        assert loaded_old is not None
        assert loaded_old.deprecated_at is not None
        assert loaded_old.superseded_by == new.id

        assert memory.backend.get_node_by_atom_id(old.id) is None
        new_leaf = memory.backend.get_node_by_atom_id(new.id)
        assert new_leaf is not None

        entity = memory.get_entity("ent-1")
        assert entity is not None
        assert entity.atom_count == 1

        live = memory.list_atoms(entity_id="ent-1", include_deprecated=False)
        assert [a.id for a in live] == [new.id]

        journal = memory.list_journal(action="user_edit")
        assert len(journal) == 1
        assert journal[0].before == {"assertion": "likes coffee", "atom_id": old.id}
        assert journal[0].after == {"assertion": "喜欢喝拿铁", "atom_id": new.id}
        assert journal[0].target_candidate_id is None

    def test_idempotent_when_text_unchanged(self, memory: Memory) -> None:
        _seed_entity(memory)
        old = _seed_atom(memory)
        same = memory.replace_atom(old.id, assertion="likes coffee")
        assert same is not None
        assert same.id == old.id
        assert memory.list_journal(action="user_edit") == []

    def test_unknown_or_deprecated_returns_none(self, memory: Memory) -> None:
        assert memory.replace_atom("nope", assertion="x") is None
        _seed_entity(memory)
        old = _seed_atom(memory)
        memory.deprecate_atom(old.id)
        assert memory.replace_atom(old.id, assertion="new text") is None

    def test_rejects_duplicate_of_other_live_atom(self, memory: Memory) -> None:
        _seed_entity(memory)
        _seed_atom(memory, atom_id="a1", assertion="likes coffee")
        other = _seed_atom(memory, atom_id="a2", assertion="likes tea")
        with pytest.raises(ValueError, match="duplicate"):
            memory.replace_atom(other.id, assertion="likes coffee")

    def test_concurrent_replacement_rolls_back_successor(self, memory: Memory, monkeypatch: pytest.MonkeyPatch) -> None:
        _seed_entity(memory)
        old = _seed_atom(memory)
        monkeypatch.setattr(memory, "supersede_atom", lambda *args, **kwargs: False)

        with pytest.raises(ValueError, match="replaced concurrently"):
            memory.replace_atom(old.id, assertion="new text")

        atoms = memory.list_atoms(entity_id=old.entity_id, include_deprecated=True)
        assert [atom.id for atom in atoms] == [old.id]
        assert memory.list_journal(action="user_edit") == []

    def test_active_atom_can_only_choose_one_successor(self, memory: Memory) -> None:
        _seed_entity(memory)
        old = _seed_atom(memory)
        first = _seed_atom(memory, atom_id="a2", assertion="first successor")
        second = _seed_atom(memory, atom_id="a3", assertion="second successor")

        assert memory.supersede_atom(old.id, new_atom_id=first.id) is True
        assert memory.supersede_atom(old.id, new_atom_id=second.id) is False
        loaded = memory.get_atom(old.id)
        assert loaded is not None
        assert loaded.superseded_by == first.id
