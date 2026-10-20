"""Tests for M0 Memory Tree behavior — covers the 15 acceptance points.

These tests exercise the public ``Memory`` API plus edge cases at the
tree validation layer:

1. ``MemoryNode.metadata`` defaults to empty dict
2. Old API ``Memory.store("x")`` still creates a leaf
3. ``Memory.store(level="root")`` creates a root
4. branch / leaf can attach to a parent
5. root with parent_id is rejected
6. parent that does not exist is rejected
7. metadata round-trips through save / load
8. SQLite legacy DB migration adds ``metadata`` column
9. ``get_node`` returns the node, or None when missing
10. leaf content is immutable; organizational topic / metadata remain mutable
11. delete leaf removes it from search/recall
12. delete branch with children without cascade is rejected
13. cascade delete removes the entire subtree
14. CLI ``store / get / update / delete / tree`` round-trip via runner
15. (covered by parametrized backend tests where applicable)

Postgres-backend coverage uses the same Memory API and runs only when
``TEST_POSTGRES_DSN`` is set; we don't repeat the full suite
here — that lives in ``tests/test_postgres.py``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})


# ---------------------------------------------------------------------------
# 1. metadata default is empty dict
# ---------------------------------------------------------------------------


def test_memory_node_metadata_defaults_to_empty_dict(memory: Memory) -> None:
    node = memory.store("hello")
    assert node.metadata == {}
    fetched = memory.get(node.id)
    assert fetched is not None
    assert fetched.metadata == {}


# ---------------------------------------------------------------------------
# 2. old API Memory.store("x") still creates a leaf
# ---------------------------------------------------------------------------


def test_legacy_store_signature_creates_leaf(memory: Memory) -> None:
    node = memory.store("legacy call")
    assert node.level == "leaf"
    assert node.parent_id is None


# ---------------------------------------------------------------------------
# 3. root creation
# ---------------------------------------------------------------------------


def test_store_root(memory: Memory) -> None:
    node = memory.store("Octop Memory", level="root")
    assert node.level == "root"
    assert node.parent_id is None


# ---------------------------------------------------------------------------
# 4. branch / leaf can attach to a parent
# ---------------------------------------------------------------------------


def test_branch_and_leaf_under_parent(memory: Memory) -> None:
    root = memory.store("Project", level="root")
    branch = memory.store("Hermes adapter", level="branch", parent_id=root.id)
    leaf = memory.store("uses enhancement mode", level="leaf", parent_id=branch.id)

    assert branch.parent_id == root.id
    assert leaf.parent_id == branch.id


# ---------------------------------------------------------------------------
# 5. root must not have parent_id
# ---------------------------------------------------------------------------


def test_root_with_parent_rejected(memory: Memory) -> None:
    other_root = memory.store("Other", level="root")
    with pytest.raises(ValueError, match="root nodes must not have a parent_id"):
        memory.store("Bad root", level="root", parent_id=other_root.id)


# ---------------------------------------------------------------------------
# 6. unknown parent rejected
# ---------------------------------------------------------------------------


def test_unknown_parent_rejected(memory: Memory) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        memory.store("orphan", level="leaf", parent_id="nonexistent-id")


def test_leaf_cannot_have_children(memory: Memory) -> None:
    leaf = memory.store("a leaf", level="leaf")
    with pytest.raises(ValueError, match="leaf nodes cannot have children"):
        memory.store("child", level="leaf", parent_id=leaf.id)


# ---------------------------------------------------------------------------
# 7. metadata round-trip
# ---------------------------------------------------------------------------


def test_metadata_round_trip(memory: Memory) -> None:
    md = {"confidence": "high", "entity_id": "ep_001", "tags": ["x", "y"]}
    node = memory.store("with metadata", metadata=md)
    fetched = memory.get(node.id)
    assert fetched is not None
    assert fetched.metadata == md


def test_metadata_isolated_from_input_dict(memory: Memory) -> None:
    """Mutating the caller's dict must not corrupt stored metadata."""
    md = {"confidence": "high"}
    node = memory.store("isolated", metadata=md)
    md["confidence"] = "low"  # mutate after store
    fetched = memory.get(node.id)
    assert fetched is not None
    assert fetched.metadata == {"confidence": "high"}


# ---------------------------------------------------------------------------
# 8. SQLite legacy DB migration
# ---------------------------------------------------------------------------


