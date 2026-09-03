"""Unit tests for trajectory list payload projection."""

from __future__ import annotations

from typing import Any

from octop.api.routers.chat.trajectory import (
    _LIST_MAX_SUMMARY_CHARS,
    _LIST_MAX_TOOL_FIELD_CHARS,
    _resume_after_seq,
    _summarize_event,
)
from octop.infra.trajectory.types import TrajectoryEvent


def _event(
    *,
    kind: str = "tool",
    summary: str = "x",
    payload: dict[str, Any] | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id="e1",
        thread_id="T1",
        agent_id="A1",
        seq=1,
        ts=1.0,
        kind=kind,  # type: ignore[arg-type]
        turn_id=None,
        request_seq=None,
        is_error=False,
        summary=summary,
        payload=payload or {},
    )


def test_summarize_keeps_tool_args_and_result() -> None:
    data = _summarize_event(
        _event(
            payload={
                "name": "read_file",
                "args": {"path": "a.py"},
                "result": "ok",
                "tool_duration_ms": 12,
            }
        )
    )
    assert data["payload"] == {
        "name": "read_file",
        "args": {"path": "a.py"},
        "result": "ok",
        "tool_duration_ms": 12,
    }


def test_summarize_omits_message_bodies() -> None:
    data = _summarize_event(
        _event(
            kind="user",
            payload={"content": "secret body", "source": "dashboard", "text": "also"},
        )
    )
    assert data["payload"] == {"source": "dashboard"}
    assert "content" not in data["payload"]
    assert "text" not in data["payload"]


def test_summarize_clips_oversized_tool_result() -> None:
    huge = "x" * (_LIST_MAX_TOOL_FIELD_CHARS + 50)
    data = _summarize_event(_event(payload={"name": "bash", "result": huge}))
    result = data["payload"]["result"]
    assert isinstance(result, str)
    assert result.endswith("…")
    assert len(result) == _LIST_MAX_TOOL_FIELD_CHARS + 1


def test_summarize_clips_message_summary() -> None:
    data = _summarize_event(_event(kind="user", summary="x" * (_LIST_MAX_SUMMARY_CHARS + 50)))

    assert data["summary"].endswith("…")
    assert len(data["summary"]) == _LIST_MAX_SUMMARY_CHARS


def test_sse_resume_prefers_newer_last_event_id() -> None:
    assert _resume_after_seq(10, "14") == 14
    assert _resume_after_seq(10, "8") == 10
