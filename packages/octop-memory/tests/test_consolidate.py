"""Tests for intra-entity semantic dedup (Entity Consolidation)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle import run_consolidation
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, ConfidenceLevel, Entity, EntityType, ImportanceLevel


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="cons", db_path=tmp_path / "cons.sqlite")
    return Memory(namespace="cons", backend=backend)


def _entity(memory: Memory, *, entity_id: str, atom_count: int, entity_type: EntityType = "User") -> None:
    memory.add_entity(
        Entity(
            id=entity_id,
            entity_type=entity_type,
            canonical_name=entity_id,
            aliases=[],
            atom_count=atom_count,
            created_at=_now(),
        )
    )


def _atom(
    memory: Memory,
    *,
    atom_id: str,
    entity_id: str,
    assertion: str,
    importance: ImportanceLevel = "medium",
    confidence: ConfidenceLevel = "medium",
    occurred_at: datetime | None = None,
    created_at: datetime | None = None,
) -> None:
    when = occurred_at or _now()
    memory.add_atom(
        AtomCard(
            id=atom_id,
            entity_id=entity_id,
            candidate_id=f"c-{atom_id}",
            raw_event_ids=[],
            assertion=assertion,
            verbatim_quote=assertion,
            quote_event_id=f"r-{atom_id}",
            search_terms=[],
            occurred_at=when,
            confidence=confidence,
            importance=importance,
            created_at=created_at or when,
        )
    )


# A mock LLM escalation hook implementing only same_assertion.
class _MockHook:
    def __init__(self, *, same: bool | None) -> None:
        self._same = same
        self.calls = 0

    def same_assertion(self, *, candidate_assertion: str, existing_assertion: str) -> bool | None:
        self.calls += 1
        return self._same

    # Unused protocol methods.
    def resolve_entity_match(self, **_: object) -> str | None:
        return None

    def is_contradiction(self, **_: object) -> bool | None:
        return None


# ---------------------------------------------------------------------------
# 1. High-Jaccard near-duplicate (no LLM needed)
# ---------------------------------------------------------------------------


class TestNearDuplicate:
    def test_near_dup_deprecated_keeper_kept(self, memory: Memory) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a-keep", entity_id="e1", assertion="User prefers dark mode", importance="high")
        _atom(memory, atom_id="a-dup", entity_id="e1", assertion="user prefers dark mode", importance="low")

        stats = run_consolidation(memory)

        assert stats.duplicate_clusters_found == 1
        assert stats.atoms_deprecated == 1
        assert stats.llm_calls == 0

        # The low-importance one loses, points at the keeper.
        loser = memory.get_atom("a-dup")
        assert loser is not None
        assert loser.superseded_by == "a-keep"
        assert loser.deprecated_at is not None

        keeper = memory.get_atom("a-keep")
        assert keeper is not None
        assert keeper.deprecated_at is None

        # Page marked dirty for regen.
        dirty = memory.list_dirty_entity_pages(limit=10)
        assert any(p.entity_id == "e1" for p in dirty)

        # Journal recorded.
        rows = memory.list_journal(action="consolidate", limit=10)
        assert len(rows) == 1
        assert rows[0].target_atom_id == "a-dup"
        assert rows[0].actor == "rule"
        assert rows[0].after == {"superseded_by": "a-keep"}


# ---------------------------------------------------------------------------
# 2. Grey-zone paraphrase needs LLM
# ---------------------------------------------------------------------------


class TestSemanticDuplicate:
    def test_no_hook_keeps_both(self, memory: Memory) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a1", entity_id="e1", assertion="用户在工作中喜欢用 Python")
        _atom(memory, atom_id="a2", entity_id="e1", assertion="用户在工作中偏好用 Python")

        stats = run_consolidation(memory)  # no hook

        assert stats.atoms_deprecated == 0
        assert memory.get_atom("a2") is not None
        assert memory.get_atom("a2").deprecated_at is None  # type: ignore[union-attr]

    def test_hook_true_merges(self, memory: Memory) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a1", entity_id="e1", assertion="用户在工作中喜欢用 Python", importance="high")
        _atom(memory, atom_id="a2", entity_id="e1", assertion="用户在工作中偏好用 Python", importance="low")

        hook = _MockHook(same=True)
        stats = run_consolidation(memory, llm_hook=hook)

        assert hook.calls == 1
        assert stats.llm_calls == 1
        assert stats.atoms_deprecated == 1
        assert memory.get_atom("a2").superseded_by == "a1"  # type: ignore[union-attr]
        rows = memory.list_journal(action="consolidate", limit=10)
        assert rows[0].actor == "auto"

    def test_high_jaccard_cluster_is_rule_even_with_hook(self, memory: Memory) -> None:
        # A near-duplicate (Jaccard >= 0.85) never calls the LLM, so even
        # when a hook is supplied the merge must be attributed to "rule".
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a-keep", entity_id="e1", assertion="User prefers dark mode", importance="high")
        _atom(memory, atom_id="a-dup", entity_id="e1", assertion="user prefers dark mode", importance="low")

        hook = _MockHook(same=True)
        stats = run_consolidation(memory, llm_hook=hook)

        assert hook.calls == 0
        assert stats.llm_calls == 0
        rows = memory.list_journal(action="consolidate", limit=10)
        assert rows[0].actor == "rule"


# ---------------------------------------------------------------------------
# 3. Conservatism — hook unsure / negative does not merge
# ---------------------------------------------------------------------------


class TestConservative:
    @pytest.mark.parametrize("verdict", [None, False])
    def test_uncertain_or_no_keeps_both(self, memory: Memory, verdict: bool | None) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a1", entity_id="e1", assertion="用户在工作中喜欢用 Python")
        _atom(memory, atom_id="a2", entity_id="e1", assertion="用户在工作中偏好用 Python")

        hook = _MockHook(same=verdict)
        stats = run_consolidation(memory, llm_hook=hook)

        assert hook.calls == 1
        assert stats.atoms_deprecated == 0


# ---------------------------------------------------------------------------
# 4. Keeper selection
# ---------------------------------------------------------------------------


class TestKeeperSelection:
    def test_higher_importance_wins(self, memory: Memory) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a-low", entity_id="e1", assertion="user likes tea", importance="low")
        _atom(memory, atom_id="a-high", entity_id="e1", assertion="User likes tea", importance="high")

        run_consolidation(memory)

        assert memory.get_atom("a-low").superseded_by == "a-high"  # type: ignore[union-attr]
        assert memory.get_atom("a-high").deprecated_at is None  # type: ignore[union-attr]

    def test_newer_occurred_at_wins_when_importance_equal(self, memory: Memory) -> None:
        old = _now() - timedelta(days=10)
        new = _now()
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a-old", entity_id="e1", assertion="user likes tea", occurred_at=old)
        _atom(memory, atom_id="a-new", entity_id="e1", assertion="User likes tea", occurred_at=new)

        run_consolidation(memory)

        assert memory.get_atom("a-old").superseded_by == "a-new"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 5. Dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_does_not_mutate(self, memory: Memory) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a-keep", entity_id="e1", assertion="User prefers dark mode", importance="high")
        _atom(memory, atom_id="a-dup", entity_id="e1", assertion="user prefers dark mode", importance="low")

        stats = run_consolidation(memory, dry_run=True)

        assert stats.dry_run is True
        assert stats.atoms_deprecated == 1  # counter reflects would-be work
        # ...but nothing actually changed.
        assert memory.get_atom("a-dup").deprecated_at is None  # type: ignore[union-attr]
        assert memory.list_journal(action="consolidate", limit=10) == []
        assert memory.list_dirty_entity_pages(limit=10) == []


# ---------------------------------------------------------------------------
# 6. Budgets
# ---------------------------------------------------------------------------


class TestBudgets:
    def test_max_llm_calls_caps_confirmations(self, memory: Memory) -> None:
        # Two independent grey-zone pairs across two entities; budget=1
        # lets only the first pair reach the hook.
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a1", entity_id="e1", assertion="用户在工作中喜欢用 Python")
        _atom(memory, atom_id="a2", entity_id="e1", assertion="用户在工作中偏好用 Python")
        _entity(memory, entity_id="e2", atom_count=2)
        _atom(memory, atom_id="b1", entity_id="e2", assertion="用户在生活中喜欢用 Python")
        _atom(memory, atom_id="b2", entity_id="e2", assertion="用户在生活中偏好用 Python")

        hook = _MockHook(same=True)
        stats = run_consolidation(memory, llm_hook=hook, max_llm_calls=1)

        assert hook.calls == 1
        assert stats.llm_calls == 1
        assert stats.atoms_deprecated == 1

    def test_max_entities_caps_scan(self, memory: Memory) -> None:
        for i in range(3):
            eid = f"e{i}"
            _entity(memory, entity_id=eid, atom_count=2)
            _atom(memory, atom_id=f"{eid}-keep", entity_id=eid, assertion="User prefers dark mode", importance="high")
            _atom(memory, atom_id=f"{eid}-dup", entity_id=eid, assertion="user prefers dark mode", importance="low")

        stats = run_consolidation(memory, max_entities=1)
        assert stats.entities_scanned == 1
        assert stats.atoms_deprecated == 1


# ---------------------------------------------------------------------------
# 7. Cross-entity isolation
# ---------------------------------------------------------------------------


class TestCrossEntityIsolation:
    def test_same_assertion_different_entity_not_merged(self, memory: Memory) -> None:
        # Both entities are scanned (atom_count >= 2) and a1/a2 share the
        # same assertion — but they live in different entities, so the
        # per-entity scan never compares them.
        _entity(memory, entity_id="e1", atom_count=2)
        _entity(memory, entity_id="e2", atom_count=2)
        _atom(memory, atom_id="a1", entity_id="e1", assertion="User prefers dark mode")
        _atom(memory, atom_id="a1b", entity_id="e1", assertion="User drinks coffee")
        _atom(memory, atom_id="a2", entity_id="e2", assertion="user prefers dark mode")
        _atom(memory, atom_id="a2b", entity_id="e2", assertion="user reads books")

        stats = run_consolidation(memory)

        assert stats.atoms_deprecated == 0
        assert memory.get_atom("a1").deprecated_at is None  # type: ignore[union-attr]
        assert memory.get_atom("a2").deprecated_at is None  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 8. Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_pass_no_op(self, memory: Memory) -> None:
        _entity(memory, entity_id="e1", atom_count=2)
        _atom(memory, atom_id="a-keep", entity_id="e1", assertion="User prefers dark mode", importance="high")
        _atom(memory, atom_id="a-dup", entity_id="e1", assertion="user prefers dark mode", importance="low")

        first = run_consolidation(memory)
        assert first.atoms_deprecated == 1

        second = run_consolidation(memory)
        assert second.atoms_deprecated == 0
        assert second.duplicate_clusters_found == 0
