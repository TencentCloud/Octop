"""Tests for Memory.merge_entity and SqliteMemoryBackend.migrate_atoms_to_entity."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, Entity

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _make_entity(eid: str, name: str = "TestEntity", entity_type: str = "Person") -> Entity:
    return Entity(
        id=eid,
        entity_type=entity_type,  # type: ignore[arg-type]
        canonical_name=name,
        aliases=[],
        atom_count=0,
        created_at=_now(),
    )


def _make_atom(
    aid: str,
    entity_id: str,
    assertion: str = "用户喜欢喝咖啡",
    importance: str = "medium",
) -> AtomCard:
    return AtomCard(
        id=aid,
        entity_id=entity_id,
        candidate_id="c0",
        raw_event_ids=["raw-1"],
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id="raw-1",
        search_terms=[],
        occurred_at=_now(),
        confidence="high",
        importance=importance,  # type: ignore[arg-type]
        created_at=_now(),
    )


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="test_merge", db_path=tmp_path / "test.sqlite")
    return Memory(namespace="test_merge", backend=backend)


# ---------------------------------------------------------------------------
# migrate_atoms_to_entity — backend-layer tests
# ---------------------------------------------------------------------------


class TestMigrateAtomsToEntity:
    def test_normal_migration_moves_atoms(self, memory: Memory) -> None:
        """Normal migration: atoms under the source entity are moved to the target entity."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))
        memory.add_atom(_make_atom("a2", "src", "用户喜欢喝茶"))

        migrated = memory.backend.migrate_atoms_to_entity("src", "tgt")

        assert migrated == 2
        # After migration, atoms belong to the target entity.
        a1 = memory.get_atom("a1")
        a2 = memory.get_atom("a2")
        assert a1 is not None and a1.entity_id == "tgt"
        assert a2 is not None and a2.entity_id == "tgt"

    def test_duplicate_atom_deprecated_after_migration(self, memory: Memory) -> None:
        """After migration, an atom duplicating one under the target entity is
        deprecated, with superseded_by pointing at the keeper."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        # Target entity already has an atom with the same assertion.
        memory.add_atom(_make_atom("keeper", "tgt", "用户喜欢喝咖啡"))
        # Source entity has an atom with the same assertion (should be deprecated after migration).
        memory.add_atom(_make_atom("dup", "src", "用户喜欢喝咖啡"))
        # Source entity also has a non-duplicate atom (should migrate normally).
        memory.add_atom(_make_atom("unique", "src", "用户喜欢喝茶"))

        migrated = memory.backend.migrate_atoms_to_entity("src", "tgt")

        # Only "unique" is migrated; "dup" is deprecated.
        assert migrated == 1
        dup = memory.get_atom("dup")
        assert dup is not None
        assert dup.deprecated_at is not None
        assert dup.superseded_by == "keeper"
        unique = memory.get_atom("unique")
        assert unique is not None and unique.entity_id == "tgt"

    def test_empty_source_returns_zero(self, memory: Memory) -> None:
        """Returns 0 when the source entity has no atoms."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))

        migrated = memory.backend.migrate_atoms_to_entity("src", "tgt")
        assert migrated == 0

    def test_deprecated_atoms_not_migrated(self, memory: Memory) -> None:
        """Already-deprecated atoms under the source entity are not migrated."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))
        memory.deprecate_atom("a1")  # Mark as deprecated.

        migrated = memory.backend.migrate_atoms_to_entity("src", "tgt")
        assert migrated == 0
        # The deprecated atom's entity_id is unchanged.
        a1 = memory.get_atom("a1")
        assert a1 is not None and a1.entity_id == "src"


# ---------------------------------------------------------------------------
# merge_entity — Memory core-layer tests
# ---------------------------------------------------------------------------


class TestMergeEntity:
    def test_merge_entity_moves_atoms_and_updates_count(self, memory: Memory) -> None:
        """After merge_entity, atoms belong to the correct entity and atom_count is updated correctly."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.bump_entity_atom_count("src", delta=2)
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))
        memory.add_atom(_make_atom("a2", "src", "用户喜欢喝茶"))

        migrated = memory.merge_entity("src", "tgt")

        assert migrated == 2
        # Atoms now belong to the target.
        assert memory.get_atom("a1").entity_id == "tgt"  # type: ignore[union-attr]
        assert memory.get_atom("a2").entity_id == "tgt"  # type: ignore[union-attr]
        # Target's atom_count increases.
        tgt = memory.get_entity("tgt")
        assert tgt is not None and tgt.atom_count == 2
        # Source's atom_count drops to zero.
        src = memory.get_entity("src")
        assert src is not None and src.atom_count == 0

    def test_merge_entity_journal_recorded(self, memory: Memory) -> None:
        """After merge_entity, the journal has an action='entity_merge' record."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))

        memory.merge_entity("src", "tgt")

        entries = memory.list_journal(action="entity_merge", limit=10)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry.target_entity_id == "tgt"
        assert "src" in (entry.note or "")
        assert "tgt" in (entry.note or "")

    def test_merge_entity_duplicate_deprecated(self, memory: Memory) -> None:
        """After merge_entity, a migrated duplicate atom is deprecated with the correct superseded_by."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("keeper", "tgt", "用户喜欢喝咖啡"))
        memory.add_atom(_make_atom("dup", "src", "用户喜欢喝咖啡"))

        memory.merge_entity("src", "tgt")

        dup = memory.get_atom("dup")
        assert dup is not None
        assert dup.deprecated_at is not None
        assert dup.superseded_by == "keeper"

    def test_merge_entity_marks_target_page_dirty(self, memory: Memory) -> None:
        """After merge_entity, the target entity's EntityPage is marked dirty."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))

        memory.merge_entity("src", "tgt")

        page = memory.get_entity_page("tgt")
        # mark_entity_page_dirty upserts a stub row with dirty=True.
        assert page is not None
        assert page.dirty is True

    def test_merge_entity_no_atoms_still_journals(self, memory: Memory) -> None:
        """merge_entity should write a journal entry even when the source entity has no atoms."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))

        migrated = memory.merge_entity("src", "tgt")

        assert migrated == 0
        entries = memory.list_journal(action="entity_merge", limit=10)
        assert len(entries) >= 1


