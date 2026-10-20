"""Tests for the recall router (M4.3) + cache + timeout."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.recall.cache import RecallCache
from octop_memory.pipeline.recall.parser import parse_query
from octop_memory.pipeline.recall.router import route
from octop_memory.pipeline.recall.timeout import (
    Stopwatch,
    TimeoutExceededError,
    with_deadline,
)
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Alias, Entity

_NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="rtr", db_path=tmp_path / "rtr.sqlite")
    return Memory(namespace="rtr", backend=backend)


@pytest.fixture
def memory_with_entity(memory: Memory) -> tuple[Memory, str]:
    eid = "ent-hermes-1"
    memory.add_entity(
        Entity(
            id=eid,
            entity_type="Project",
            canonical_name="Hermes",
            aliases=["hermes"],
            atom_count=0,
            created_at=_NOW,
        )
    )
    memory.add_alias(
        Alias(
            alias="hermes",
            entity_id=eid,
            entity_type="Project",
            created_by="test",
            created_at=_NOW,
        )
    )
    return memory, eid


class TestRouteEmpty:
    def test_empty_text(self, memory: Memory) -> None:
        decision = route(memory, parse_query("", now=_NOW))
        assert decision.sources == ()


class TestRouteEntityHint:
    def test_resolves_known_alias(self, memory_with_entity: tuple[Memory, str]) -> None:
        mem, eid = memory_with_entity
        parsed = parse_query("Hermes 怎么样", now=_NOW)
        decision = route(mem, parsed)
        assert eid in decision.resolved_entity_ids
        # page_headline is now included when entity anchors are resolved
        assert decision.sources == ("atom", "page_headline", "raw")

    def test_unknown_alias(self, memory: Memory) -> None:
        parsed = parse_query("Atlantis 怎么样", now=_NOW)
        decision = route(memory, parsed)
        assert decision.resolved_entity_ids == ()


class TestRouteCoreference:
    def test_pulls_from_active_stack(self, memory_with_entity: tuple[Memory, str]) -> None:
        mem, eid = memory_with_entity
        mem.upsert_active_entity("thr-1", eid, source="manual", when=_NOW)
        parsed = parse_query("那个项目最近怎么样", now=_NOW)
        decision = route(mem, parsed, thread_id="thr-1")
        assert decision.coref_resolved_entity_id == eid
        assert eid in decision.resolved_entity_ids

    def test_no_thread_id_no_coref(self, memory_with_entity: tuple[Memory, str]) -> None:
        mem, eid = memory_with_entity
        mem.upsert_active_entity("thr-1", eid, source="manual", when=_NOW)
        parsed = parse_query("那个项目最近怎么样", now=_NOW)
        decision = route(mem, parsed)  # no thread_id
        assert decision.coref_resolved_entity_id is None

    def test_explicit_hint_wins_over_coref(self, memory_with_entity: tuple[Memory, str]) -> None:
        mem, eid = memory_with_entity
        mem.upsert_active_entity("thr-1", "different-entity", source="manual", when=_NOW)
        # Both an explicit "Hermes" hint and a coreference marker are present;
        # we don't fall back to the stale stack entity.
        parsed = parse_query("那个 Hermes 怎么样", now=_NOW)
        decision = route(mem, parsed, thread_id="thr-1")
        assert decision.coref_resolved_entity_id is None  # explicit hint
        assert eid in decision.resolved_entity_ids


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestRecallCache:
    def test_get_miss(self) -> None:
        cache = RecallCache()
        assert cache.get(thread_id="t", query="q") is None

    def test_set_then_get(self) -> None:
        cache = RecallCache()
        from octop_memory.pipeline.recall import RecallResult, RecallSnippet

        result = RecallResult(
            snippets=[RecallSnippet(source_id="s1", timestamp_iso="t", role_hint="r", text="x")],
            rendered="hello",
        )
        cache.set(thread_id="t", query="q", value=result)
        got = cache.get(thread_id="t", query="q")
        assert got is not None
        assert got.rendered == "hello"

    def test_ttl_expiry(self) -> None:
        clock = [0.0]
        cache = RecallCache(ttl_seconds=10.0, _now_fn=lambda: clock[0])
        from octop_memory.pipeline.recall import RecallResult

        cache.set(thread_id="t", query="q", value=RecallResult(snippets=[], rendered="x"))
        clock[0] = 5.0
        assert cache.get(thread_id="t", query="q") is not None
        clock[0] = 11.0
        assert cache.get(thread_id="t", query="q") is None

    def test_eviction(self) -> None:
        cache = RecallCache(max_entries=2)
        from octop_memory.pipeline.recall import RecallResult

        cache.set(thread_id="t", query="a", value=RecallResult(snippets=[], rendered="A"))
        cache.set(thread_id="t", query="b", value=RecallResult(snippets=[], rendered="B"))
        cache.set(thread_id="t", query="c", value=RecallResult(snippets=[], rendered="C"))
        assert cache.stats()["size"] == 2


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


class TestWithDeadline:
    def test_returns_value_under_budget(self) -> None:
        out = with_deadline(lambda: 42, stage="x", budget_ms=200)
        assert out == 42

    def test_raises_on_overrun(self) -> None:
        def slow() -> int:
            time.sleep(0.1)
            return 1

        with pytest.raises(TimeoutExceededError) as exc_info:
            with_deadline(slow, stage="slow", budget_ms=10)
        assert exc_info.value.stage == "slow"

    def test_zero_budget_immediate_timeout(self) -> None:
        with pytest.raises(TimeoutExceededError):
            with_deadline(lambda: 1, stage="x", budget_ms=0)


class TestStopwatch:
    def test_remaining_decreases(self) -> None:
        sw = Stopwatch(total_budget_ms=100)
        time.sleep(0.02)
        assert sw.remaining_ms < 100
        assert not sw.expired

    def test_split_records_label(self) -> None:
        sw = Stopwatch(total_budget_ms=100)
        sw.split("first")
        assert "first" in sw.splits
