"""Consecutive identical tool-call cap."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from octop.infra.agents.middleware.consecutive_tool_call import (
    ConsecutiveToolCallMiddleware,
    tool_call_signature,
)


def _call(name: str, args: dict[str, object], call_id: str) -> dict[str, object]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _state(*calls: dict[str, object], streak: dict[str, object] | None = None) -> dict[str, object]:
    state: dict[str, object] = {"messages": [AIMessage(content="", tool_calls=list(calls))]}
    if streak is not None:
        state["tool_call_streak"] = streak
    return state


def test_different_calls_do_not_add_up() -> None:
    middleware = ConsecutiveToolCallMiddleware(limit=2)
    first = middleware.after_model(
        _state(_call("read_file", {"path": "a"}, "1")),
        None,
    )
    assert first is not None
    assert "jump_to" not in first
    assert first["tool_call_streak"]["count"] == 1

    second = middleware.after_model(
        _state(
            _call("read_file", {"path": "b"}, "2"),
            streak=first["tool_call_streak"],
        ),
        None,
    )
    assert second is not None
    assert "jump_to" not in second
    assert second["tool_call_streak"]["count"] == 1
    assert second["tool_call_streak"]["signature"] == tool_call_signature(
        _call("read_file", {"path": "b"}, "2")
    )


def test_identical_streak_ends_the_turn_on_the_next_call() -> None:
    middleware = ConsecutiveToolCallMiddleware(limit=2)
    signature = tool_call_signature(_call("search", {"q": "x"}, "1"))
    update = middleware.after_model(
        _state(
            _call("search", {"q": "x"}, "3"),
            streak={"signature": signature, "count": 2},
        ),
        None,
    )
    assert update is not None
    assert update["jump_to"] == "end"
    content = str(update["messages"][-1].content)
    assert "[tool_call_repeat]" in content
    assert "tool: search" in content
    assert "count: 3" in content
    assert "limit: 2" in content
    assert update["messages"][0].status == "error"


def test_reply_without_a_tool_call_resets_the_streak() -> None:
    middleware = ConsecutiveToolCallMiddleware(limit=2)
    update = middleware.after_model(
        {
            "messages": [AIMessage(content="done")],
            "tool_call_streak": {"signature": "search\n{}", "count": 2},
        },
        None,
    )
    assert update == {"tool_call_streak": {"signature": "", "count": 0}}