# ---------------------------------------------------------------------------
# Transaction atomicity tests
# ---------------------------------------------------------------------------


class TestMigrateAtomsTransactionality:
    def test_all_atoms_migrated_atomically(self, memory: Memory) -> None:
        """migrate_atoms_to_entity should migrate all atoms atomically.

        Verifies: after migration completes, the source entity has no
        non-deprecated atoms left, and all atoms have been migrated to
        the target entity (no partial state).
        """
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))
        memory.add_atom(_make_atom("a2", "src", "用户喜欢喝茶"))
        memory.add_atom(_make_atom("a3", "src", "用户喜欢听音乐"))

        migrated = memory.backend.migrate_atoms_to_entity("src", "tgt")

        assert migrated == 3
        # Verify atomicity: the source entity has no non-deprecated atoms left.
        src_atoms = memory.list_atoms(entity_id="src", include_deprecated=False)
        assert len(src_atoms) == 0, f"source entity still has {len(src_atoms)} atom(s) (partial state)"
        # All atoms are now under the target entity.
        tgt_atoms = memory.list_atoms(entity_id="tgt", include_deprecated=False)
        assert len(tgt_atoms) == 3

    def test_idempotent_second_call_no_op(self, memory: Memory) -> None:
        """A second call to migrate_atoms_to_entity should be a no-op (source has no atoms left)."""
        memory.add_entity(_make_entity("src", "Source"))
        memory.add_entity(_make_entity("tgt", "Target"))
        memory.add_atom(_make_atom("a1", "src", "用户喜欢喝咖啡"))

        first = memory.backend.migrate_atoms_to_entity("src", "tgt")
        second = memory.backend.migrate_atoms_to_entity("src", "tgt")

        assert first == 1
        assert second == 0  # Nothing left to migrate on the second call.
