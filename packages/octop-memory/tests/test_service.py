"""Tests for the MemoryService transport-neutral facade.

These drive the typed facade directly (no JSON-RPC envelopes), mirroring how an
in-process host (octop-harness / Hermes) would use it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from octop_memory import MemoryService
from octop_memory.core import Memory
from octop_memory.pipeline.recall import RecallResult
from octop_memory.ports.llm._protocol import LLMTier


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(
        namespace="test_service",
        backend="sqlite",
        backend_config={"db_path": str(tmp_path / "svc.sqlite")},
    )


class TierLLM:
    """LLM stub returning a canned response per workload tier."""

    def __init__(self, *, light: str, heavy: str) -> None:
        self._responses = {"light": light, "heavy": heavy}
        self.calls: list[LLMTier] = []

    def call_llm(
        self,
        prompt: str,
        *,
        tier: LLMTier = "light",
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: Literal["text", "json"] = "text",
    ) -> str:
        self.calls.append(tier)
        return self._responses[tier]


def _extractor_json(quote_event_id: str, source_refs: list[str]) -> str:
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


_REGEN_JSON = json.dumps(
    {
        "summary_markdown": "## Project X\n\nUses Augment mode first.",
        "headline": "Project X: Augment first",
        "topics": ["mode"],
    }
)

# Capture config with the min-length filter disabled so short test messages pass.
_OPEN_CAPTURE = {"capture": {"min_message_chars": 0, "include_roles": ["user", "assistant"]}}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class TestRead:
    def test_recall_returns_recall_result(self, memory: Memory) -> None:
        svc = MemoryService(memory, host="test")
        result = svc.recall("anything")
        assert isinstance(result, RecallResult)
        assert result.snippets == []
        assert result.rendered == ""

    def test_search_empty(self, memory: Memory) -> None:
        svc = MemoryService(memory)
        out = svc.search("nothing-matches-zzz")
        assert out["total"] == 0
        assert out["hits"] == []


# ---------------------------------------------------------------------------
# Write — capture
# ---------------------------------------------------------------------------


class TestCaptureTurn:
    def test_save_writes_canonical_memory(self, memory: Memory) -> None:
        svc = MemoryService(memory)

        node = svc.save("User prefers dark mode", topic="preferences")

        assert node.topic == "preferences"
        assert "dark mode" in node.content
        assert memory.recall("dark mode")

    def test_writes_two_raw_events(self, memory: Memory) -> None:
        svc = MemoryService(memory, host="octop-harness", config=_OPEN_CAPTURE)
        svc.capture_turn(user="hello there", assistant="hi back", session_id="s1", thread_id="t1")

        raws = memory.list_raw(session_id="s1")
        assert len(raws) == 2
        assert {r.event_type for r in raws} == {"user_message", "assistant_message"}
        assert all(r.host == "octop-harness" for r in raws)

    def test_empty_turn_is_noop(self, memory: Memory) -> None:
        svc = MemoryService(memory, config=_OPEN_CAPTURE)
        svc.capture_turn(user=None, assistant=None, session_id="s1")
        assert memory.list_raw(session_id="s1") == []

    def test_only_user_side(self, memory: Memory) -> None:
        svc = MemoryService(memory, config=_OPEN_CAPTURE)
        svc.capture_turn(user="just the user speaking", session_id="s1")
        raws = memory.list_raw(session_id="s1")
        assert len(raws) == 1
        assert raws[0].event_type == "user_message"


# ---------------------------------------------------------------------------
# Write — extract (the L0 → L2/L3 distill pipeline)
# ---------------------------------------------------------------------------


class TestExtract:
    def _seed(self, memory: Memory) -> list[str]:
        ids = [
            memory.add_raw(
                content="decided to use Augment first, NOT replace mode",
                event_type="user_message",
                host="octop-harness",
                session_id="s1",
            ).id,
            memory.add_raw(
                content="好的，已记住",
                event_type="assistant_message",
                host="octop-harness",
                session_id="s1",
            ).id,
        ]
        return ids

    def test_full_pipeline_with_model(self, memory: Memory) -> None:
        ids = self._seed(memory)
        llm = TierLLM(light=_extractor_json(ids[0], ids), heavy=_REGEN_JSON)
        svc = MemoryService(memory, llm=llm)

        out = svc.extract("s1")

        assert out["events_extracted"] == 2
        assert len(memory.list_atoms()) >= 1  # candidate promoted to an atom
        assert "light" in llm.calls  # extraction tier was used

    def test_without_model_degrades(self, memory: Memory) -> None:
        self._seed(memory)
        svc = MemoryService(memory)  # no llm → NoopLLMClient

        out = svc.extract("s1")  # must not raise

        assert isinstance(out, dict)
        assert memory.list_atoms() == []  # no distillation without a model


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


class TestWiring:
    def test_exposes_memory(self, memory: Memory) -> None:
        svc = MemoryService(memory)
        assert svc.memory is memory
