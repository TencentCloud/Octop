"""Tests for the bridge ``extract`` / ``promote`` RPC methods.

These drive ``Bridge.handle`` directly (no subprocess) with a tier-aware
LLM stub: ``light`` calls get extractor JSON, ``heavy`` calls get page
regen JSON. That exercises the full L0 → L1 → L2 → L3 pipeline the
OpenClaw TS shell triggers after agent_end capture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from octop_memory.adapters.bridge.handlers import ERR_INVALID_PARAMS, Bridge
from octop_memory.application.config import MemoryRuntimeConfig
from octop_memory.core import Memory
from octop_memory.ports.llm._protocol import LLMClientError, LLMTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    db_path = tmp_path / "bridge_extract.sqlite"
    return Memory(
        namespace="test_bridge_extract",
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
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


class FailingLLM:
    """LLM stub that always raises (no-LLM degradation path)."""

    def call_llm(self, prompt: str, **kwargs: object) -> str:
        raise LLMClientError("no LLM in this test")


def _seed_session(memory: Memory, session_id: str = "sess-1") -> list[str]:
    ids: list[str] = []
    for i, content in enumerate(
        [
            "decided to use Augment first, NOT replace mode",
            "好的，已记住",
        ]
    ):
        ev = memory.add_raw(
            content=content,
            event_type="user_message" if i == 0 else "assistant_message",
            host="openclaw",
            session_id=session_id,
        )
        ids.append(ev.id)
    return ids


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


def _bridge_with_tier_llm(memory: Memory, ids: list[str]) -> tuple[Bridge, TierLLM]:
    llm = TierLLM(light=_extractor_json(ids[0], ids), heavy=_REGEN_JSON)
    return Bridge(memory, llm=llm), llm


def _call(bridge: Bridge, method: str, params: dict) -> dict:
    return bridge.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


class TestExtract:
    def test_full_pipeline(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, llm = _bridge_with_tier_llm(memory, ids)

        resp = _call(bridge, "extract", {"session_id": "sess-1"})
        result = resp["result"]

        assert result["events_extracted"] == 2
        assert result["candidates"] == 1
        assert result["failure_reason"] is None
        assert result["promotion"]["promoted"] == 1
        assert result["pages"]["regenerated"] == 1
        # Calls: candidate-extract (light) + page-regen (heavy) +
        # episode-extract (light, M5 — runs in parallel and uses the
        # candidate-shaped canned response, which it harmlessly fails
        # to parse as episodes).
        assert llm.calls == ["light", "heavy", "light"]

        counts = memory.backend.count_stats()
        assert counts["atoms"] == 1
        assert counts["entities"] == 1
        page = memory.get_entity_page(memory.list_entities(limit=1)[0].id)
        assert page is not None
        assert page.dirty is False

    def test_incremental_skips_already_extracted_events(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, llm = _bridge_with_tier_llm(memory, ids)

        first = _call(bridge, "extract", {"session_id": "sess-1"})["result"]
        assert first["events_extracted"] == 2
        calls_after_first = len(llm.calls)

        second = _call(bridge, "extract", {"session_id": "sess-1"})["result"]
        assert second["events_extracted"] == 0
        assert second["candidates"] == 0
        # No further LLM calls on a quiet session.
        assert len(llm.calls) == calls_after_first

    def test_incremental_false_re_extracts(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        _call(bridge, "extract", {"session_id": "sess-1"})
        again = _call(bridge, "extract", {"session_id": "sess-1", "incremental": False})["result"]
        assert again["events_extracted"] == 2

    def test_promote_false_leaves_candidates_pending(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        result = _call(bridge, "extract", {"session_id": "sess-1", "promote": False})["result"]
        assert result["candidates"] == 1
        assert result["promotion"] is None
        assert memory.backend.count_stats()["atoms"] == 0
        assert len(memory.list_candidates(status="pending")) == 1

    def test_missing_session_id_is_invalid_params(self, memory: Memory) -> None:
        bridge = Bridge(memory)
        resp = _call(bridge, "extract", {})
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_llm_failure_degrades_and_allows_retry(self, memory: Memory) -> None:
        _seed_session(memory)
        bridge = Bridge(memory, llm=FailingLLM())

        first = _call(bridge, "extract", {"session_id": "sess-1"})["result"]
        assert first["failure_reason"] is not None
        assert first["candidates"] == 0

        # Events were NOT marked extracted — the next call retries them.
        second = _call(bridge, "extract", {"session_id": "sess-1"})["result"]
        assert second["events_extracted"] == 2

    def test_no_llm_config_uses_noop_and_reports_failure(self, memory: Memory) -> None:
        _seed_session(memory)
        bridge = Bridge(memory)  # no llm injected, no llm config

        result = _call(bridge, "extract", {"session_id": "sess-1"})["result"]
        assert result["failure_reason"] is not None
        assert "no LLM backend" in result["failure_reason"]


class TestExtractRunMeta:
    """Completed passes overwrite ``last_extract_run`` meta and do not journal."""

    def test_fruitful_run_records_stats(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        _call(bridge, "extract", {"session_id": "sess-1"})
        assert memory.list_journal(action="extract_run", limit=10) == []
        stats = memory.get_last_extract_run()
        assert stats is not None
        assert stats["events_extracted"] == 2
        assert stats["candidates"] == 1
        assert stats["promoted"] == 1
        assert stats["failure_reason"] is None
        assert stats["quiet"] is False

    def test_empty_run_overwrites_meta(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        _call(bridge, "extract", {"session_id": "sess-1"})
        _call(bridge, "extract", {"session_id": "sess-1"})

        assert memory.list_journal(action="extract_run", limit=10) == []
        latest = memory.get_last_extract_run()
        assert latest is not None
        assert latest["events_extracted"] == 0
        assert latest["candidates"] == 0
        assert latest["quiet"] is True
        assert "no new events" in latest["note"]

    def test_repeated_quiet_runs_do_not_grow_journal(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        _call(bridge, "extract", {"session_id": "sess-1"})
        _call(bridge, "extract", {"session_id": "sess-1"})
        _call(bridge, "extract", {"session_id": "sess-1"})
        _call(bridge, "extract", {"session_id": "sess-1"})

        assert memory.list_journal(action="extract_run", limit=10) == []
        assert memory.get_last_extract_run() is not None

    def test_failed_run_records_failure_reason(self, memory: Memory) -> None:
        _seed_session(memory)
        bridge = Bridge(memory, llm=FailingLLM())

        _call(bridge, "extract", {"session_id": "sess-1"})
        assert memory.list_journal(action="extract_run", limit=10) == []
        stats = memory.get_last_extract_run()
        assert stats is not None
        assert stats["failure_reason"] is not None
        assert "extraction failed" in stats["note"]

    def test_invalid_params_writes_no_run(self, memory: Memory) -> None:
        bridge = Bridge(memory)
        _call(bridge, "extract", {})  # missing session_id → ValueError, not a run
        assert memory.get_last_extract_run() is None
        assert memory.list_journal(action="extract_run", limit=10) == []


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------


class TestPromote:
    def test_promotes_pending_candidates(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        _call(bridge, "extract", {"session_id": "sess-1", "promote": False, "regen_pages": False})
        result = _call(bridge, "promote", {})["result"]

        assert result["promoted"] == 1
        assert memory.backend.count_stats()["atoms"] == 1

    def test_promote_with_regen_pages(self, memory: Memory) -> None:
        ids = _seed_session(memory)
        bridge, _ = _bridge_with_tier_llm(memory, ids)

        _call(bridge, "extract", {"session_id": "sess-1", "promote": False, "regen_pages": False})
        result = _call(bridge, "promote", {"regen_pages": True})["result"]

        assert result["promoted"] == 1
        assert result["pages"]["regenerated"] == 1


# ---------------------------------------------------------------------------
# config / stats surface
# ---------------------------------------------------------------------------


class TestLlmConfigSurface:
    def test_stats_reports_llm_without_api_key(self, memory: Memory) -> None:
        bridge = Bridge(
            memory,
            config=MemoryRuntimeConfig(
                llm={
                    "endpoint": "https://api.example.com/v1",
                    "model": "small-model",
                    "model_heavy": "big-model",
                    "api_key": "sk-secret-do-not-echo",
                }
            ),
        )
        result = _call(bridge, "stats", {})["result"]
        llm_info = result["config"]["llm"]
        assert llm_info["configured"] is True
        assert llm_info["endpoint"] == "https://api.example.com/v1"
        assert llm_info["model"] == "small-model"
        assert llm_info["model_heavy"] == "big-model"
        assert "sk-secret-do-not-echo" not in json.dumps(result)

    def test_stats_reports_unconfigured_llm(self, memory: Memory) -> None:
        bridge = Bridge(memory)
        result = _call(bridge, "stats", {})["result"]
        assert result["config"]["llm"]["configured"] is False

    def test_extraction_config_override(self, memory: Memory) -> None:
        bridge = Bridge(memory, config={"extraction": {"promote": False, "max_candidates": 7}})
        cfg = _call(bridge, "stats", {})["result"]["config"]["extraction"]
        assert cfg["promote"] is False
        assert cfg["max_candidates"] == 7
        assert cfg["regen_pages"] is True
