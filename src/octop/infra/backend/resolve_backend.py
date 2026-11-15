"""Resolve harness backend specs, including Octop-owned types.

``tos`` is not a harness builtin. It is replaced with a :class:`TOSBackend`
instance before ``resolve_backend`` runs, including inside composite routes.
Missing OpenSandbox filesystem helpers are installed on the class first so
bootstrap, delete, and rename work on the pinned harness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.backend.opensandbox_mkdir import install_opensandbox_fs
from octop.infra.backend.tos_backend import tos_backend_from_spec


def materialize_octop_specs(spec: Any) -> Any:
    """Replace ``type=tos`` nodes with live backends. Other specs pass through."""
    if not isinstance(spec, dict):
        return spec
    kind = str(spec.get("type") or "").lower()
    if kind == "tos":
        return tos_backend_from_spec(spec)
    if kind != "composite":
        return spec
    out = dict(spec)
    if "default" in out:
        out["default"] = materialize_octop_specs(out.get("default"))
    routes = out.get("routes")
    if isinstance(routes, dict):
        out["routes"] = {
            str(prefix): materialize_octop_specs(sub) for prefix, sub in routes.items()
        }
    return out


def resolve_octop_backend(
    spec: Any,
    *,
    workspace_dir: str | Path | None = None,
    system_files_path: str = "",
) -> Any:
    """Harness ``resolve_backend``, after Octop spec materialization."""
    install_opensandbox_fs()
    from octop_harness.backends import resolve_backend

    return resolve_backend(
        materialize_octop_specs(spec),
        workspace_dir=workspace_dir,
        system_files_path=system_files_path,
    )
