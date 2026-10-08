from __future__ import annotations

from octop.infra.gateway.process.file_delivery import FileDeliveryTracker


def test_file_failure_remains_incomplete_without_follow_up_write() -> None:
    tracker = FileDeliveryTracker()
    tracker.observe({"type": "tool_call_chunk", "id": "c1", "name": "edit_file"})
    tracker.observe(
        {
            "type": "tool_result",
            "messages": [{"tool_call_id": "c1", "status": "error"}],
        }
    )
    assert tracker.incomplete


def test_successful_follow_up_file_write_resolves_failure() -> None:
    tracker = FileDeliveryTracker()
    tracker.observe({"type": "tool_call_chunk", "id": "c1", "name": "edit_file"})
    tracker.observe(
        {
            "type": "tool_result",
            "messages": [{"tool_call_id": "c1", "status": "error"}],
        }
    )
    tracker.observe({"type": "tool_call_chunk", "id": "c2", "name": "write_file"})
    tracker.observe(
        {
            "type": "tool_result",
            "messages": [{"tool_call_id": "c2", "status": "success"}],
        }
    )
    assert not tracker.incomplete


def test_non_file_tool_error_does_not_trigger_guard() -> None:
    tracker = FileDeliveryTracker()
    tracker.observe({"type": "tool_call_chunk", "id": "c1", "name": "execute"})
    tracker.observe(
        {
            "type": "tool_result",
            "messages": [{"tool_call_id": "c1", "status": "error"}],
        }
    )
    assert not tracker.incomplete
