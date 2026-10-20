"""End-to-end tests for the M3 page regenerator.

Covers:
- D33-B mark-dirty hook is fired on atom promotion.
- D36-A single-JSON LLM contract: parsing happy path + parse failure
  + LLM error.
- D34-A ``## My Notes`` is preserved across regen.
- D35-A failed regen keeps the previous summary and increments
  ``regen_attempt_count``.
- Batch regen (``regenerate_dirty``) processes all dirty pages and
  isolates failures.
- Empty-entity edge case produces an empty page without an LLM call.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.page import (
    HEADLINE_MAX_CHARS,
    regenerate_dirty,
    regenerate_page,
)
from octop_memory.pipeline.promotion import promote_candidates
from octop_memory.ports.llm._protocol import LLMClientError
from octop_memory.ports.llm.mock import MockLLMClient
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend
from octop_memory.types import Candidate, Entity, EntityPage, RawEvent


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="m3", db_path=tmp_path / "m3.sqlite")
    return Memory(namespace="m3", backend=backend)


def _seed_entity_with_atoms(memory: Memory, *, name: str = "Octop Memory") -> str:
    """Helper: create entity + a couple of atoms + dirty page row.

    Returns the entity_id.
    """
    when = _now()
    # Use the entity name as a per-call uniqueness suffix so the helper
    # can be called multiple times in the same test (batch tests).
    suffix = name.lower().replace(" ", "_")
    entity = Entity(
        id=f"ent-{suffix}",
        entity_type="Project",
        canonical_name=name,
        aliases=[],
        atom_count=0,
        created_at=when,
    )
    memory.add_entity(entity)

    raw = RawEvent(
        id=f"raw-{suffix}",
        host="dogfood",
        session_id="s1",
        thread_id=None,
        user=None,
        timestamp=when,
        event_type="user_message",
        content="x",
        payload={},
    )
    memory.add_raw_batch([raw])

    candidates = [
        Candidate(
            id=f"c-{suffix}-{i}",
            raw_event_ids=[f"raw-{suffix}"],
            candidate_type="Fact",
            status="pending",
            title=f"fact-{i}",
            assertion=f"{name} fact #{i}",
            verbatim_quote=f"{name} fact #{i}",
            quote_event_id=f"raw-{suffix}",
            subject_name=name,
            subject_entity_type="Project",
            target_entity_id=None,
            confidence="high",
            importance="high",
            recommended_action="promote",
            promotion_reason="",
            extractor_version="v2.1",
            created_at=when,
            session_id="s1",
        )
        for i in range(2)
    ]
    for c in candidates:
        memory.add_candidate(c)

    promote_candidates(memory, candidates)
    # The promotion will have created/used an entity by name. Find it.
    found = memory.find_entity_by_name(name)
    assert found is not None
    return found.id


def _good_response(headline: str = "rocking entity", body: str = "## Summary\nbody (atom-1)") -> str:
    return json.dumps(
        {
            "headline": headline,
            "summary_markdown": body,
            "topics": ["alpha", "beta"],
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# D33-B trigger: promotion marks page dirty
# ---------------------------------------------------------------------------


class TestDirtyTrigger:
    def test_promote_marks_page_dirty(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        page = memory.get_entity_page(eid)
        assert page is not None
        assert page.dirty is True

    def test_dirty_list_contains_entity(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        dirty = memory.list_dirty_entity_pages()
        assert any(p.entity_id == eid for p in dirty)


# ---------------------------------------------------------------------------
# D36-A / D37-B happy path
# ---------------------------------------------------------------------------


class TestRegenHappyPath:
    def test_success_writes_summary_and_clears_dirty(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        llm = MockLLMClient(default_response=_good_response("Octop Memory notes"))

        result = regenerate_page(memory, eid, llm=llm)

        assert result.success is True
        assert result.headline == "Octop Memory notes"
        assert "Summary" in result.summary_markdown
        page = memory.get_entity_page(eid)
        assert page is not None
        assert page.dirty is False
        assert page.regen_attempt_count == 0
        assert page.summary_version == 1
        assert page.last_regen_at is not None
        assert page.headline == "Octop Memory notes"

    def test_strips_markdown_fences(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        wrapped = "```json\n" + _good_response() + "\n```"
        llm = MockLLMClient(default_response=wrapped)
        result = regenerate_page(memory, eid, llm=llm)
        assert result.success is True

    def test_journal_entry_recorded(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        llm = MockLLMClient(default_response=_good_response())
        regenerate_page(memory, eid, llm=llm)
        rows = memory.list_journal(target_entity_id=eid, limit=20)
        actions = [r.action for r in rows]
        assert "page_regen" in actions

    def test_topics_capped_at_five(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        too_many = json.dumps(
            {
                "headline": "x",
                "summary_markdown": "body",
                "topics": [f"topic-{i}" for i in range(20)],
            }
        )
        llm = MockLLMClient(default_response=too_many)
        result = regenerate_page(memory, eid, llm=llm)
        assert len(result.topics) == 5

    def test_headline_hard_clamped(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        long_headline = "x" * 80
        llm = MockLLMClient(default_response=_good_response(headline=long_headline))
        regenerate_page(memory, eid, llm=llm)
        page = memory.get_entity_page(eid)
        assert page is not None
        assert len(page.headline) == HEADLINE_MAX_CHARS


# ---------------------------------------------------------------------------
# D34-A user notes preservation
# ---------------------------------------------------------------------------


class TestUserNotes:
    def test_preserves_existing_notes_through_regen(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        # Pre-seed an existing page with user notes
        when = _now()
        existing = EntityPage(
            id=f"page_{eid}",
            entity_id=eid,
            summary_markdown="old summary\n\n## My Notes\nUSER PERSONAL THOUGHTS",
            headline="old",
            topics=[],
            dirty=True,
            regen_attempt_count=0,
            summary_version=1,
            last_regen_at=when,
            last_user_edit_at=when,
            created_at=when,
            updated_at=when,
        )
        memory.upsert_entity_page(existing)

        # LLM returns a body WITHOUT the notes section.
        llm = MockLLMClient(
            default_response=json.dumps(
                {
                    "headline": "new",
                    "summary_markdown": "## Summary\nnew summary body",
                    "topics": [],
                }
            )
        )
        result = regenerate_page(memory, eid, llm=llm)

        assert result.success is True
        assert "USER PERSONAL THOUGHTS" in result.summary_markdown
        assert "## My Notes" in result.summary_markdown

    def test_drops_llm_emitted_notes_section(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        when = _now()
        memory.upsert_entity_page(
            EntityPage(
                id=f"page_{eid}",
                entity_id=eid,
                summary_markdown="old\n## My Notes\nKEEP ME",
                headline="o",
                topics=[],
                dirty=True,
                regen_attempt_count=0,
                summary_version=1,
                last_regen_at=when,
                last_user_edit_at=when,
                created_at=when,
                updated_at=when,
            )
        )
        # LLM also emits its OWN notes section — must be dropped.
        rogue = json.dumps(
            {
                "headline": "x",
                "summary_markdown": "## Summary\nbody\n\n## My Notes\nLLM HALLUCINATION",
                "topics": [],
            }
        )
        llm = MockLLMClient(default_response=rogue)
        result = regenerate_page(memory, eid, llm=llm)

        assert result.success is True
        assert "LLM HALLUCINATION" not in result.summary_markdown
        assert "KEEP ME" in result.summary_markdown


# ---------------------------------------------------------------------------
# D35-A failure: keep old summary, increment attempt
# ---------------------------------------------------------------------------


class TestFailureKeepsOldSummary:
    def test_llm_error_records_failure(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        # Pre-seed an existing summary so we can verify it's preserved.
        when = _now()
        memory.upsert_entity_page(
            EntityPage(
                id=f"page_{eid}",
                entity_id=eid,
                summary_markdown="OLD_GOOD_SUMMARY",
                headline="old",
                topics=["existing"],
                dirty=True,
                regen_attempt_count=0,
                summary_version=2,
                last_regen_at=when,
                last_user_edit_at=None,
                created_at=when,
                updated_at=when,
            )
        )
        llm = MockLLMClient(raise_on_call=True)

        result = regenerate_page(memory, eid, llm=llm)

        assert result.success is False
        assert "llm_error" in result.reason
        page = memory.get_entity_page(eid)
        assert page is not None
        assert page.summary_markdown == "OLD_GOOD_SUMMARY"
        assert page.headline == "old"
        assert page.summary_version == 2  # NOT bumped
        assert page.regen_attempt_count == 1
        assert page.dirty is True  # stays dirty for retry

    def test_malformed_json_records_failure(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        llm = MockLLMClient(default_response="this is not JSON at all")
        result = regenerate_page(memory, eid, llm=llm)
        assert result.success is False
        assert "parse_error" in result.reason
        # journal entry exists
        rows = memory.list_journal(target_entity_id=eid, action="page_regen_failed", limit=10)
        assert len(rows) >= 1

    def test_multiple_failures_increment_counter(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        llm = MockLLMClient(default_response="garbage")
        for _ in range(3):
            regenerate_page(memory, eid, llm=llm)
        page = memory.get_entity_page(eid)
        assert page is not None
        assert page.regen_attempt_count == 3

    def test_success_after_failure_resets_counter(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)
        bad_llm = MockLLMClient(default_response="not json")
        regenerate_page(memory, eid, llm=bad_llm)
        regenerate_page(memory, eid, llm=bad_llm)
        page = memory.get_entity_page(eid)
        assert page is not None and page.regen_attempt_count == 2

        good_llm = MockLLMClient(default_response=_good_response())
        result = regenerate_page(memory, eid, llm=good_llm)
        assert result.success is True
        page2 = memory.get_entity_page(eid)
        assert page2 is not None and page2.regen_attempt_count == 0


# ---------------------------------------------------------------------------
# Empty entity edge case (no LLM call)
# ---------------------------------------------------------------------------


class TestEmptyEntity:
    def test_empty_entity_skips_llm(self, memory: Memory) -> None:
        # Manually create an entity with NO atoms, then mark its page dirty.
        when = _now()
        memory.add_entity(
            Entity(
                id="ent-empty",
                entity_type="Fact",
                canonical_name="emptyset",
                aliases=[],
                atom_count=0,
                created_at=when,
            )
        )
        memory.mark_entity_page_dirty("ent-empty", when=when)

        # LLM that would explode if called.
        llm = MockLLMClient(raise_on_call=True)

        result = regenerate_page(memory, "ent-empty", llm=llm)

        assert result.success is True
        page = memory.get_entity_page("ent-empty")
        assert page is not None
        assert page.dirty is False
        assert page.summary_markdown == ""
        # MockLLMClient.calls is empty since we didn't call it.
        assert llm.calls == []


# ---------------------------------------------------------------------------
# Batch worker: regenerate_dirty
# ---------------------------------------------------------------------------


class TestBatchRegen:
    def test_processes_all_dirty(self, memory: Memory) -> None:
        # Two entities with atoms.
        e1 = _seed_entity_with_atoms(memory, name="ProjectA")
        e2 = _seed_entity_with_atoms(memory, name="ProjectB")
        llm = MockLLMClient(default_response=_good_response())

        batch = regenerate_dirty(memory, llm=llm, limit=10)

        assert batch.success_count == 2
        assert batch.failure_count == 0
        assert len(memory.list_dirty_entity_pages()) == 0
        assert memory.get_entity_page(e1) is not None
        assert memory.get_entity_page(e2) is not None

    def test_failure_does_not_block_others(self, memory: Memory) -> None:
        e1 = _seed_entity_with_atoms(memory, name="ProjectA")
        e2 = _seed_entity_with_atoms(memory, name="ProjectB")

        # Per-call response: alternate between bad / good.
        responses = iter(["not json at all", _good_response()])

        class _Switcher:
            def call_llm(self, prompt: str, **kwargs: object) -> str:
                return next(responses)

        batch = regenerate_dirty(memory, llm=_Switcher(), limit=10)  # type: ignore[arg-type]

        assert batch.success_count == 1
        assert batch.failure_count == 1
        # The failed page is still dirty, the other is clean.
        dirty = memory.list_dirty_entity_pages()
        dirty_ids = {p.entity_id for p in dirty}
        assert dirty_ids in ({e1}, {e2})

    def test_respects_limit(self, memory: Memory) -> None:
        for i in range(3):
            _seed_entity_with_atoms(memory, name=f"P{i}")
        llm = MockLLMClient(default_response=_good_response())
        batch = regenerate_dirty(memory, llm=llm, limit=2)
        assert len(batch.results) == 2
        # one page still dirty
        assert len(memory.list_dirty_entity_pages()) == 1


# ---------------------------------------------------------------------------
# Programmer error: missing entity
# ---------------------------------------------------------------------------


class TestMissingEntity:
    def test_raises_value_error(self, memory: Memory) -> None:
        with pytest.raises(ValueError):
            regenerate_page(memory, "no-such-id", llm=MockLLMClient(default_response=_good_response()))


# ---------------------------------------------------------------------------
# LLMClientError surfacing — ensure the worker never propagates LLM errors
# ---------------------------------------------------------------------------


class TestErrorSurfacing:
    def test_error_subclass_caught(self, memory: Memory) -> None:
        eid = _seed_entity_with_atoms(memory)

        class _ExplodingClient:
            def call_llm(self, prompt: str, **kwargs: object) -> str:
                raise LLMClientError("simulated outage")

        result = regenerate_page(memory, eid, llm=_ExplodingClient())  # type: ignore[arg-type]
        assert result.success is False
        assert "simulated outage" in result.reason
