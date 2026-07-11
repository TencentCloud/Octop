"""Host filesystem browsing for dashboard forms (root_dir pickers).

Security notes:
- Authenticated users only (JWT).
- Paths are resolved absolutely; ``..`` / symlinks cannot escape a denylist
  of sensitive pseudo-fs mounts (``/proc``, ``/sys``, ``/dev``, ``/etc``, ``/root`` on POSIX).
- Directory listing is capped and skips unreadable entries.
- Write probe creates a short-lived dotfile only for non-``/`` selections.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from octop.api.deps import current_user
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.host_dirs import (
    assert_safe_host_path,
    list_host_subdirs,
    probe_host_root_dir,
)

router = APIRouter()


class ProbeBody(BaseModel):
    path: str = Field("/", description="Host directory to verify read/write access")


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