def test_sqlite_migrates_legacy_db_without_metadata_column(tmp_path: Path) -> None:
    """A pre-M0 database has no ``metadata`` column; opening it must migrate."""
    db_path = tmp_path / "legacy.sqlite"
    # Build a legacy schema by hand (the pre-M0 version).
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE test_memory_nodes (
            id TEXT PRIMARY KEY,
            parent_id TEXT,
            level TEXT NOT NULL,
            content TEXT NOT NULL,
            topic TEXT,
            conversation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO test_memory_nodes "
        "(id, parent_id, level, content, topic, conversation_id, created_at, updated_at) "
        "VALUES ('legacy-1', NULL, 'root', 'old node', NULL, NULL, "
        "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    # Now open via Memory — should auto-migrate and the legacy node should
    # be readable with metadata defaulting to {}.
    mem = Memory(namespace="test", backend_config={"db_path": str(db_path)})
    legacy = mem.get("legacy-1")
    assert legacy is not None
    assert legacy.content == "old node"
    assert legacy.metadata == {}


# ---------------------------------------------------------------------------
# 9. get_node returns node or None
# ---------------------------------------------------------------------------


def test_get_returns_none_for_missing_id(memory: Memory) -> None:
    assert memory.get("never-existed") is None


def test_get_returns_node(memory: Memory) -> None:
    node = memory.store("findable")
    fetched = memory.get(node.id)
    assert fetched is not None
    assert fetched.id == node.id
    assert fetched.content == "findable"
    assert fetched.atom_id == node.atom_id


def test_leaf_content_is_projected_from_atom(memory: Memory) -> None:
    node = memory.store("canonical atom text", topic="design")
    assert node.atom_id is not None
    atom = memory.get_atom(node.atom_id)
    assert atom is not None
    assert atom.assertion == "canonical atom text"

    row = memory.backend._conn.execute(  # type: ignore[attr-defined]
        "SELECT content, atom_id FROM test_memory_nodes WHERE id = ?",
        (node.id,),
    ).fetchone()
    assert row["content"] == ""
    assert row["atom_id"] == atom.id
    assert memory.get(node.id).content == atom.assertion  # type: ignore[union-attr]


def test_backend_rejects_leaf_without_atom(memory: Memory) -> None:
    from datetime import UTC, datetime

    from octop_memory.types import MemoryNode

    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="must reference an AtomCard"):
        memory.backend.save_node(
            MemoryNode(
                id="unlinked-leaf",
                parent_id=None,
                level="leaf",
                content="duplicate fact storage",
                topic=None,
                conversation_id=None,
                created_at=now,
                updated_at=now,
            )
        )


# ---------------------------------------------------------------------------
# 10. leaf content is canonical AtomCard data; organization stays mutable
# ---------------------------------------------------------------------------


def test_update_leaf_content_is_rejected(memory: Memory) -> None:
    node = memory.store("alpha original content", topic="t")
    with pytest.raises(ValueError, match="owned by AtomCard"):
        memory.update(node.id, content="alpha updated content")
    assert any(h.id == node.id for h in memory.recall("original"))


def test_update_topic_only_does_not_change_content(memory: Memory) -> None:
    node = memory.store("keep this content", topic="old")
    assert memory.update(node.id, topic="new")
    fetched = memory.get(node.id)
    assert fetched is not None
    assert fetched.content == "keep this content"
    assert fetched.topic == "new"


def test_update_metadata_replace_semantics(memory: Memory) -> None:
    node = memory.store("x", metadata={"a": 1, "b": 2})
    assert memory.update(node.id, metadata={"c": 3})
    fetched = memory.get(node.id)
    assert fetched is not None
    assert fetched.metadata == {"c": 3}  # full replace, not merge


def test_update_metadata_does_not_corrupt_fts(memory: Memory) -> None:
    """Updating only metadata should leave AtomCard FTS intact."""
    node = memory.store("searchable phrase", topic="foo")
    memory.update(node.id, metadata={"k": "v"})
    hits = memory.recall("searchable")
    assert any(h.id == node.id for h in hits)


def test_update_returns_false_for_missing(memory: Memory) -> None:
    assert memory.update("nope", content="x") is False


# ---------------------------------------------------------------------------
# 11. delete leaf — recall no longer hits
# ---------------------------------------------------------------------------


def test_delete_leaf_clears_recall(memory: Memory) -> None:
    node = memory.store("unique-marker-zzz", topic="t")
    assert node.atom_id is not None
    assert memory.recall("unique-marker-zzz")
    assert memory.delete(node.id)
    # FTS must not return ghosts after delete
    assert memory.recall("unique-marker-zzz") == []
    assert memory.get(node.id) is None
    atom = memory.get_atom(node.atom_id)
    assert atom is not None
    assert atom.deprecated_at is not None


# ---------------------------------------------------------------------------
# 12. deleting a branch with children w/o cascade is rejected
# ---------------------------------------------------------------------------


def test_delete_branch_with_children_without_cascade(memory: Memory) -> None:
    root = memory.store("p", level="root")
    branch = memory.store("b", level="branch", parent_id=root.id)
    memory.store("leaf1", level="leaf", parent_id=branch.id)
    with pytest.raises(ValueError, match="cascade=True"):
        memory.delete(branch.id)
    # Tree still intact
    assert memory.get(branch.id) is not None


# ---------------------------------------------------------------------------
# 13. cascade delete removes entire subtree
# ---------------------------------------------------------------------------


