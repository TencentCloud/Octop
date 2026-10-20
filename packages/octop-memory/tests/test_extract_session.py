"""Tests for ``extract_session`` (extractor + Memory glue)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory.core import Memory
from octop_memory.pipeline.extractor import CandidateExtractor, extract_session
from octop_memory.ports.llm import MockLLMClient, NoopLLMClient
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    backend = SqliteMemoryBackend(namespace="m2", db_path=tmp_path / "extract.sqlite")
    return Memory(namespace="m2", backend=backend)


def _seed_session(memory: Memory, session_id: str = "sess-1") -> list[str]:
    """Seed three raw events for the session and return their ids."""
    ids: list[str] = []
    for i, content in enumerate(
        [
            "decided to use Augment first, NOT replace mode",
            "好的，已记住",
            "what's the deadline?",
        ]
    ):
        ev = memory.add_raw(
            content=content,
            event_type="user_message" if i != 1 else "assistant_message",
            host="manual",
            session_id=session_id,
        )
        ids.append(ev.id)
    return ids


def _candidate_payload_referencing(quote_event_id: str, source_refs: list[str]) -> str:
    """Synthesize a Candidate JSON that references the given raw event ids."""
    return json.dumps(
        {
            "candidates": [
                {
                    "candidate_id": "",
                    "candidate_type": "Decision",
                    "status": "pending",
                    "title": "mode decision",
                    "assertion": "decided to use Augment first, NOT replace mode",
                    "verbatim_quote": "decided to use Augment first, NOT replace mode",
                    "quote_event_id": quote_event_id,
                    "subject": {"name": "Project X", "entity_type": "Project", "entity_id_hint": ""},
                    "target_entities": [],
                    "source_refs": source_refs,
                    "confidence": "high",
                    "importance": "high",
                    "recommended_action": "promote",
                    "promotion_reason": "explicit",
                }
            ]
        }
    )


class TestExtractSession:
    def test_pulls_raw_events_for_session_and_persists(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        mock = MockLLMClient(default_response=_candidate_payload_referencing(ids[0], ids))
        extractor = CandidateExtractor(llm=mock)

        result = extract_session(memory=memory, extractor=extractor, session_id="sess-1")

        assert len(result.candidates) == 1
        assert result.failure_reason is None

        # Persisted to backend (default persist=True)
        listed = memory.list_candidates(session_id="sess-1")
        assert len(listed) == 1
        assert listed[0].assertion == "decided to use Augment first, NOT replace mode"

    def test_no_raw_events_short_circuits(self, memory: Memory) -> None:
        # Empty session — no LLM call.
        mock = MockLLMClient(raise_on_call=True)
        extractor = CandidateExtractor(llm=mock)

        result = extract_session(memory=memory, extractor=extractor, session_id="ghost-session")

        assert result.candidates == []
        assert result.llm_calls == 0
        assert mock.calls == []

    def test_persist_false_does_not_save(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        mock = MockLLMClient(default_response=_candidate_payload_referencing(ids[0], ids))
        extractor = CandidateExtractor(llm=mock)

        result = extract_session(memory=memory, extractor=extractor, session_id="sess-1", persist=False)

        assert len(result.candidates) == 1
        assert memory.list_candidates(session_id="sess-1") == []

    def test_llm_failure_does_not_corrupt_storage(self, memory: Memory) -> None:
        _seed_session(memory)
        extractor = CandidateExtractor(llm=NoopLLMClient())

        result = extract_session(memory=memory, extractor=extractor, session_id="sess-1")

        assert result.candidates == []
        assert result.failure_reason is not None
        # No partial writes to storage.
        assert memory.list_candidates(session_id="sess-1") == []

    def test_uses_only_session_specific_raw_events(self, memory: Memory) -> None:
        _seed_session(memory, session_id="sess-A")
        _seed_session(memory, session_id="sess-B")
        # If extractor referenced sess-B raw ids while we asked for sess-A,
        # parser would reject. So the helper must filter by session_id.
        a_ids = [e.id for e in memory.list_raw(session_id="sess-A", limit=100)]
        mock = MockLLMClient(default_response=_candidate_payload_referencing(a_ids[0], a_ids))
        extractor = CandidateExtractor(llm=mock)

        result = extract_session(memory=memory, extractor=extractor, session_id="sess-A")
        assert len(result.candidates) == 1
        assert all(rid in a_ids for rid in result.candidates[0].raw_event_ids)
