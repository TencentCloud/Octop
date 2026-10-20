"""Tests for thread active-entity stack (M4.2, D41a + D41b)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.recall.thread_state import (
    DEFAULT_KEEP,
    list_active_entities,
    push_query_mentions,
    push_recall_hits,
    top_active_entity,
)
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="ts", db_path=tmp_path / "ts.sqlite")
    return Memory(namespace="ts", backend=backend)


class TestPushAndTop:
    def test_push_recall_hit_then_top(self, memory: Memory) -> None:
        push_recall_hits(memory, "thr-1", entity_ids=["E1"])
        top = top_active_entity(memory, "thr-1")
        assert top is not None
        assert top.entity_id == "E1"
        assert top.source == "recall_hit"

    def test_push_query_mention(self, memory: Memory) -> None:
        push_query_mentions(memory, "thr-1", entity_ids=["E2"])
        top = top_active_entity(memory, "thr-1")
        assert top is not None
        assert top.source == "query_mention"

    def test_top_empty_thread(self, memory: Memory) -> None:
        assert top_active_entity(memory, "missing") is None


class TestStackOrder:
    def test_recently_pushed_at_top(self, memory: Memory) -> None:
        t0 = datetime(2026, 6, 1, tzinfo=UTC)
        push_recall_hits(memory, "thr", entity_ids=["A"], when=t0)
        push_recall_hits(memory, "thr", entity_ids=["B"], when=t0 + timedelta(seconds=10))
        push_recall_hits(memory, "thr", entity_ids=["C"], when=t0 + timedelta(seconds=20))
        rows = list_active_entities(memory, "thr")
        assert [r.entity_id for r in rows] == ["C", "B", "A"]

    def test_re_seeing_refreshes(self, memory: Memory) -> None:
        t0 = datetime(2026, 6, 1, tzinfo=UTC)
        push_recall_hits(memory, "thr", entity_ids=["A"], when=t0)
        push_recall_hits(memory, "thr", entity_ids=["B"], when=t0 + timedelta(seconds=10))
        # Re-push A — should jump back to top.
        push_recall_hits(memory, "thr", entity_ids=["A"], when=t0 + timedelta(seconds=20))
        rows = list_active_entities(memory, "thr")
        assert [r.entity_id for r in rows] == ["A", "B"]


class TestEviction:
    def test_keeps_only_n_newest(self, memory: Memory) -> None:
        t0 = datetime(2026, 6, 1, tzinfo=UTC)
        for i in range(DEFAULT_KEEP + 3):
            push_recall_hits(
                memory,
                "thr",
                entity_ids=[f"E{i}"],
                when=t0 + timedelta(seconds=i),
            )
        rows = list_active_entities(memory, "thr", limit=20)
        assert len(rows) == DEFAULT_KEEP


class TestDedupOnPush:
    def test_dup_within_call_pushes_once(self, memory: Memory) -> None:
        # Calling with [A, A, B] should only result in 2 distinct rows.
        pushed = push_recall_hits(memory, "thr", entity_ids=["A", "A", "B"])
        assert pushed == 2
        rows = list_active_entities(memory, "thr")
        assert {r.entity_id for r in rows} == {"A", "B"}


class TestThreadIsolation:
    def test_threads_dont_cross_pollute(self, memory: Memory) -> None:
        push_recall_hits(memory, "thr-1", entity_ids=["A"])
        push_recall_hits(memory, "thr-2", entity_ids=["B"])
        assert top_active_entity(memory, "thr-1").entity_id == "A"  # type: ignore[union-attr]
        assert top_active_entity(memory, "thr-2").entity_id == "B"  # type: ignore[union-attr]
