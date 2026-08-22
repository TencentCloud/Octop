"""Tests for the persisted thread task projection."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents.thread_tasks import (
    project_thread_task_state,
    read_thread_task_state,
    task_state_from_stream_chunk,
)


def test_project_thread_task_state_normalizes_items_and_status() -> None:
    state = project_thread_task_state(
        "thread-1",
        [
            {"content": "Inspect", "status": "done"},
            {"id": "build", "content": "Build", "status": "running"},
            {"content": "  "},
        ],
    )

    assert state == {
        "thread_id": "thread-1",
        "available": True,
        "status": "active",
        "items": [
            {"id": "1", "content": "Inspect", "status": "completed"},
            {"id": "build", "content": "Build", "status": "in_progress"},
        ],
        "completed": 1,
        "total": 2,
    }


def test_stream_projection_only_emits_when_todos_are_explicit() -> None:
    assert (
        task_state_from_stream_chunk(
            "thread-1", {"type": "state_snapshot", "data": {"messages": []}}
        )
        is None
    )

    state = task_state_from_stream_chunk(
        "thread-1",
        {
            "type": "state_update",
            "data": {"todos": [{"content": "Ship", "status": "pending"}]},
        },
    )
    assert state is not None
    assert state["status"] == "active"
    assert state["items"][0]["content"] == "Ship"


@pytest.mark.asyncio
async def test_read_thread_task_state_reads_harness_graph() -> None:
    class Graph:
        async def aget_state(self, config: dict[str, Any]) -> SimpleNamespace:
            assert config == {"configurable": {"thread_id": "thread-1"}}
            return SimpleNamespace(values={"todos": [{"content": "Done", "status": "completed"}]})

    manager = SimpleNamespace(get_agent=lambda _agent_id: SimpleNamespace(graph=Graph()))

    state = await read_thread_task_state(manager, "agent-1", "thread-1")

    assert state["status"] == "completed"
    assert state["completed"] == 1


@pytest.mark.asyncio
async def test_read_thread_task_state_is_unavailable_when_agent_is_stopped() -> None:
    def unavailable(_agent_id: str) -> None:
        raise RuntimeError("stopped")

    state = await read_thread_task_state(
        SimpleNamespace(get_agent=unavailable), "agent-1", "thread-1"
    )

    assert state["available"] is False
    assert state["status"] == "idle"
