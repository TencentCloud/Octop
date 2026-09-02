from __future__ import annotations

from octop.infra.trajectory.projector import project_harness_chunk


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


def test_unknown_chunk_becomes_unknown_kind() -> None:
    events = project_harness_chunk(
        {"type": "not_a_real_chunk"}, agent_id="A1", thread_id="T1", seq=1
    )
    assert events[0].kind in ("unknown", "system")
