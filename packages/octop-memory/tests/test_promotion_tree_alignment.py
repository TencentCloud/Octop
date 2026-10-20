"""Tests: full alignment between promotion and the MemoryNode tree (ADR-010 entity branch addendum).

Verification points:
1. Leaves produced by promotion are attached under the corresponding entity branch, not orphaned top-level nodes.
2. Multiple promotions of the same entity share a single branch node.
3. get_or_create_entity_branch is idempotent.
4. get_node_by_atom_id can locate a leaf directly via atom_id (O(1) lookup).
5. _create_entity creates the entity branch in the same step.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from octop_memory import Memory
from octop_memory.pipeline.promotion import PromotionWorker
from octop_memory.types import (
    Candidate,
    Entity,
)


def _make_memory() -> Memory:
    return Memory("test", backend="sqlite", backend_config={"db_path": ":memory:"})


def _seed_raw(mem: Memory, raw_id: str = "raw-1") -> str:
    """Write a raw event and return its id, for use by the candidate's evidence check."""
    from octop_memory.types import RawEvent

    raw = RawEvent(
        id=raw_id,
        host="test",
        session_id="s1",
        thread_id=None,
        user=None,
        timestamp=datetime.now(UTC),
        event_type="user_message",
        content="test event",
        payload={},
    )
    mem.backend.save_raw(raw)
    return raw_id


def _make_candidate(
    *,
    subject_name: str = "张伟",
    assertion: str = "张伟负责后端架构",
    entity_type: str = "Person",
    raw_event_ids: list[str] | None = None,
) -> Candidate:
    now = datetime.now(UTC)
    return Candidate(
        id=str(uuid.uuid4()),
        raw_event_ids=raw_event_ids if raw_event_ids is not None else ["raw-1"],
        candidate_type="Fact",
        status="pending",
        title=assertion[:80],
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id=(raw_event_ids[0] if raw_event_ids else "raw-1"),
        subject_name=subject_name,
        subject_entity_type=entity_type,
        target_entity_id=None,
        confidence="high",
        importance="high",
        recommended_action="promote",
        promotion_reason="test",
        extractor_version="test/v1",
        created_at=now,
        session_id="s1",
    )


# ---------------------------------------------------------------------------
# 1. promotion leaf attaches under the entity branch
# ---------------------------------------------------------------------------


class TestPromotionLeafUnderEntityBranch:
    def test_promoted_leaf_has_entity_branch_as_parent(self) -> None:
        mem = _make_memory()
        _seed_raw(mem)
        worker = PromotionWorker(mem)
        cand = _make_candidate(subject_name="张伟", assertion="张伟负责后端架构")
        result = worker.promote([cand])
        assert result.promoted == 1

        tree = mem.get_tree()
        leaves = [n for n in tree if n.level == "leaf"]
        branches = [n for n in tree if n.level == "branch"]

        assert len(leaves) == 1, f"expected 1 leaf, got {leaves}"
        assert len(branches) == 1, f"expected 1 branch, got {branches}"

        leaf = leaves[0]
        branch = branches[0]
        assert leaf.parent_id == branch.id, f"leaf.parent_id={leaf.parent_id!r} should equal branch.id={branch.id!r}"
        assert branch.metadata.get("entity_id") is not None

    def test_multiple_promotions_same_entity_share_one_branch(self) -> None:
        mem = _make_memory()
        _seed_raw(mem)
        worker = PromotionWorker(mem)
        cands = [
            _make_candidate(subject_name="张伟", assertion="张伟负责后端架构"),
            _make_candidate(subject_name="张伟", assertion="张伟擅长 Python"),
        ]
        result = worker.promote(cands)
        assert result.promoted == 2

        tree = mem.get_tree()
        branches = [n for n in tree if n.level == "branch"]
        leaves = [n for n in tree if n.level == "leaf"]

        # Only one branch for the same entity.
        assert len(branches) == 1, f"expected 1 branch for same entity, got {branches}"
        assert len(leaves) == 2

        branch_id = branches[0].id
        for leaf in leaves:
            assert leaf.parent_id == branch_id, f"leaf {leaf.id} parent_id={leaf.parent_id!r} != branch {branch_id!r}"

    def test_different_entities_get_separate_branches(self) -> None:
        mem = _make_memory()
        _seed_raw(mem)
        worker = PromotionWorker(mem)
        cands = [
            _make_candidate(subject_name="张伟", assertion="张伟负责后端"),
            _make_candidate(subject_name="李娜", assertion="李娜负责前端"),
        ]
        result = worker.promote(cands)
        assert result.promoted == 2

        tree = mem.get_tree()
        branches = [n for n in tree if n.level == "branch"]
        assert len(branches) == 2, f"expected 2 branches for 2 entities, got {branches}"

        entity_ids = {b.metadata.get("entity_id") for b in branches}
        assert len(entity_ids) == 2, "branches should reference different entity_ids"


