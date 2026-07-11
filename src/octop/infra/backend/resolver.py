"""Resolve agent ``backend`` config (named refs, composite routes)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from octop.infra.backend.adapter import row_to_backend_spec


def default_agent_backend_spec(workspace_dir: Path) -> dict[str, Any]:
    """Harness backend for agents with no explicit ``backend`` in config.

    On POSIX this matches harness ``DEFAULT_BACKEND_SPEC`` (host-rooted virtual
    paths). On Windows ``root_dir='/'`` resolves to the process current-drive
    root, which often differs from the drive hosting ``workspace_dir`` — scope
    the default to the agent workspace instead.
    """
    from harness_agent.backends import DEFAULT_BACKEND_SPEC  # noqa: PLC0415

    if os.name == "nt":
        return {
            "type": "local_shell",
            "root_dir": str(workspace_dir.resolve()),
            "virtual_mode": True,
        }
    return dict(DEFAULT_BACKEND_SPEC)


def resolve_agent_backend_spec(
    spec: Any,
    *,
    repo: Any | None,
) -> Any:
    """Expand ``named`` refs (and composite trees) into harness-ready specs."""
    if spec is None:
        return None
    if not isinstance(spec, dict):
        return spec

    kind = spec.get("type")
    if kind == "named":
        name = spec.get("name")
        if not repo or not name:
            raise ValueError("named backend requires a configured storage backend name")
        row = repo.get_by_name(str(name))
        if row is None:
            raise ValueError(f"storage backend {name!r} not found")
        inner = row_to_backend_spec(row)
        if inner is None:
            raise ValueError(f"storage backend {name!r} is incomplete")
        return resolve_agent_backend_spec(inner, repo=repo)

    if kind == "composite":
        default = spec.get("default")
        if default is None:
            raise ValueError("composite backend requires a default sub-spec")
        routes = spec.get("routes") or {}
        if not isinstance(routes, dict):
            raise ValueError("composite backend routes must be a dict")
        return {
            "type": "composite",
            "default": resolve_agent_backend_spec(default, repo=repo),
            "routes": {
                str(prefix): resolve_agent_backend_spec(sub, repo=repo)
                for prefix, sub in routes.items()
            },
        }

    cleaned = dict(spec)
    if kind not in ("named", "composite") and "name" in cleaned:
        del cleaned["name"]
    return cleaned


def backend_spec_supports_execution(spec: Any) -> bool:
    """True when the backend spec resolves to a sandbox/shell backend.

    deepagents ``FilesystemMiddleware`` rejects filesystem ``permissions`` when
    the backend implements ``SandboxBackendProtocol`` (e.g. ``local_shell``).
    """
    if spec is None:
        return True
    if isinstance(spec, str):
        return spec == "local_shell"
    if not isinstance(spec, dict):
        return False
    kind = spec.get("type")
    if kind == "local_shell":
        return True
    if kind == "composite":
        if backend_spec_supports_execution(spec.get("default")):
            return True
        routes = spec.get("routes")
        if isinstance(routes, dict):
            return any(backend_spec_supports_execution(route) for route in routes.values())
    return False
