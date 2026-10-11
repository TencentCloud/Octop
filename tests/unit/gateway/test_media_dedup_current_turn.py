"""Replayed history must not re-push media that an earlier turn delivered."""

from __future__ import annotations

from octop.infra.gateway.media.tool_media import dedup_tool_result_messages


def _chunk(*ids: str) -> dict:
    return {
        "type": "tool_result",
        "messages": [{"tool_call_id": call_id, "content": f"file {call_id}"} for call_id in ids],
    }


def test_replayed_history_is_dropped_when_the_current_turn_is_known():
    chunk = _chunk("current-call", "old-call-from-history")

    kept = dedup_tool_result_messages(chunk, set(), current_turn_ids={"current-call"})

    assert kept is not None
    assert [m["tool_call_id"] for m in kept["messages"]] == ["current-call"]


def test_only_history_returns_none():
    chunk = _chunk("old-call-from-history")

    assert dedup_tool_result_messages(chunk, set(), current_turn_ids={"current-call"}) is None


def test_without_a_current_turn_whitelist_behaviour_is_unchanged():
    """Control: callers that pass no whitelist keep the previous semantics."""
    chunk = _chunk("a", "b")

    kept = dedup_tool_result_messages(chunk, set())

    assert kept is chunk
    assert [m["tool_call_id"] for m in kept["messages"]] == ["a", "b"]


def test_already_emitted_ids_are_still_skipped():
    chunk = _chunk("current-call")

    assert (
        dedup_tool_result_messages(chunk, {"current-call"}, current_turn_ids={"current-call"})
        is None
    )