# ---------------------------------------------------------------------------
# 2. get_or_create_entity_branch is idempotent
# ---------------------------------------------------------------------------


class TestGetOrCreateEntityBranch:
    def test_idempotent_returns_same_branch(self) -> None:
        mem = _make_memory()
        entity = Entity(
            id=str(uuid.uuid4()),
            entity_type="Person",
            canonical_name="测试实体",
            aliases=[],
            atom_count=0,
            created_at=datetime.now(UTC),
        )
        mem.add_entity(entity)

        branch1 = mem.get_or_create_entity_branch(entity.id)
        branch2 = mem.get_or_create_entity_branch(entity.id)
        assert branch1.id == branch2.id, "get_or_create_entity_branch should be idempotent"

    def test_branch_content_is_entity_canonical_name(self) -> None:
        mem = _make_memory()
        entity = Entity(
            id=str(uuid.uuid4()),
            entity_type="Person",
            canonical_name="王芳",
            aliases=[],
            atom_count=0,
            created_at=datetime.now(UTC),
        )
        mem.add_entity(entity)
        branch = mem.get_or_create_entity_branch(entity.id)
        assert branch.content == "王芳"
        assert branch.level == "branch"
        assert branch.metadata.get("entity_id") == entity.id


# ---------------------------------------------------------------------------
# 3. get_node_by_atom_id O(1) lookup
# ---------------------------------------------------------------------------


class TestGetNodeByAtomId:
    def test_returns_leaf_for_known_atom(self) -> None:
        mem = _make_memory()
        leaf = mem.store("测试事实内容", topic="test")
        assert leaf.atom_id is not None

        found = mem.backend.get_node_by_atom_id(leaf.atom_id)
        assert found is not None
        assert found.id == leaf.id
        assert found.atom_id == leaf.atom_id

    def test_returns_none_for_unknown_atom(self) -> None:
        mem = _make_memory()
        result = mem.backend.get_node_by_atom_id("nonexistent-atom-id")
        assert result is None

    def test_content_is_projected_from_atom(self) -> None:
        mem = _make_memory()
        leaf = mem.store("投影内容测试", topic="test")
        assert leaf.atom_id is not None

        found = mem.backend.get_node_by_atom_id(leaf.atom_id)
        assert found is not None
        assert found.content == "投影内容测试"


# ---------------------------------------------------------------------------
# 4. _create_entity creates the entity branch in the same step
# ---------------------------------------------------------------------------


class TestCreateEntityCreatesEntityBranch:
    def test_promotion_creates_branch_for_new_entity(self) -> None:
        mem = _make_memory()
        _seed_raw(mem)
        worker = PromotionWorker(mem)
        cand = _make_candidate(subject_name="新实体名称", assertion="新实体的第一条事实")
        result = worker.promote([cand])
        assert result.promoted == 1

        tree = mem.get_tree()
        branches = [n for n in tree if n.level == "branch"]
        assert len(branches) == 1
        assert branches[0].content == "新实体名称"
