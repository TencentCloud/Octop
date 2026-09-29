"""Resolve agent memory storage backend for octop-harness / octop-memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.config import OctopConfig
from octop.infra.agents.workspace.dir import host_system_dir
from octop.infra.errors import ErrorCode, OctopError

# ``agent_{agent_id}`` is the private namespace the harness itself uses
# (``infra/agents/manager.py · _memory_namespace``); ``project_{project_id}`` is
# the project-owned namespace fixed by the project-memory design (D14);
# ``team_{team_agent_id}`` is the namespace shared by a team layer (T-42).
_AGENT_NS_PREFIX = "agent_"
_PROJECT_NS_PREFIX = "project_"
_TEAM_NS_PREFIX = "team_"


def agent_memory_namespace(agent_id: str) -> str:
    """Return the private memory namespace of ``agent_id`` (the default)."""
    return f"{_AGENT_NS_PREFIX}{agent_id}"


def project_memory_namespace(project_id: str) -> str:
    """Return the memory namespace owned by a project (``project_{project_id}``).

    Mirrors ``infra/db/repos/projects.py · project_memory_namespace`` (the
    writer of ``projects.memory_namespace``); ``tests/unit/agents/
    test_memory_backend.py`` pins the two together so the convention cannot drift.
    """
    return f"{_PROJECT_NS_PREFIX}{project_id}"


def team_memory_namespace(team_agent_id: str) -> str:
    """Return the memory namespace shared by a team layer (``team_{id}``).

    The third isolation axis, spelled here next to ``agent_`` and ``project_`` so
    that no module defines its own namespace convention. ``memory/multi_ns.py``
    recalls this layer and re-exports this helper instead of building the name.
    """
    return f"{_TEAM_NS_PREFIX}{team_agent_id}"


def resolve_project_namespace(*, memory_namespace: str | None, project_id: str) -> str:
    """Return the namespace to hand to :func:`open_memory_kwargs` for a project.

    ``projects.memory_namespace`` is the single authority: whenever the column
    carries a value it wins, so a renamed namespace is honoured without touching
    callers. The ``project_{project_id}`` convention is only the fallback for a
    caller that holds a project id but no row.
    """
    return memory_namespace or project_memory_namespace(project_id)


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
    namespace: str | None = None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Return ``(namespace, backend_type, backend_config)`` for ``Memory(...)``.

    ``namespace`` overrides the default private namespace ``agent_{agent_id}``
    with an explicit one — project memory passes ``project_{project_id}``, see
    :func:`resolve_project_namespace`. ``None`` keeps the pre-existing
    behaviour, so agent-private memory is unchanged.

    The override only changes which namespace is handed to ``Memory``. It must
    never change the agent's ``HarnessAgentConfig(name=...)``: that one stays
    ``agent_{agent_id}``, otherwise the agent would lose its private memory.
    """
    ns = agent_memory_namespace(agent_id) if namespace is None else namespace
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
