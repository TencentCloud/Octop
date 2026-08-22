"""Read-only projection of DeepAgents todos from persisted thread state."""

from __future__ import annotations

import logging
from typing import Any, Literal, TypeGuard

logger = logging.getLogger(__name__)

TaskItemStatus = Literal["pending", "in_progress", "completed", "cancelled"]
TaskPlanStatus = Literal["idle", "active", "completed"]


def _is_task_item_status(value: str) -> TypeGuard[TaskItemStatus]:
    return value in {"pending", "in_progress", "completed", "cancelled"}


def _normalize_item(raw: Any, index: int) -> dict[str, str] | None:
    if isinstance(raw, str):
        content = raw.strip()
        status: TaskItemStatus = "pending"
    elif isinstance(raw, dict):
        content = str(
            raw.get("content")
            or raw.get("text")
            or raw.get("title")
            or raw.get("description")
            or ""
        ).strip()
        raw_status = str(raw.get("status") or "pending").strip().lower()
        aliases = {
            "done": "completed",
            "complete": "completed",
            "running": "in_progress",
            "active": "in_progress",
            "canceled": "cancelled",
        }
        normalized = aliases.get(raw_status, raw_status)
        status = normalized if _is_task_item_status(normalized) else "pending"
    else:
        return None
    if not content:
        return None
    item_id = (
        str(raw.get("id") or raw.get("key") or index + 1)
        if isinstance(raw, dict)
        else str(index + 1)
    )
    return {"id": item_id, "content": content, "status": status}


def project_thread_task_state(
    thread_id: str,
    todos: Any,
    *,
    available: bool = True,
) -> dict[str, Any]:
    """Normalize LangGraph ``todos`` into the stable dashboard contract."""
    raw_items = todos if isinstance(todos, list) else []
    items = [
        item
        for index, raw in enumerate(raw_items)
        if (item := _normalize_item(raw, index)) is not None
    ]
    completed = sum(item["status"] == "completed" for item in items)
    active = any(item["status"] in {"pending", "in_progress"} for item in items)
    status: TaskPlanStatus = "active" if active else "completed" if items else "idle"
    return {
        "thread_id": thread_id,
        "available": available,
        "status": status,
        "items": items,
        "completed": completed,
        "total": len(items),
    }


def task_state_from_stream_chunk(thread_id: str, chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Project a harness state frame when it explicitly contains todos."""
    if chunk.get("type") not in {"state_update", "state_snapshot"}:
        return None
    data = chunk.get("data")
    if not isinstance(data, dict) or "todos" not in data:
        return None
    return project_thread_task_state(thread_id, data.get("todos"))


async def read_thread_task_state(
    agent_manager: Any,
    agent_id: str,
    thread_id: str,
) -> dict[str, Any]:
    """Read the current todo list from the live harness checkpointer.

    Agent shutdown makes the live graph unavailable.  That is represented in
    the response instead of turning thread history and the task center into a
    500 response.
    """
    try:
        harness = agent_manager.get_agent(agent_id)
        graph = getattr(harness, "graph", None)
        aget_state = getattr(graph, "aget_state", None)
        if aget_state is None:
            return project_thread_task_state(thread_id, [], available=False)
        state = await aget_state({"configurable": {"thread_id": thread_id}})
        values = getattr(state, "values", None)
        todos = values.get("todos") if isinstance(values, dict) else []
        return project_thread_task_state(thread_id, todos)
    except Exception:
        logger.warning(
            "failed to read task state for agent=%s thread=%s",
            agent_id,
            thread_id,
            exc_info=True,
        )
        return project_thread_task_state(thread_id, [], available=False)


def task_state_fingerprint(state: dict[str, Any]) -> tuple[Any, ...]:
    """Return a compact equality key used to suppress duplicate stream frames."""
    return (
        state.get("available"),
        state.get("status"),
        tuple(
            (item.get("id"), item.get("content"), item.get("status"))
            for item in state.get("items", [])
            if isinstance(item, dict)
        ),
    )
