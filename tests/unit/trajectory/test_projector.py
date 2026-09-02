"""Harness/session-fact projector tests.

Fixture shapes live in ``tests/unit/trajectory/fixtures/``:

* ``session_user.json`` — anonymized MemoryMiddleware ``sessions/*.jsonl`` user
  line (real local samples use ``role`` not ``type``; ISO-8601 ``ts``).
  Keys: ``ts``, ``role=user``, ``content``, ``thread_id``, ``source``.
* ``context_injection.json`` — synthetic; session JSONL has no context rows.
  Spec §2 ``context`` (source / label / token estimate). ``source=rules``
  matches ``harness_agent.context_usage`` (AGENTS.md / ``<agent_memory>``).
* ``compacted.json`` — synthetic; matches ``harness_agent.compaction.CompactResult``
  field names (``summarized_count``, ``preserved_count``, ``removed_tokens``)
  plus spec §2 ``summary`` / ``file_path``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop.infra.trajectory.projector import project_harness_chunk

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_project_tool_call_chunk_emits_tool_event() -> None:
    chunk = {
        "type": "tool_call_chunk",
        "id": "call_1",
        "name": "read_file",
        "args": {"path": "a.py"},
    }
    events = project_harness_chunk(chunk, agent_id="A1", thread_id="T1", seq=10)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "tool"
    assert ev.seq == 10
    assert ev.thread_id == "T1"
    assert ev.event_id == "T1:10:tool:call_1"
    assert "read_file" in ev.summary
    assert ev.payload["call_id"] == "call_1"


def test_project_token_chunk_emits_assistant_event() -> None:
    chunk = {"type": "token", "node": "agent", "content": "Hello world"}
    events = project_harness_chunk(chunk, agent_id="A1", thread_id="T1", seq=3)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "assistant"
    assert ev.seq == 3
    assert "Hello" in ev.summary


def test_empty_token_chunk_emits_no_events() -> None:
    events = project_harness_chunk(
        {"type": "token", "node": "agent", "content": ""},
        agent_id="A1",
        thread_id="T1",
        seq=4,
    )
    assert events == []


def test_unknown_chunk_becomes_unknown_kind() -> None:
    events = project_harness_chunk(
        {"type": "not_a_real_chunk"}, agent_id="A1", thread_id="T1", seq=1
    )
    assert len(events) == 1
    assert events[0].kind in ("unknown", "system")


def test_project_session_user_fact_emits_user_event() -> None:
    chunk = _load_fixture("session_user.json")
    events = project_harness_chunk(chunk, agent_id="A1", thread_id="T1", seq=5)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "user"
    assert ev.seq == 5
    assert ev.thread_id == "T1"
    assert ev.event_id == "T1:5:user"
    assert "Compare React and Vue" in ev.summary
    assert ev.payload["content"] == chunk["content"]
    assert ev.ts > 0


def test_project_context_injection_fact_emits_context_event() -> None:
    chunk = _load_fixture("context_injection.json")
    events = project_harness_chunk(chunk, agent_id="A1", thread_id="T1", seq=7)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "context"
    assert ev.event_id == "T1:7:context"
    assert ev.payload["source"] == "rules"
    assert ev.payload["label"] == "AGENTS.md"
    assert ev.payload["tokens"] == 1280
    assert "AGENTS.md" in ev.summary


def test_project_compacted_fact_emits_compacted_event() -> None:
    chunk = _load_fixture("compacted.json")
    events = project_harness_chunk(chunk, agent_id="A1", thread_id="T1", seq=8)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "compacted"
    assert ev.event_id == "T1:8:compacted"
    assert ev.payload["summarized_count"] == 12
    assert ev.payload["preserved_count"] == 6
    assert ev.payload["removed_tokens"] == 4200
    assert "offloaded" in ev.summary.lower() or "compact" in ev.summary.lower()


def test_bad_input_never_raises() -> None:
    events = project_harness_chunk(
        "not-a-chunk",  # type: ignore[arg-type]
        agent_id="A1",
        thread_id="T1",
        seq=1,
    )
    assert len(events) == 1
    assert events[0].kind in ("unknown", "system")

    events = project_harness_chunk(
        {"type": "user", "ts": object(), "content": "hi"},
        agent_id="A1",
        thread_id="T1",
        seq=2,
    )
    assert len(events) == 1
    assert events[0].kind == "user"

    events = project_harness_chunk(
        {"type": "nope", "ts": "not-a-timestamp"},
        agent_id="A1",
        thread_id="T1",
        seq=3,
    )
    assert len(events) == 1
    assert events[0].kind in ("unknown", "system")
    assert events[0].ts == 0.0
