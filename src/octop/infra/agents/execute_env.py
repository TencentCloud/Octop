"""Inject platform execute defaults into harness backend specs.

Global admin env (``~/.octop/env``) and workspace ``.env`` are merged at
**execute** time inside harness (``inherit_env`` / ``environment_file`` /
``BackendWorkspace`` reader) — not snapshotted here.

``OCTOP_AUTH_DIR`` / ``OCTOP_SKILLS_DIR`` use agent-facing paths when the
backend is scoped (bwrap / virtual rootfs), so skill scripts resolve the same
locations inside the jail. Host paths are still mkdir'd for Octop host ops.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.agents.workspace_dir import (
    agent_auth_dir,
    agent_facing_workspace_dir_from_config,
    agent_facing_workspace_root,
    host_system_dir,
    join_agent_facing,
    local_backend_root_dir,
    system_files_path_from_config,
    uses_scoped_workspace_default,
)
from octop.infra.db.repos.agents import AgentRow
from octop.infra.utils.paths import PathLayout

_EXECUTE_BACKEND_KINDS = frozenset({"local_shell", "docker"})


def _agent_facing_auth_and_skills(
    *,
    workspace_dir: Path,
    cfg: dict[str, Any] | None,
    auth_host: Path,
    skills_host: Path,
) -> tuple[str, str]:
    """Return execute-visible auth/skills paths (agent-facing when scoped)."""
    facing = agent_facing_workspace_dir_from_config(cfg)
    if not facing:
        facing = agent_facing_workspace_root(
            workspace_dir,
            root_dir=local_backend_root_dir(cfg),
            virtual_mode=True,
        )
    scoped = uses_scoped_workspace_default(cfg) or facing.startswith("/.octop/")
    if not scoped:
        return str(auth_host), str(skills_host)

    prefix = system_files_path_from_config(cfg)
    # Match agent_auth_dir legacy preference when tokens already live at root.
    if auth_host.name == ".octop-auth":
        auth_env = join_agent_facing(facing, ".octop-auth")
    elif prefix:
        auth_env = join_agent_facing(facing, prefix, "auth")
    else:
        auth_env = join_agent_facing(facing, ".octop-auth")

    if prefix:
        skills_env = join_agent_facing(facing, prefix, "skills")
    else:
        skills_env = join_agent_facing(facing, "skills")
    return auth_env, skills_env


def agent_execute_env_defaults(
    *,
    paths: PathLayout,
    agent_id: str,
    workspace_dir: Path,
    cfg: dict[str, Any] | None = None,
) -> dict[str, str]:
    auth_dir = agent_auth_dir(workspace_dir, cfg)
    auth_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = host_system_dir(workspace_dir, cfg) / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    auth_env, skills_env = _agent_facing_auth_and_skills(
        workspace_dir=workspace_dir,
        cfg=cfg,
        auth_host=auth_dir,
        skills_host=skills_dir,
    )
    return {
        "OCTOP_AGENT_ID": agent_id,
        "OCTOP_AUTH_DIR": auth_env,
        "OCTOP_HOME": str(paths.root),
        "OCTOP_SKILLS_DIR": skills_env,
    }


def inject_agent_execute_env(
    backend: Any,
    *,
    paths: PathLayout,
    row: AgentRow,
    workspace_dir: Path,
    cfg: dict[str, Any] | None = None,
) -> Any:
    """Fold Octop platform identity into shell/sandbox backend specs."""
    if not isinstance(backend, dict):
        return backend

    kind = str(backend.get("type") or "").lower()
    if kind == "composite":
        default = backend.get("default")
        if not isinstance(default, dict):
            return backend
        injected = inject_agent_execute_env(
            default,
            paths=paths,
            row=row,
            workspace_dir=workspace_dir,
            cfg=cfg,
        )
        if injected is default:
            return backend
        return {**backend, "default": injected}

    if kind not in _EXECUTE_BACKEND_KINDS:
        return backend

    extra: dict[str, str] = {str(k): str(v) for k, v in dict(backend.get("env") or {}).items()}
    extra.update(
        agent_execute_env_defaults(
            paths=paths,
            agent_id=row.agent_id,
            workspace_dir=workspace_dir,
            cfg=cfg,
        )
    )

    out = dict(backend)
    out["env"] = extra
    if kind == "local_shell":
        out.setdefault("inherit_env", True)
    return out
