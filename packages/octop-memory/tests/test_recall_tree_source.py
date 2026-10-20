"""Tests: MemoryNode tree is an organizational view over AtomCard."""

from __future__ import annotations

from pathlib import Path

from octop_memory import Memory
from octop_memory.pipeline.recall import recall_for_prompt


def _make_memory(tmp_path: Path) -> Memory:
    # File-backed: recall gather runs FTS on a worker thread, and the
    # per-thread SQLite pool cannot see a private ``:memory:`` schema.
    return Memory("test", backend="sqlite", backend_config={"db_path": tmp_path / "tree.sqlite"})


# ---------------------------------------------------------------------------
# Manual leaves are recalled through their canonical AtomCard
# ---------------------------------------------------------------------------


class TestRecallAtomBackedTree:
    def test_recall_v2_includes_manual_leaf_once_as_atom(self, tmp_path: Path) -> None:
        mem = _make_memory(tmp_path)
        leaf = mem.store("user prefers darkmode theme", topic="preferences")
        result = recall_for_prompt(mem, "darkmode preference")
        texts = [s.text for s in result.snippets]
        layers = [s.layer for s in result.snippets]
        assert any("darkmode" in t for t in texts), f"expected atom in snippets: {texts}"
        assert layers == ["atom"]
        assert leaf.atom_id == result.snippets[0].source_id

    def test_recall_v2_skips_branch_nodes(self, tmp_path: Path) -> None:
        """Branch labels organize leaves but never become recall snippets."""
        mem = _make_memory(tmp_path)
        branch = mem.store("张伟", level="branch", topic="person")
        mem.store("张伟负责后端", level="leaf", parent_id=branch.id, topic="role")
        result = recall_for_prompt(mem, "张伟")
        source_ids = {s.source_id for s in result.snippets}
        # Branch should not appear; only its leaf may
        assert branch.id not in source_ids

    def test_recall_v2_never_emits_tree_layer(self, tmp_path: Path) -> None:
        mem = _make_memory(tmp_path)
        mem.store("项目上线了", topic="milestone")
        result = recall_for_prompt(mem, "昨天上线了什么")
        assert all(s.layer in ("atom", "raw") for s in result.snippets)
