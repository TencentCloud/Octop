"""Resolve an agent's ``workspace_dir`` (persisted in ``config_json``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.utils.paths import PathLayout


def default_agent_workspace_dir(paths: PathLayout, agent_id: str) -> Path:
    """Octop default layout: ``{OCTOP_HOME}/agents/<agent_id>/`` (mkdir -p)."""
    return paths.ensure_agent_workspace(agent_id)


def workspace_dir_from_config(
    cfg: dict[str, Any] | None,
    *,
    paths: PathLayout,
    agent_id: str,
) -> Path:
    """Return the agent workspace path from config, or the Octop default.

    ``config.workspace_dir`` is written when the expert is created. Older rows
    without the key fall back to :func:`default_agent_workspace_dir`.
    """
    raw = (cfg or {}).get("workspace_dir")
    if isinstance(raw, str) and raw.strip():
        out = Path(raw.strip()).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        return out
    return default_agent_workspace_dir(paths, agent_id)


__all__ = [
    "default_agent_workspace_dir",
    "workspace_dir_from_config",
]
