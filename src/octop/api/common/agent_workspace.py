"""Resolve agent ``workspace_dir`` for API handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast


def resolve_agent_workspace_dir(server: Any, agent_id: str) -> Path:
    """Prefer ``config.workspace_dir`` via agent registry; else Octop default layout."""
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    if registry is not None and hasattr(registry, "resolve_workspace_dir"):
        return cast(Path, registry.resolve_workspace_dir(agent_id))
    paths = getattr(server, "paths", None) or server.services.paths
    return cast(Path, paths.ensure_agent_workspace(agent_id))


__all__ = ["resolve_agent_workspace_dir"]
