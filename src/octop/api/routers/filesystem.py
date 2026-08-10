"""Host filesystem browsing for dashboard forms (root_dir pickers).

Security notes:
- Authenticated users only (JWT).
- Paths are resolved absolutely; ``..`` / symlinks cannot escape a denylist
  of sensitive pseudo-fs mounts (``/proc``, ``/sys``, ``/dev``, ``/etc``, ``/root`` on POSIX).
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
from octop.infra.utils.bwrap import ensure_bubblewrap
from octop.infra.utils.docker_env import docker_status, ensure_docker
from octop.infra.utils.host_dirs import (
    assert_safe_host_path,
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


@router.get("/dirs")
async def list_host_dirs(
    path: str = Query("/", description="Absolute host directory to list"),
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Single-level directory listing for lazy folder pickers."""
    try:
        entries = await asyncio.to_thread(list_host_subdirs, path)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc
    return {"path": str(assert_safe_host_path(path)), "entries": entries}


@router.post("/probe")
async def probe_host_dir(
    body: ProbeBody,
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Check whether Octop can use *path* as a local backend root_dir."""
    return await asyncio.to_thread(probe_host_root_dir, body.path)


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
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Create a child directory under *path* for root_dir pickers."""
    try:
        return await asyncio.to_thread(
            mkdir_host_subdir,
            body.path,
            base_name=body.base_name,
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc


@router.post("/rename")
async def rename_host_directory(
    body: RenameBody,
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """Rename a host directory (basename only) for root_dir pickers."""
    try:
        return await asyncio.to_thread(rename_host_dir, body.path, body.new_name)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc
