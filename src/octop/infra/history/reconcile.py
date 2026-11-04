"""Resolve cached user turns by identity, independently of pagination."""

from __future__ import annotations

import asyncio
from typing import Any

from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.history.legacy import checkpoint_wires
from octop.infra.history.ordering import message_order
from octop.infra.history.service import HistoryArchive


async def reconcile_user_messages(
    archive: HistoryArchive | None,
    repo: ThreadMessageRepo,
    registry: Any,
    agent_id: str,
    thread_id: str,
    message_ids: list[str],
    *,
    turn_active: bool,
) -> dict[str, Any]:
    receipts: dict[str, Any] = {
        mid: {"state": "unknown", "persisted": False} for mid in message_ids
    }
    segments = await asyncio.to_thread(archive.store.segments, thread_id) if archive else []
    if archive:
        receipts.update(
            await asyncio.to_thread(archive.store.user_message_positions, thread_id, message_ids)
        )
    missing = [mid for mid in message_ids if receipts[mid]["state"] == "unknown"]
    rows = await asyncio.to_thread(repo.find_by_ids, thread_id, missing)
    for row in rows:
        if row.role not in ("human", "user") or row.message_id is None:
            continue
        segment = next(
            (
                s
                for s in segments
                if s["format"] == "legacy"
                and not s["anchor"]
                and s["legacy_start"] < row.seq
                and (s["legacy_end"] is None or row.seq <= s["legacy_end"])
            ),
            None,
        )
        if segments and segment is None:
            continue
        receipts[row.message_id] = {
            "state": "stored",
            "server_order": message_order(segment, segments[0]["id"], row.seq)
            if segment
            else [0, row.seq],
            "persisted": not turn_active,
        }
    # Pinned legacy checkpoints do not have the v2 metadata index. Only read
    # those when an actual cache needs reconciliation, never on every page load.
    unresolved = {mid for mid in message_ids if receipts[mid]["state"] == "unknown"}
    anchors = [s for s in segments if s["format"] == "legacy" and s["anchor"]]
    if (
        unresolved
        and not turn_active
        and (
            anchors
            or (
                not segments
                and await asyncio.to_thread(repo.projection_status, thread_id) != "ready"
            )
        )
    ):
        import json  # noqa: PLC0415

        checkpoint_segments: list[dict[str, Any] | None] = list(anchors) or [None]
        for segment in checkpoint_segments:
            anchor = json.loads(segment["anchor"]) if segment else None
            wires = await checkpoint_wires(registry.get_agent(agent_id), thread_id, anchor)
            for index, wire in enumerate(wires):
                data = wire.get("data", {})
                mid = data.get("id")
                if mid in unresolved and wire.get("type") in ("human", "user"):
                    receipts[mid] = {
                        "state": "stored",
                        "server_order": message_order(segment, segments[0]["id"], index)
                        if segment
                        else [0, index + 1],
                        "persisted": bool(segment),
                    }
    return receipts
