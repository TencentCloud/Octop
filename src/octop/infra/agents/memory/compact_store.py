"""Run ``VACUUM`` / ``VACUUM FULL`` against one live agent's memory store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.i18n import tr
from octop.infra.errors import OctopError


@dataclass(frozen=True)
class StoreCompactResult:
    """Sizes are the whole database file, measured before and after compact."""

    bytes_before: int | None
    bytes_after: int | None
    tables_done: int
    tables_skipped: tuple[str, ...]


def compact_agent_store(
    agent_manager: Any, agent_id: str, *, locale: str = "en"
) -> StoreCompactResult:
    """Rebuild the agent's memory database so deleted rows can leave the file.

    SQLite runs ``VACUUM``. Postgres runs ``VACUUM FULL`` on the shared
    checkpoint tables for that database, which blocks every agent using it.
    The agent must be loaded and idle.
    """
    if agent_manager.is_agent_active(agent_id):
        raise ValueError(tr("slash.memory.compact_busy", locale))
    try:
        agent = agent_manager.get_agent(agent_id)
    except OctopError as exc:
        raise ValueError(tr("slash.memory.compact_not_running", locale)) from exc
    memory = getattr(getattr(agent, "_memory_runtime", None), "memory", None)
    if memory is None:
        raise ValueError(tr("slash.memory.compact_no_memory", locale))
    from octop_memory.pipeline.lifecycle.vacuum import compact_vacuum

    stats = compact_vacuum(memory)
    skipped = tuple(item.table for item in stats.tables if item.skipped_reason)
    done = sum(1 for item in stats.tables if not item.skipped_reason)
    return StoreCompactResult(
        bytes_before=stats.file_size_before,
        bytes_after=stats.file_size_after,
        tables_done=done,
        tables_skipped=skipped,
    )
