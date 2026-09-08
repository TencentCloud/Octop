"""Read pinned legacy state without rewriting a projection or touching checkpoints."""

from __future__ import annotations

from typing import Any

from octop.infra.gateway.process.history_projection import _role, message_inputs


async def checkpoint_snapshot(
    harness: Any, thread_id: str, anchor: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    import json  # noqa: PLC0415

    config = anchor["checkpoint_config"] if anchor else {"configurable": {"thread_id": thread_id}}
    state = await harness.graph.aget_state(config)
    if anchor and (state is None or not getattr(state, "config", None)):
        raise ValueError("The pinned legacy checkpoint is unavailable")
    raw = list((getattr(state, "values", None) or {}).get("messages") or [])
    items = message_inputs(raw)
    if len(items) != len([m for m in raw if _role(m) != "system"]):
        raise ValueError("A legacy message could not be decoded")
    return [json.loads(item.message_json) for item in items], getattr(state, "config", None)


async def checkpoint_wires(
    harness: Any, thread_id: str, anchor: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    wires, _ = await checkpoint_snapshot(harness, thread_id, anchor)
    return wires
