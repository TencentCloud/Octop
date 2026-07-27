"""Resolve agent memory storage backend for harness-agent / harness-memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.config import OctopConfig
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
            db_path = str(workspace_dir / "memory.sqlite")
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
        return ns, "sqlite", {"db_path": str(workspace_dir / "memory.sqlite")}
    btype = str(spec.get("type") or "sqlite")
    if btype == "postgres":
        return ns, "postgres", {"dsn": spec["dsn"]}
    db_path = spec.get("db_path") or str(workspace_dir / "memory.sqlite")
    return ns, "sqlite", {"db_path": str(db_path)}
