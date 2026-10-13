"""Read both formats without creating or repairing legacy records."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from octop.infra.history.legacy import checkpoint_snapshot, checkpoint_wires
from octop.infra.history.service import HistoryArchive


async def read_page(
    archive: HistoryArchive,
    registry: Any,
    agent_id: str,
    thread_id: str,
    *,
    limit: int,
    offset: int = 0,
    cursor: str | None = None,
) -> dict[str, Any]:
    async def legacy(anchor: dict[str, Any]) -> list[Any]:
        return await checkpoint_wires(registry.get_agent(agent_id), thread_id, anchor)

    boundary = None
    if cursor and cursor.startswith("legacy:"):
        try:
            boundary = json.loads(base64.urlsafe_b64decode(cursor[7:]))
            if boundary["thread"] != thread_id or not isinstance(boundary["before"], int):
                raise ValueError("Invalid legacy cursor")
            if boundary["source"] not in ("projection", "checkpoint"):
                raise ValueError("Invalid legacy source")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("Invalid legacy cursor") from exc
    segments = await asyncio.to_thread(archive.store.segments, thread_id)
    if boundary is None and segments:
        return await archive.page(
            thread_id, limit=limit, cursor=cursor, offset=offset, legacy_reader=legacy
        )
    if cursor and boundary is None:
        raise ValueError("History cursor has no corresponding segment")
    source = (
        boundary["source"]
        if boundary
        else (
            "projection"
            if await asyncio.to_thread(archive.messages.projection_status, thread_id) == "ready"
            else "checkpoint"
        )
    )
    anchor = None
    if source == "projection":
        if boundary:
            descending = await asyncio.to_thread(
                archive.messages.range_page, thread_id, 0, boundary["before"] - 1, limit + 1
            )
            rows, has_more = list(reversed(descending[:limit])), len(descending) > limit
        else:
            rows, has_more = await asyncio.to_thread(
                archive.messages.page, thread_id, limit=limit, offset=offset
            )
        wires = [json.loads(row.message_json) for row in rows]
        before = rows[0].seq if rows else 0
    else:
        if boundary:
            # Never trust a cursor to select a different thread's checkpoint.
            checkpoint_id = boundary.get("checkpoint_id")
            if not isinstance(checkpoint_id, str) or not checkpoint_id:
                raise ValueError("Invalid pinned checkpoint")
            anchor = {
                "checkpoint_config": {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": checkpoint_id,
                        "checkpoint_ns": "",
                    }
                }
            }
        raw, config = await checkpoint_snapshot(registry.get_agent(agent_id), thread_id, anchor)
        stop = min(len(raw), boundary["before"]) if boundary else max(0, len(raw) - offset)
        start = max(0, stop - limit)
        wires, has_more, before = raw[start:stop], start > 0, start
        checkpoint_id = (config or {}).get("configurable", {}).get("checkpoint_id")
        if has_more and not checkpoint_id:
            raise ValueError("Cannot pin the legacy history page")
    next_cursor = None
    if has_more:
        value = {"thread": thread_id, "source": source, "before": before}
        if source == "checkpoint":
            value["checkpoint_id"] = checkpoint_id
        next_cursor = "legacy:" + base64.urlsafe_b64encode(json.dumps(value).encode()).decode()
    return {"messages": wires, "has_more": has_more, "next_cursor": next_cursor}


async def export_messages(
    archive: HistoryArchive, registry: Any, agent_id: str, thread_id: str
) -> list[Any]:
    page = await read_page(archive, registry, agent_id, thread_id, limit=1000)
    messages = page["messages"]
    while page["has_more"]:
        page = await read_page(
            archive,
            registry,
            agent_id,
            thread_id,
            limit=1000,
            offset=len(messages),
            cursor=page["next_cursor"],
        )
        messages = [*page["messages"], *messages]
    return messages  # type: ignore[no-any-return]