def test_cascade_delete_subtree(memory: Memory) -> None:
    root = memory.store("R", level="root")
    branch_a = memory.store("BA", level="branch", parent_id=root.id)
    branch_b = memory.store("BB", level="branch", parent_id=root.id)
    leaf_a1 = memory.store("LA1", level="leaf", parent_id=branch_a.id)
    leaf_a2 = memory.store("LA2", level="leaf", parent_id=branch_a.id)
    leaf_b1 = memory.store("LB1", level="leaf", parent_id=branch_b.id)

    assert memory.delete(branch_a.id, cascade=True)

    # branch_a + its leaves gone; the rest survive
    assert memory.get(branch_a.id) is None
    assert memory.get(leaf_a1.id) is None
    assert memory.get(leaf_a2.id) is None
    assert memory.get(root.id) is not None
    assert memory.get(branch_b.id) is not None
    assert memory.get(leaf_b1.id) is not None

    # FTS no leftovers from deleted subtree
    assert memory.recall("LA1") == []
    assert memory.recall("LA2") == []


def test_delete_returns_false_for_missing(memory: Memory) -> None:
    assert memory.delete("never-existed") is False


# ---------------------------------------------------------------------------
# Extra: save_node strict insert (no silent overwrite)
# ---------------------------------------------------------------------------


def test_strict_insert_rejects_duplicate_id(memory: Memory) -> None:
    from datetime import UTC, datetime

    from octop_memory.types import MemoryNode

    node = MemoryNode(
        id="fixed-id",
        parent_id=None,
        level="root",
        content="first",
        topic=None,
        conversation_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    memory.backend.save_node(node)
    with pytest.raises(sqlite3.IntegrityError):
        memory.backend.save_node(node)


# ---------------------------------------------------------------------------
# 14. CLI round-trip via runner
# ---------------------------------------------------------------------------


def _run(runner: CliRunner, db_path: str, *args: str) -> click.testing.Result:
    return runner.invoke(
        main,
        ["--db", db_path, "--namespace", "test", "--json", *args],
    )


class TestCLIRoundtrip:
    def test_store_get_update_delete_via_cli(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()

        # store root
        result = _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "ROOT",
            "--level",
            "root",
        )
        assert result.exit_code == 0, result.output
        root_id = json.loads(result.output)["data"]["id"]

        # store branch under root with metadata
        result = _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "BRANCH",
            "--level",
            "branch",
            "--parent",
            root_id,
            "--metadata",
            '{"confidence":"high"}',
        )
        assert result.exit_code == 0, result.output
        branch_id = json.loads(result.output)["data"]["id"]

        # store leaf
        result = _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "LEAF",
            "--level",
            "leaf",
            "--parent",
            branch_id,
        )
        assert result.exit_code == 0, result.output
        leaf_id = json.loads(result.output)["data"]["id"]

        # get
        result = _run(runner, db_path, "memory", "get", branch_id)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["level"] == "branch"
        assert data["metadata"] == {"confidence": "high"}

        # update metadata (replace)
        result = _run(
            runner,
            db_path,
            "memory",
            "update",
            branch_id,
            "--metadata",
            '{"status":"confirmed"}',
        )
        assert result.exit_code == 0, result.output
        result = _run(runner, db_path, "memory", "get", branch_id)
        data = json.loads(result.output)["data"]
        assert data["metadata"] == {"status": "confirmed"}

        # delete leaf (no children)
        result = _run(runner, db_path, "memory", "delete", leaf_id)
        assert result.exit_code == 0

        # delete branch w/o cascade -> ok now (no children left)
        result = _run(runner, db_path, "memory", "delete", branch_id)
        assert result.exit_code == 0

    def test_cli_metadata_must_be_object(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()
        # array is invalid
        result = _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "x",
            "--metadata",
            "[1,2,3]",
        )
        assert result.exit_code != 0
        assert "JSON object" in result.output

        # malformed json invalid
        result = _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "x",
            "--metadata",
            "not-json",
        )
        assert result.exit_code != 0

    def test_cli_delete_branch_with_children_without_cascade(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()

        result = _run(runner, db_path, "memory", "store", "--content", "R", "--level", "root")
        root_id = json.loads(result.output)["data"]["id"]
        result = _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "B",
            "--level",
            "branch",
            "--parent",
            root_id,
        )
        branch_id = json.loads(result.output)["data"]["id"]
        _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "L",
            "--level",
            "leaf",
            "--parent",
            branch_id,
        )

        # delete branch w/o cascade -> error
        result = _run(runner, db_path, "memory", "delete", branch_id)
        assert result.exit_code != 0

        # with --cascade -> ok
        result = _run(runner, db_path, "memory", "delete", branch_id, "--cascade")
        assert result.exit_code == 0

    def test_cli_tree_pretty_print_ascii(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()

        # build a small tree
        result = _run(runner, db_path, "memory", "store", "--content", "R", "--level", "root")
        root_id = json.loads(result.output)["data"]["id"]
        _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "B1",
            "--level",
            "branch",
            "--parent",
            root_id,
        )
        _run(
            runner,
            db_path,
            "memory",
            "store",
            "--content",
            "B2",
            "--level",
            "branch",
            "--parent",
            root_id,
        )

        # pretty print without --json
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", "test", "memory", "tree"],
        )
        assert result.exit_code == 0
        # ASCII connectors only — no unicode box drawing
        assert "├" not in result.output
        assert "└" not in result.output
        assert "R" in result.output
        assert "B1" in result.output
        assert "B2" in result.output
