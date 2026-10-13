"""LangGraph v2 interrupt projection for dashboard HITL."""

from __future__ import annotations

from octop.infra.gateway.hitl.stream_compat import (
    hitl_events_from_interrupts,
    merge_hitl_projection,
)


def test_hitl_events_from_interrupt_objects() -> None:
    class _Interrupt:
        def __init__(self, value: object) -> None:
            self.value = value

    events = hitl_events_from_interrupts(
        (
            _Interrupt(
                {
                    "action_requests": [
                        {
                            "name": "ask_user_question",
                            "args": {"questions": [{"question": "Go?"}]},
                        }
                    ]
                }
            ),
        )
    )
    assert len(events) == 1
    assert events[0]["type"] == "hitl_required"
    assert events[0]["request"]["action_requests"][0]["name"] == "ask_user_question"


def test_hitl_events_from_interrupt_dicts() -> None:
    events = hitl_events_from_interrupts(
        [
            {
                "id": "abc",
                "value": {
                    "action_requests": [{"name": "execute", "args": {"command": "ls"}}],
                },
            }
        ]
    )
    assert events[0]["request"]["action_requests"][0]["args"]["command"] == "ls"


def test_hitl_events_ignore_empty_envelopes() -> None:
    assert hitl_events_from_interrupts([{"id": "x", "value": {"raw": "nope"}}]) == []
    assert hitl_events_from_interrupts(None) == []


def test_merge_replaces_empty_hitl_required_from_interrupts() -> None:
    events = merge_hitl_projection(
        [{"type": "hitl_required", "request": {"id": "int-1", "value": {}}}],
        [
            {
                "id": "int-1",
                "value": {
                    "action_requests": [
                        {"name": "ask_user_question", "args": {"questions": [{"question": "Go?"}]}}
                    ]
                },
            }
        ],
    )
    assert len(events) == 1
    assert events[0]["request"]["action_requests"][0]["name"] == "ask_user_question"


def test_merge_keeps_actionable_hitl_required() -> None:
    existing = {
        "type": "hitl_required",
        "request": {"action_requests": [{"name": "execute", "args": {"command": "ls"}}]},
    }
    events = merge_hitl_projection(
        [existing],
        [{"value": {"action_requests": [{"name": "ask_user_question", "args": {}}]}}],
    )
    assert events == [existing]
