"""Resolve agent memory storage backend for harness-agent / harness-memory."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from octop.config import OctopConfig
from octop.infra.agents.workspace_dir import host_system_dir
from octop.infra.errors import ErrorCode, OctopError


def memory_backend_from_agent_config(
    cfg: dict[str, Any],
    *,
    octop_config: OctopConfig,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Return HarnessAgentConfig kwargs for memory storage (may be empty).

    Recognized ``config_json.memory.backend`` shapes:

    * omitted / null → empty on SQLite control plane (harness default
      ``memory.sqlite``); on PostgreSQL control plane, default to the same
      DSN with per-agent schema (``use_control_plane_dsn``)
    * ``{"type": "sqlite", "db_path": "..."}`` (db_path optional)
    * ``{"type": "postgres", "dsn": "..."}``
    * ``{"type": "postgres", "use_control_plane_dsn": true}``
    """
    mem = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    backend = mem.get("backend") if isinstance(mem, dict) else None
    if backend is None:
        if octop_config.database.is_postgresql:
            return {
                "memory_backend": {
                    "type": "postgres",
                    "dsn": octop_config.database.postgresql_conninfo(),
                }
            }
        return {}
    if not isinstance(backend, dict):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "memory.backend must be an object")

    btype = str(backend.get("type") or "sqlite").strip().lower()
    if btype == "sqlite":
        db_path = backend.get("db_path")
        if not db_path and workspace_dir is not None:
            db_path = str(host_system_dir(workspace_dir, cfg) / "memory.sqlite")
        spec: dict[str, Any] = {"type": "sqlite"}
        if db_path:
            spec["db_path"] = str(db_path)
        return {"memory_backend": spec}

    if btype == "postgres":
        dsn = backend.get("dsn")
        if backend.get("use_control_plane_dsn") or not dsn:
            if not octop_config.database.is_postgresql:
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "memory.backend use_control_plane_dsn requires postgresql control plane",
                )
            dsn = octop_config.database.postgresql_conninfo()
        return {"memory_backend": {"type": "postgres", "dsn": str(dsn)}}

    raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unsupported memory.backend.type: {btype!r}")


def open_memory_kwargs(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> tuple[str, str, dict[str, Any] | None]:
    """Return ``(namespace, backend_type, backend_config)`` for ``Memory(...)``."""
    ns = f"agent_{agent_id}"
    resolved = memory_backend_from_agent_config(
        cfg, octop_config=octop_config, workspace_dir=workspace_dir
    )
    spec = resolved.get("memory_backend")
    if not isinstance(spec, dict):
        return ns, "sqlite", {"db_path": str(host_system_dir(workspace_dir, cfg) / "memory.sqlite")}
    btype = str(spec.get("type") or "sqlite")
    if btype == "postgres":
        return ns, "postgres", {"dsn": spec["dsn"]}
    db_path = spec.get("db_path") or str(host_system_dir(workspace_dir, cfg) / "memory.sqlite")
    return ns, "sqlite", {"db_path": str(db_path)}


async def delete_thread_from_storage(
    *,
    agent_id: str,
    thread_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> bool:
    """Delete persisted checkpoint data without requiring a running agent.

    Memory-enabled agents use ``harness-memory`` as their LangGraph
    checkpointer. Agents with memory explicitly disabled fall back to the
    standalone ``checkpoints.sqlite`` created by ``harness-agent``.

    Returns ``False`` only when the local SQLite store does not exist, which
    means there is no persisted checkpoint data to remove.
    """
    raw_memory = cfg.get("memory")
    memory_cfg: dict[str, Any] = raw_memory if isinstance(raw_memory, dict) else {}
    memory_enabled = memory_cfg.get("memory_enabled", True) is not False

    if memory_enabled:
        namespace, backend, backend_config = open_memory_kwargs(
            agent_id=agent_id,
            cfg=cfg,
            octop_config=octop_config,
            workspace_dir=workspace_dir,
        )
        if backend == "sqlite":
            db_path = Path((backend_config or {}).get("db_path") or "")
            if not db_path.exists():
                return False

        from harness_agent.memory.store import close_memory_resources  # noqa: PLC0415
        from harness_memory import Memory  # noqa: PLC0415

        memory = Memory(
            namespace=namespace,
            backend=backend,
            backend_config=backend_config,
        )
        try:
            await memory.adelete_thread(thread_id)
        finally:
            await asyncio.to_thread(close_memory_resources, memory)
        return True

    checkpoint_path = host_system_dir(workspace_dir, cfg) / "checkpoints.sqlite"
    if not checkpoint_path.exists():
        return False

    import aiosqlite  # noqa: PLC0415
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: PLC0415

    conn = await aiosqlite.connect(str(checkpoint_path))
    try:
        await AsyncSqliteSaver(conn).adelete_thread(thread_id)
    finally:
        await conn.close()
    return True
