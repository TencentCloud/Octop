"""Environment variables API — backed by ``~/.octop/env``."""

from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, Body, Depends

from octop.api.deps import get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.env_file import (
    apply_env_file,
    env_file_path,
    list_env_items,
    load_env_file,
    save_env_file,
)

router = APIRouter(prefix="/envs", tags=["envs"])

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@router.get("")
async def list_envs(
    _: Any = Depends(require_permission("envs")),
    server: Any = Depends(get_server),
) -> list[dict[str, str]]:
    path = env_file_path(server.paths.root)
    return list_env_items(path)


@router.put("")
async def batch_save_envs(
    body: dict[str, str] = Body(...),
    _: Any = Depends(require_permission("envs")),
    server: Any = Depends(get_server),
) -> list[dict[str, str]]:
    cleaned: dict[str, str] = {}
    for key, value in body.items():
        k = key.strip()
        if not k:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "env key cannot be empty")
        if not _KEY_RE.match(k):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid env key: {k!r}")
        cleaned[k] = str(value)
    path = env_file_path(server.paths.root)
    save_env_file(path, cleaned)
    apply_env_file(path)
    return list_env_items(path)


@router.delete("/{key}")
async def delete_env(
    key: str,
    _: Any = Depends(require_permission("envs")),
    server: Any = Depends(get_server),
) -> list[dict[str, str]]:
    k = key.strip()
    if not _KEY_RE.match(k):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid env key: {k!r}")
    path = env_file_path(server.paths.root)
    values = load_env_file(path)
    values.pop(k, None)
    save_env_file(path, values)
    apply_env_file(path)
    os.environ.pop(k, None)
    return list_env_items(path)
