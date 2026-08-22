"""Host filesystem browsing for dashboard forms (root_dir pickers).

Security notes:
- Authenticated users only (JWT).
- Paths are resolved with ``os.path.realpath`` and must stay under the browse
  tree root (``startswith`` containment — CodeQL-recognized sanitizer).
  A denylist further blocks sensitive mounts (``/proc``, ``/sys``, ``/dev``,
  ``/etc``, ``/root`` on POSIX). The process home is never denied (so uid 0
  with home ``/root`` can use the default picker path).
- All authenticated users may browse from host root ``/`` (denylist still applies).
  The UI default ``root_dir`` remains the process home directory.
- Directory listing is capped and skips unreadable entries.
- Write probe creates a short-lived dotfile only for non-``/`` selections.
- mkdir / rename only allow basename-safe names under already-browsable parents.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from octop.api.deps import current_user
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.utils.bwrap import ensure_bubblewrap
from octop.infra.utils.docker_env import docker_status, ensure_docker
from octop.infra.utils.host_dirs import (
    assert_safe_host_path,
    host_fs_tree_root,
    host_home_dir,
    host_path_text,
    list_host_subdirs,
    mkdir_host_subdir,
    probe_host_root_dir,
    rename_host_dir,
)

router = APIRouter()


class ProbeBody(BaseModel):
    path: str = Field("/", description="Host directory to verify read/write access")


class MkdirBody(BaseModel):
    path: str = Field(..., description="Parent host directory for the new folder")
    base_name: str = Field(
        "New Folder",
        description="Preferred folder name; collisions become 'Name (2)', …",
    )


class RenameBody(BaseModel):
    path: str = Field(..., description="Existing host directory to rename")
    new_name: str = Field(..., description="New basename (no path separators)")


@router.get(
    "/defaults",
    summary="Default root_dir picker bounds for the current user",
)
async def filesystem_defaults(
    _: User = Depends(current_user),
) -> dict[str, Any]:
    """Return the process home path and browse-tree root (host ``/`` on POSIX)."""
    home = host_path_text(host_home_dir())
    return {
        "home": home,
        "default_root_dir": home,
        "allow_outside_home": True,
        "tree_root": host_fs_tree_root(allow_outside_home=True),
    }


@router.get("/dirs")
async def list_host_dirs(
    path: str = Query("/", description="Absolute host directory to list"),
    _: User = Depends(current_user),
) -> dict[str, Any]:
    """Single-level directory listing for lazy folder pickers."""
    try:
        entries = await asyncio.to_thread(list_host_subdirs, path, restrict_to_home=False)
        resolved = assert_safe_host_path(path, restrict_to_home=False)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc
    return {"path": host_path_text(resolved), "entries": entries}


@router.post("/probe")
async def probe_host_dir(
    body: ProbeBody,
    _: User = Depends(current_user),
) -> dict[str, Any]:
    """Check whether Octop can use *path* as a local backend root_dir."""
    return await asyncio.to_thread(
        probe_host_root_dir,
        body.path,
        restrict_to_home=False,
    )


@router.post(
    "/ensure-bwrap",
    summary="Best-effort ensure bubblewrap for scoped root_dir",
)
async def ensure_bwrap(
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Ensure ``bwrap`` is available when saving a non-host-root backend.

    Never fails the HTTP call for missing packages — returns
    ``ready`` / ``installed`` / ``skipped`` / ``degraded`` so the dashboard
    can warn without blocking agent config save.
    """
    return await asyncio.to_thread(ensure_bubblewrap)


@router.get(
    "/docker-status",
    summary="Detect whether Docker CLI/daemon are available",
)
async def get_docker_status(
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Probe Docker without attempting installation.

    Returns ``status`` plus ``install_script`` / ``agent_prompt`` for the UI.
    """
    return await asyncio.to_thread(docker_status, attempt_install=False)


@router.post(
    "/ensure-docker",
    summary="Best-effort ensure Docker Engine for sandbox backends",
)
async def post_ensure_docker(
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Detect Docker; on Linux with passwordless sudo, try package install.

    Never fails the HTTP call for missing packages — returns guidance fields
    (``install_script``, ``agent_prompt``, ``docs_url``) for the dashboard.
    """
    return await asyncio.to_thread(ensure_docker)


@router.post("/mkdir")
async def mkdir_host_dir(
    body: MkdirBody,
    _: User = Depends(current_user),
) -> dict[str, Any]:
    """Create a child directory under *path* for root_dir pickers."""
    try:
        return await asyncio.to_thread(
            mkdir_host_subdir,
            body.path,
            base_name=body.base_name,
            restrict_to_home=False,
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc


@router.post("/rename")
async def rename_host_directory(
    body: RenameBody,
    _: User = Depends(current_user),
) -> dict[str, Any]:
    """Rename a host directory (basename only) for root_dir pickers."""
    try:
        return await asyncio.to_thread(
            rename_host_dir,
            body.path,
            body.new_name,
            restrict_to_home=False,
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc
