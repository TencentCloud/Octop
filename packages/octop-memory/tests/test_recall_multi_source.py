"""Tests for M2.9 multi-source recall (atom main + raw fallback)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.recall import RecallSnippet, recall_multi_source
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import AtomCard, Entity, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="rec", db_path=tmp_path / "rec.sqlite")
    return Memory(namespace="rec", backend=backend)


def _seed_raw(memory: Memory, content: str) -> RawEvent:
    """Insert a raw event and return it."""
    return memory.add_raw(content=content, event_type="user_message")


def _seed_entity(memory: Memory) -> Entity:
    ent = Entity(
        id=str(uuid.uuid4()),
        entity_type="Project",
        canonical_name="Project",
        aliases=[],
        atom_count=0,
        created_at=_now(),
    )
    memory.add_entity(ent)
    return ent


def _seed_atom(
    memory: Memory,
    *,
    entity_id: str,
    raw_event_id: str,
    assertion: str,
    importance: str = "high",
) -> AtomCard:
    atom = AtomCard(
        id=str(uuid.uuid4()),
        entity_id=entity_id,
        candidate_id="seeded",
        raw_event_ids=[raw_event_id],
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id=raw_event_id,
        search_terms=[],
        occurred_at=_now(),
        confidence="high",
        importance=importance,  # type: ignore[arg-type]
        created_at=_now(),
    )
    memory.add_atom(atom)
    return atom


# ---------------------------------------------------------------------------
# Default behaviour: atom-first, raw fallback
# ---------------------------------------------------------------------------


class TestDefaultMultiSource:
    def test_atom_layer_returned_when_atom_matches(self, memory: Memory) -> None:
        ev = _seed_raw(memory, "我们项目用 PostgreSQL 16")
        ent = _seed_entity(memory)
        _seed_atom(memory, entity_id=ent.id, raw_event_id=ev.id, assertion="项目用 PostgreSQL 16")

        result = recall_multi_source(memory, "PostgreSQL")

        assert len(result.snippets) == 1
        s = result.snippets[0]
        assert s.layer == "atom"
        assert s.role_hint.startswith("atom:")
        assert "[atom]" in result.rendered

    def test_raw_fallback_when_no_atom_matches(self, memory: Memory) -> None:
        # Raw exists, no atom — should still recall via raw fallback
        _seed_raw(memory, "Hermes adapter discussion only in raw")

        result = recall_multi_source(memory, "Hermes")
        assert len(result.snippets) == 1
        assert result.snippets[0].layer == "raw"
        assert "[raw]" in result.rendered

    def test_atom_suppresses_underlying_raw_event(self, memory: Memory) -> None:
        # Same content lives both as raw and as the atom that quotes it
        ev = _seed_raw(memory, "项目用 PostgreSQL 16 unique-keyword-zzy")
        ent = _seed_entity(memory)
        _seed_atom(
            memory,
            entity_id=ent.id,
            raw_event_id=ev.id,
            assertion="项目用 PostgreSQL 16 unique-keyword-zzy",
        )

        result = recall_multi_source(memory, "unique-keyword-zzy")

        # Should return ONLY the atom (raw is deduped because it underlies
        # the atom we just returned).
        layers = [s.layer for s in result.snippets]
        assert layers.count("atom") == 1
        assert layers.count("raw") == 0

    def test_atom_then_raw_when_distinct_matches(self, memory: Memory) -> None:
        # Atom matches one phrasing; a different raw matches another.
        ev1 = _seed_raw(memory, "alpha-token sentence 1")
        _seed_raw(memory, "alpha-token sentence 2")
        ent = _seed_entity(memory)
        _seed_atom(
            memory,
            entity_id=ent.id,
            raw_event_id=ev1.id,
            assertion="alpha-token sentence 1",
        )

        result = recall_multi_source(memory, "alpha-token")
        layers = [s.layer for s in result.snippets]
        assert "atom" in layers
        assert "raw" in layers


# ---------------------------------------------------------------------------
# Source override
# ---------------------------------------------------------------------------


class TestSourcesParameter:
    def test_sources_raw_only_keeps_m1_behaviour(self, memory: Memory) -> None:
        ev = _seed_raw(memory, "Hermes legacy raw match")
        ent = _seed_entity(memory)
        _seed_atom(
            memory,
            entity_id=ent.id,
            raw_event_id=ev.id,
            assertion="Hermes legacy raw match",
        )

        result = recall_multi_source(memory, "Hermes", sources=("raw",))
        assert all(s.layer == "raw" for s in result.snippets)
        assert result.snippets, "raw-only must still return the underlying raw event"

    def test_sources_atom_only_skips_raw_fallback(self, memory: Memory) -> None:
        _seed_raw(memory, "Hermes ONLY in raw")
        result = recall_multi_source(memory, "Hermes", sources=("atom",))
        # No atom exists; atom-only must NOT fall back to raw.
        assert result.snippets == []
        assert result.rendered == ""

    def test_unknown_source_raises(self, memory: Memory) -> None:
        with pytest.raises(ValueError, match="unknown source layer"):
            recall_multi_source(memory, "anything", sources=("graph",))  # type: ignore[arg-type]

    def test_empty_sources_returns_empty(self, memory: Memory) -> None:
        _seed_raw(memory, "anything Hermes")
        result = recall_multi_source(memory, "Hermes", sources=())
        assert result.snippets == []


# ---------------------------------------------------------------------------
# Limits + budget
# ---------------------------------------------------------------------------


class TestLimitsAndBudget:
    def test_limit_caps_total_across_layers(self, memory: Memory) -> None:
        ent = _seed_entity(memory)
        for i in range(3):
            ev = _seed_raw(memory, f"alpha hit {i}")
            _seed_atom(
                memory,
                entity_id=ent.id,
                raw_event_id=ev.id,
                assertion=f"alpha hit {i}",
            )
        for i in range(3):
            _seed_raw(memory, f"alpha extra {i}")

        result = recall_multi_source(memory, "alpha", limit=2)
        assert len(result.snippets) == 2

    def test_total_chars_stops_appending(self, memory: Memory) -> None:
        ev = _seed_raw(memory, "alpha-token long content " + "x" * 400)
        ent = _seed_entity(memory)
        _seed_atom(
            memory,
            entity_id=ent.id,
            raw_event_id=ev.id,
            assertion="alpha-token long content " + "y" * 400,
        )
        _seed_raw(memory, "alpha-token short raw")

        # Tight budget: only one atom snippet should fit
        result = recall_multi_source(
            memory,
            "alpha-token",
            per_snippet_chars=200,
            total_chars=200,
        )
        assert len(result.snippets) == 1


# ---------------------------------------------------------------------------
# Backward compat for the layer field
# ---------------------------------------------------------------------------


class TestLayerField:
    def test_default_construction_layer_is_raw(self) -> None:
        # Construct directly to confirm dataclass default — old callers
        # that didn't pass ``layer`` get backward-compat behaviour.
        s = RecallSnippet(
            source_id="x",
            timestamp_iso="2026-06-03T00:00:00+00:00",
            role_hint="user",
            text="hi",
        )
        assert s.layer == "raw"
