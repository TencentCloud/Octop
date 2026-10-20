"""End-to-end tests for ``recall_for_prompt`` (full pipeline)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.recall import recall_for_prompt
from octop_memory.pipeline.recall.cache import RecallCache
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Alias, AtomCard, Entity, RawEvent

_NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Memory, dict[str, str]]:
    backend = SqliteMemoryBackend(namespace="v2", db_path=tmp_path / "v2.sqlite")
    mem = Memory(namespace="v2", backend=backend)

    # Two entities with overlapping topics so we can test diversifier
    # + entity hint routing.
    hermes_id = "ent-hermes"
    openclaw_id = "ent-openclaw"
    for entity_id, name in [(hermes_id, "Hermes"), (openclaw_id, "OpenClaw")]:
        mem.add_entity(
            Entity(
                id=entity_id,
                entity_type="Project",
                canonical_name=name,
                aliases=[name.lower()],
                atom_count=0,
                created_at=_NOW,
            )
        )
        mem.add_alias(
            Alias(
                alias=name.lower(),
                entity_id=entity_id,
                entity_type="Project",
                created_by="test",
                created_at=_NOW,
            )
        )

    # 4 atoms about Hermes, 2 about OpenClaw — gives the diversifier
    # something to do (cap = 3).
    seed = [
        (hermes_id, "Hermes uses Postgres 16 as primary storage", "high"),
        (hermes_id, "Hermes deployment target is 2026-Q3", "medium"),
        (hermes_id, "Hermes backend is Python 3.13", "medium"),
        (hermes_id, "Hermes monitoring uses Prometheus", "low"),
        (openclaw_id, "OpenClaw plugin SDK is npm distributed", "high"),
        (openclaw_id, "OpenClaw default memory adapter is memory-core", "high"),
    ]
    for idx, (eid, text, importance) in enumerate(seed):
        when = _NOW - timedelta(days=idx)
        raw_id = str(uuid.uuid4())
        mem.add_raw_batch(
            [
                RawEvent(
                    id=raw_id,
                    host="t",
                    session_id="s",
                    thread_id=None,
                    user=None,
                    timestamp=when,
                    event_type="user_message",
                    content=text,
                    payload={},
                )
            ]
        )
        mem.add_atom(
            AtomCard(
                id=str(uuid.uuid4()),
                entity_id=eid,
                candidate_id=str(uuid.uuid4()),
                raw_event_ids=[raw_id],
                assertion=text,
                verbatim_quote=text,
                quote_event_id=raw_id,
                search_terms=["Hermes" if eid == hermes_id else "OpenClaw"],
                occurred_at=when,
                confidence="high",
                importance=importance,  # type: ignore[arg-type]
                created_at=when,
            )
        )

    return mem, {"hermes": hermes_id, "openclaw": openclaw_id}


class TestEmptyQuery:
    def test_empty_returns_empty(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        result = recall_for_prompt(mem, "", limit=5)
        assert result.snippets == []
        assert result.rendered == ""


class TestEntityHitRoute:
    def test_hermes_query_returns_hermes_atoms(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ids = seeded
        result = recall_for_prompt(mem, "Hermes 进度怎么样", limit=5, now=_NOW)
        assert result.snippets, "expected at least one Hermes atom"
        # All atom snippets should belong to Hermes (entity_anchor injected
        # via the resolved alias).
        atom_texts = [s.text for s in result.snippets if s.layer == "atom"]
        assert any("Hermes" in t for t in atom_texts)

    def test_query_mention_pushes_to_stack(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, ids = seeded
        recall_for_prompt(mem, "Hermes 进度", thread_id="thr-1", now=_NOW)
        rows = mem.list_active_entities("thr-1")
        assert any(r.entity_id == ids["hermes"] for r in rows)


class TestCorefRoute:
    def test_pronoun_resolves_via_stack(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, ids = seeded
        # Prime the stack so the coreference query resolves to Hermes.
        mem.upsert_active_entity("thr-c", ids["hermes"], source="manual", when=_NOW)
        result = recall_for_prompt(mem, "那个项目最近怎么样", thread_id="thr-c", limit=5, now=_NOW)
        assert result.snippets
        # Should be Hermes atoms.
        assert all("Hermes" in s.text or s.layer == "raw" for s in result.snippets)


class TestDiversifyAndBudget:
    def test_per_entity_cap_3(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        # A query that matches all atoms ("Hermes" returns 4) — the
        # diversifier should still cap at 3 per entity.
        result = recall_for_prompt(mem, "Hermes Postgres", limit=10, now=_NOW)
        # Find atoms by source_id; cross-check against AtomCard.entity_id
        hermes_count = 0
        for s in result.snippets:
            atom = mem.get_atom(s.source_id)
            if atom and atom.entity_id == "ent-hermes":
                hermes_count += 1
        assert hermes_count <= 3


class TestCacheIntegration:
    def test_second_call_hits_cache(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        cache = RecallCache(ttl_seconds=60.0)
        r1 = recall_for_prompt(mem, "Hermes 进度", thread_id="thr-x", cache=cache, limit=5, now=_NOW)
        # Second call should be served from cache (stats grow by 1 entry).
        r2 = recall_for_prompt(mem, "Hermes 进度", thread_id="thr-x", cache=cache, limit=5, now=_NOW)
        assert r1.rendered == r2.rendered
        assert cache.stats()["size"] == 1


class TestTimeBoundedRoute:
    def test_today_returns_recent(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        # All atoms are within the last 6 days, so the last-week window covers them.
        result = recall_for_prompt(mem, "上周聊过什么", limit=5, now=_NOW)
        # No assertion on exact content — we only verify the time-bounded
        # path runs without errors and returns something.
        assert result.snippets


class TestRecallDegrades:
    def test_closed_db_returns_empty_not_raise(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        mem.backend.close()  # type: ignore[union-attr]
        result = recall_for_prompt(mem, "Hermes 进度怎么样", limit=5, now=_NOW)
        assert result.snippets == []
        assert result.rendered == ""


def _add_raw(mem: Memory, *, content: str, event_id: str, session_id: str, thread_id: str | None) -> None:
    mem.add_raw_batch(
        [
            RawEvent(
                id=event_id,
                host="t",
                session_id=session_id,
                thread_id=thread_id,
                user=None,
                timestamp=_NOW,
                event_type="user_message",
                content=content,
                payload={},
            )
        ]
    )


class TestStrictInjectRaw:
    def test_does_not_top_up_with_raw_when_atoms_hit(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        _add_raw(
            mem,
            content="Hermes standup notes from an older chat about Postgres",
            event_id="raw-extra-hermes",
            session_id="older-session",
            thread_id="older-thread",
        )
        result = recall_for_prompt(mem, "Hermes Postgres", limit=10, now=_NOW)
        assert result.snippets
        assert all(s.layer == "atom" for s in result.snippets)
        assert "raw-extra-hermes" not in {s.source_id for s in result.snippets}

    def test_always_policy_keeps_raw_alongside_atoms(self, seeded: tuple[Memory, dict[str, str]]) -> None:
        mem, _ = seeded
        _add_raw(
            mem,
            content="Hermes standup notes from an older chat about Postgres",
            event_id="raw-extra-always",
            session_id="older-session",
            thread_id="older-thread",
        )
        result = recall_for_prompt(
            mem,
            "Hermes Postgres",
            limit=10,
            now=_NOW,
            raw_policy="always",
        )
        layers = {s.layer for s in result.snippets}
        assert "atom" in layers
        assert "raw" in layers

    def test_raw_fallback_uses_other_session_when_no_atoms(self, tmp_path: Path) -> None:
        backend = SqliteMemoryBackend(namespace="raw-only", db_path=tmp_path / "raw.sqlite")
        mem = Memory(namespace="raw-only", backend=backend)
        _add_raw(
            mem,
            content="User prefers darkmode theme in the editor",
            event_id="raw-older",
            session_id="s-old",
            thread_id="thr-old",
        )
        result = recall_for_prompt(mem, "darkmode theme", thread_id="thr-now", limit=5, now=_NOW)
        assert [s.source_id for s in result.snippets] == ["raw-older"]
        assert result.snippets[0].layer == "raw"

    def test_skips_raw_from_current_thread(self, tmp_path: Path) -> None:
        backend = SqliteMemoryBackend(namespace="raw-only", db_path=tmp_path / "raw.sqlite")
        mem = Memory(namespace="raw-only", backend=backend)
        _add_raw(
            mem,
            content="User prefers darkmode theme in the editor",
            event_id="raw-current",
            session_id="s-now",
            thread_id="thr-now",
        )
        result = recall_for_prompt(mem, "darkmode theme", thread_id="thr-now", limit=5, now=_NOW)
        assert result.snippets == []
        assert result.rendered == ""

    def test_skips_raw_when_session_id_matches_thread(self, tmp_path: Path) -> None:
        backend = SqliteMemoryBackend(namespace="raw-only", db_path=tmp_path / "raw.sqlite")
        mem = Memory(namespace="raw-only", backend=backend)
        _add_raw(
            mem,
            content="User prefers darkmode theme in the editor",
            event_id="raw-session",
            session_id="thr-now",
            thread_id=None,
        )
        result = recall_for_prompt(mem, "darkmode theme", thread_id="thr-now", limit=5, now=_NOW)
        assert result.snippets == []

    def test_skips_raw_from_same_session_other_thread(self, tmp_path: Path) -> None:
        backend = SqliteMemoryBackend(namespace="raw-only", db_path=tmp_path / "raw.sqlite")
        mem = Memory(namespace="raw-only", backend=backend)
        _add_raw(
            mem,
            content="User prefers darkmode theme in the editor",
            event_id="raw-sibling",
            session_id="sess-now",
            thread_id="thr-other",
        )
        result = recall_for_prompt(
            mem,
            "darkmode theme",
            thread_id="thr-now",
            session_id="sess-now",
            limit=5,
            now=_NOW,
        )
        assert result.snippets == []
        assert result.rendered == ""
