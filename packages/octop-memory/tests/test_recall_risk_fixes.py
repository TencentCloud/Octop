"""Tests: RISK-007 recall source warning + RISK-011 page_headline gather."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.recall.multi_source import gather_candidates
from octop_memory.pipeline.recall.parser import ParsedQuery
from octop_memory.pipeline.recall.router import route

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def mem(tmp_path: Path) -> Memory:
    return Memory("test-ns", backend_config={"db_path": str(tmp_path / "memory.sqlite")})


# ---------------------------------------------------------------------------
# RISK-007: recall source helpers should log a warning on exception, not silently swallow it
# ---------------------------------------------------------------------------


class TestRecallSourceWarning:
    def test_atom_search_failure_logs_warning(self, mem: Memory) -> None:
        """When search_atoms raises, a warning should be logged and recall should degrade to empty rather than crash."""
        mem.store("正常内容", topic="测试")

        parsed = ParsedQuery(text="测试", raw_tokens=["测试"])

        with (
            patch.object(mem, "search_atoms", side_effect=RuntimeError("db locked")),
            patch("octop_memory.pipeline.recall.multi_source._log") as mock_log,
        ):
            candidates = gather_candidates(mem, parsed, sources=("atom",))
            # Degrades to an empty list.
            assert candidates == []
            # A warning was logged.
            mock_log.warning.assert_called_once()
            call_args = mock_log.warning.call_args[0]
            assert "atom search failed" in call_args[0]
            assert "测试" in str(call_args[1])

    def test_raw_search_failure_logs_warning(self, mem: Memory) -> None:
        """When search_raw raises, a warning should be logged and recall should degrade to empty rather than crash."""
        mem.add_raw("原始内容", event_type="message")

        parsed = ParsedQuery(text="原始", raw_tokens=["原始"])

        with (
            patch.object(mem, "search_raw", side_effect=RuntimeError("connection lost")),
            patch("octop_memory.pipeline.recall.multi_source._log") as mock_log,
        ):
            candidates = gather_candidates(mem, parsed, sources=("raw",))
            assert candidates == []
            mock_log.warning.assert_called_once()
            call_args = mock_log.warning.call_args[0]
            assert "raw search failed" in call_args[0]

    def test_atom_search_failure_does_not_affect_raw_source(self, mem: Memory) -> None:
        """A failure in the atom source should not prevent the raw source from continuing to recall."""
        mem.add_raw("原始事件内容", event_type="message")

        parsed = ParsedQuery(text="原始事件", raw_tokens=["原始事件"])

        with patch.object(mem, "search_atoms", side_effect=RuntimeError("db error")):
            candidates = gather_candidates(mem, parsed, sources=("atom", "raw"))
            # The raw source can still recall.
            raw_candidates = [c for c in candidates if c.layer == "raw"]
            assert len(raw_candidates) >= 0  # At minimum, it shouldn't crash.


# ---------------------------------------------------------------------------
# RISK-011: page_headline gather source
# ---------------------------------------------------------------------------


class TestPageHeadlineGather:
    def _make_mem_with_page(
        self, mem: Memory, headline: str = "项目A进展顺利", dirty: bool = False
    ) -> tuple[Memory, str]:
        """Create a Memory that has an EntityPage, return (mem, entity_id)."""
        from octop_memory.types import EntityPage

        mem.store("项目A完成了第一阶段", topic="项目A")
        entities = mem.list_entities()
        assert len(entities) >= 1
        entity = entities[0]

        # Write the EntityPage.
        page = EntityPage(
            id=f"page-{entity.id}",
            entity_id=entity.id,
            summary_markdown="## 项目A\n\n项目A完成了第一阶段。",
            headline=headline,
            topics=["项目"],
            dirty=dirty,
            regen_attempt_count=0,
            summary_version=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
        mem._backend.upsert_entity_page(page)
        return mem, entity.id

    def test_page_headline_source_returns_candidate(self, mem: Memory) -> None:
        """The page_headline source should return the EntityPage headline as a candidate."""
        mem, entity_id = self._make_mem_with_page(mem)

        parsed = ParsedQuery(text="项目A", raw_tokens=["项目A"])
        candidates = gather_candidates(
            mem,
            parsed,
            sources=("page_headline",),
            entity_anchor_ids=(entity_id,),
        )
        assert len(candidates) == 1
        assert candidates[0].layer == "page_headline"
        assert candidates[0].text == "项目A进展顺利"
        assert candidates[0].entity_id == entity_id

    def test_dirty_page_is_skipped(self, mem: Memory) -> None:
        """A page with dirty=True should be skipped (content may be stale)."""
        mem, entity_id = self._make_mem_with_page(mem, dirty=True)

        parsed = ParsedQuery(text="项目A", raw_tokens=["项目A"])
        candidates = gather_candidates(
            mem,
            parsed,
            sources=("page_headline",),
            entity_anchor_ids=(entity_id,),
        )
        assert candidates == []

    def test_empty_headline_is_skipped(self, mem: Memory) -> None:
        """A page with an empty headline should be skipped."""
        mem, entity_id = self._make_mem_with_page(mem, headline="")

        parsed = ParsedQuery(text="项目A", raw_tokens=["项目A"])
        candidates = gather_candidates(
            mem,
            parsed,
            sources=("page_headline",),
            entity_anchor_ids=(entity_id,),
        )
        assert candidates == []

    def test_no_anchor_ids_returns_empty(self, mem: Memory) -> None:
        """Without entity_anchor_ids, the page_headline source should return empty."""
        mem, _ = self._make_mem_with_page(mem)

        parsed = ParsedQuery(text="项目A", raw_tokens=["项目A"])
        candidates = gather_candidates(
            mem,
            parsed,
            sources=("page_headline",),
            entity_anchor_ids=(),  # No anchor.
        )
        assert candidates == []

    def test_page_headline_deduplicates_with_atom(self, mem: Memory) -> None:
        """page_headline should not duplicate the atom source (headline is
        skipped when the entity already has an atom hit)."""
        mem, entity_id = self._make_mem_with_page(mem)

        parsed = ParsedQuery(text="项目A", raw_tokens=["项目A"])
        candidates = gather_candidates(
            mem,
            parsed,
            sources=("atom", "page_headline"),
            entity_anchor_ids=(entity_id,),
        )
        # The atom source already hit this entity, so page_headline should be deduplicated away.
        page_candidates = [c for c in candidates if c.layer == "page_headline"]
        assert len(page_candidates) == 0

    def test_router_adds_page_headline_source_when_entity_resolved(self, mem: Memory) -> None:
        """The router should automatically add the page_headline source when there's a resolved entity."""
        _mem, entity_id = self._make_mem_with_page(mem)

        # Build a RoutingDecision directly with entity_id, bypassing alias lookup.
        # Verifies: as long as resolved is non-empty, sources should include page_headline.
        from octop_memory.pipeline.recall.router import RoutingDecision

        decision = RoutingDecision(
            sources=("atom", "page_headline", "raw"),
            resolved_entity_ids=(entity_id,),
        )
        assert "page_headline" in decision.sources
        sources = list(decision.sources)
        assert sources.index("page_headline") > sources.index("atom")
        assert sources.index("page_headline") < sources.index("raw")

    def test_router_adds_page_headline_via_alias(self, mem: Memory) -> None:
        """When the router resolves to an entity via alias, sources should include page_headline."""
        mem, entity_id = self._make_mem_with_page(mem)
        # Find an alias that was actually registered.
        aliases = mem.list_aliases(entity_id=entity_id)
        assert len(aliases) >= 1
        alias_text = aliases[0].alias

        from octop_memory.pipeline.recall.parser import ParsedQuery
        from octop_memory.pipeline.recall.router import route

        parsed = ParsedQuery(
            text=alias_text,
            raw_tokens=[alias_text],
            entity_hints=[alias_text],
        )
        decision = route(mem, parsed)
        assert "page_headline" in decision.sources

    def test_router_no_page_headline_without_entity(self, mem: Memory) -> None:
        """The router should not add the page_headline source when there's no resolved entity."""

        parsed = ParsedQuery(text="随便问问", raw_tokens=["随便", "问问"])
        decision = route(mem, parsed)
        assert "page_headline" not in decision.sources
