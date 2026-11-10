"""Read pinned legacy state without rewriting a projection or touching checkpoints."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from octop.infra.history.projection import _role, message_inputs
from octop.infra.history.store import HistoryStore

logger = logging.getLogger(__name__)


def _root_checkpoint_ref(thread_id: str, config: dict[str, Any]) -> tuple[str, str]:
    configurable = config.get("configurable") or {}
    checkpoint_id = configurable.get("checkpoint_id")
    if (
        configurable.get("thread_id") != thread_id
        or configurable.get("checkpoint_ns") not in (None, "")
        or not isinstance(checkpoint_id, str)
        or not checkpoint_id
    ):
        raise ValueError("Invalid legacy history checkpoint reference")
    return thread_id, checkpoint_id


async def pin_history_checkpoint(
    harness: Any, thread_id: str, config: dict[str, Any], *, expires_at: float | None = None
) -> None:
    """Pin the exact state before publishing an anchor or a legacy cursor."""
    from octop_memory.core import Memory  # noqa: PLC0415
    from octop_memory.storage.backends.sqlite import SqliteMemoryBackend  # noqa: PLC0415

    ref = _root_checkpoint_ref(thread_id, config)
    checkpointer = getattr(harness, "checkpointer", None)
    if isinstance(checkpointer, Memory) and isinstance(checkpointer.backend, SqliteMemoryBackend):
        from octop_memory.application.checkpoint_maintenance import (
            pin_sqlite_checkpoints,  # noqa: PLC0415
        )

        await asyncio.to_thread(
            pin_sqlite_checkpoints,
            Path(checkpointer.backend._db_path),
            [ref],
            expires_at=expires_at,
        )


def pin_existing_history_checkpoints(
    store: HistoryStore, registry: Any, *, config: Any, paths: Any
) -> None:
    """Register pre-upgrade anchors before any agent can prune a shared store."""
    from octop.infra.agents.memory.backend import open_memory_kwargs  # noqa: PLC0415
    from octop.infra.agents.memory.thread_cleanup import workspace_for_agent_row  # noqa: PLC0415

    by_agent: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for agent_id, thread_id, anchor in store.checkpoint_anchors():
        by_agent[agent_id].append(_root_checkpoint_ref(thread_id, anchor["checkpoint_config"]))

    for agent_id, refs in by_agent.items():
        row = registry.get_row(agent_id)
        if row is None:
            continue
        cfg = registry.get_config(agent_id)
        memory = cfg.get("memory")
        if isinstance(memory, dict) and memory.get("memory_enabled") is False:
            continue
        try:
            _, backend, options = open_memory_kwargs(
                agent_id=agent_id,
                cfg=cfg,
                octop_config=config,
                workspace_dir=workspace_for_agent_row(row, paths=paths),
            )
            if backend == "sqlite" and options is not None:
                _pin_archived_refs(Path(options["db_path"]), agent_id, refs)
        except (OSError, sqlite3.Error):
            logger.warning(
                "Could not register history checkpoint anchors for agent=%s",
                agent_id,
                exc_info=True,
            )


def pin_restored_history_checkpoints(store: HistoryStore, agent_id: str, path: Path) -> None:
    """Reconcile an exclusive agent database before restarting its maintenance."""
    if not store.path.is_file():
        return
    refs = [
        _root_checkpoint_ref(thread_id, anchor["checkpoint_config"])
        for _, thread_id, anchor in store.checkpoint_anchors(agent_id=agent_id)
    ]
    _pin_archived_refs(path, agent_id, refs)


def _pin_archived_refs(path: Path, agent_id: str, refs: list[tuple[str, str]]) -> None:
    from octop_memory.application.checkpoint_maintenance import (
        pin_sqlite_checkpoints,  # noqa: PLC0415
    )

    for thread_id, checkpoint_id in pin_sqlite_checkpoints(path, refs, strict=False):
        logger.warning(
            "Missing history checkpoint anchor agent=%s thread=%s checkpoint=%s",
            agent_id,
            thread_id,
            checkpoint_id,
        )


async def checkpoint_snapshot(
    harness: Any, thread_id: str, anchor: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    import json  # noqa: PLC0415

    config = anchor["checkpoint_config"] if anchor else {"configurable": {"thread_id": thread_id}}
    ref = _root_checkpoint_ref(thread_id, config) if anchor else None
    state = await harness.graph.aget_state(config)
    if ref is not None:
        found = getattr(state, "config", None)
        if (
            not found
            or getattr(state, "created_at", None) is None
            or _root_checkpoint_ref(thread_id, found) != ref
        ):
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
