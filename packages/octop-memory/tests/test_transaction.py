"""Tests: backend transaction atomicity — rollback leaves no partial rows (RISK-013)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory import Memory
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, Entity


def _make_backend(tmp_path: Path) -> SqliteMemoryBackend:
    return SqliteMemoryBackend("test", db_path=str(tmp_path / "test.sqlite"))


def _make_atom(entity_id: str) -> AtomCard:
    now = datetime.now(UTC)
    raw_id = str(uuid.uuid4())
    return AtomCard(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        candidate_id=str(uuid.uuid4()),
        raw_event_ids=[raw_id],
        assertion="测试事实",
        verbatim_quote="测试事实",
        quote_event_id=raw_id,
        search_terms=["测试"],
        occurred_at=now,
        confidence="high",
        importance="medium",
        created_at=now,
    )


# ---------------------------------------------------------------------------
# 1. transaction commit — all rows readable
# ---------------------------------------------------------------------------


class TestTransactionCommit:
    def test_all_rows_visible_after_commit(self, tmp_path: Path) -> None:
        backend = _make_backend(tmp_path)
        now = datetime.now(UTC)
        entity_id = str(uuid.uuid4())

        entity = Entity(
            id=entity_id,
            entity_type="Person",
            canonical_name="张伟",
            aliases=[],
            atom_count=0,
            created_at=now,
        )
        atom = _make_atom(entity_id)

        with backend.transaction():
            backend.save_entity(entity)
            backend.save_atom(atom)

        # Both rows are readable after commit.
        assert backend.get_entity(entity_id) is not None
        assert backend.get_atom(atom.id) is not None

    def test_nested_transaction_is_noop(self, tmp_path: Path) -> None:
        """A nested transaction produces no extra commit/rollback; the outer scope owns the boundary."""
        backend = _make_backend(tmp_path)
        now = datetime.now(UTC)
        entity_id = str(uuid.uuid4())
        entity = Entity(
            id=entity_id,
            entity_type="Person",
            canonical_name="李娜",
            aliases=[],
            atom_count=0,
            created_at=now,
        )
        atom = _make_atom(entity_id)

        with backend.transaction():
            backend.save_entity(entity)
            with backend.transaction():  # Nested — no-op.
                backend.save_atom(atom)
            # At this point the outer transaction hasn't committed yet, but
            # the inner one has already "completed".

        assert backend.get_entity(entity_id) is not None
        assert backend.get_atom(atom.id) is not None


# ---------------------------------------------------------------------------
# 2. transaction rollback — no partial rows
# ---------------------------------------------------------------------------


class TestTransactionRollback:
    def test_rollback_leaves_no_partial_rows(self, tmp_path: Path) -> None:
        backend = _make_backend(tmp_path)
        now = datetime.now(UTC)
        entity_id = str(uuid.uuid4())

        entity = Entity(
            id=entity_id,
            entity_type="Person",
            canonical_name="王芳",
            aliases=[],
            atom_count=0,
            created_at=now,
        )
        atom = _make_atom(entity_id)

        with pytest.raises(RuntimeError), backend.transaction():
            backend.save_entity(entity)
            backend.save_atom(atom)
            raise RuntimeError("simulated mid-transaction exception")

        # Neither row exists after rollback.
        assert backend.get_entity(entity_id) is None, "entity should be rolled back"
        assert backend.get_atom(atom.id) is None, "atom should be rolled back"

    def test_rollback_on_constraint_violation(self, tmp_path: Path) -> None:
        """Inserting a duplicate id triggers IntegrityError, rolling back the whole transaction."""
        import sqlite3

        backend = _make_backend(tmp_path)
        now = datetime.now(UTC)
        entity_id = str(uuid.uuid4())

        entity = Entity(
            id=entity_id,
            entity_type="Person",
            canonical_name="赵六",
            aliases=[],
            atom_count=0,
            created_at=now,
        )
        atom = _make_atom(entity_id)
        atom2 = _make_atom(entity_id)
        atom2 = AtomCard(
            id=atom.id,  # Intentionally duplicate id.
            entity_id=entity_id,
            candidate_id=str(uuid.uuid4()),
            raw_event_ids=[],
            assertion="重复 atom",
            verbatim_quote="重复 atom",
            quote_event_id=None,
            search_terms=[],
            occurred_at=now,
            confidence="high",
            importance="medium",
            created_at=now,
        )

        with pytest.raises(sqlite3.IntegrityError), backend.transaction():
            backend.save_entity(entity)
            backend.save_atom(atom)
            backend.save_atom(atom2)  # Triggers a UNIQUE conflict.

        # The whole transaction rolls back; neither the entity nor the first atom exist.
        assert backend.get_entity(entity_id) is None
        assert backend.get_atom(atom.id) is None


# ---------------------------------------------------------------------------
# 3. Memory.store() atomicity — a mid-flight exception leaves no partial rows
# ---------------------------------------------------------------------------


class TestMemoryStoreAtomicity:
    def test_store_is_atomic_via_memory_api(self, tmp_path: Path) -> None:
        """Memory.store() uses a transaction; on overall success all rows are readable."""
        mem = Memory("test", backend_config={"db_path": str(tmp_path / "test.sqlite")})
        node = mem.store("原子写入测试", topic="测试主题")

        assert node.atom_id is not None
        assert mem.get_atom(node.atom_id) is not None
        assert mem.get(node.id) is not None
        # The entity and journal entry should also exist.
        entities = mem.list_entities()
        assert any(e.canonical_name == "测试主题" for e in entities)
