"""Environment variables API — backed by ``~/.octop/env`` (inherited by all agents)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, Body, Depends

from octop.api.deps import get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.env_file import (
    apply_env_file_replace,
    env_file_path,
    list_env_items,
    load_env_file,
    save_env_file,
    search_env_changed,
)

router = APIRouter(prefix="/envs", tags=["envs"])
logger = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _after_env_sync(server: Any, previous: dict[str, str], new: dict[str, str]) -> None:
    """Sync process env; reload agents only when search-tool keys change."""
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    if registry is None:
        return
    invalidate = getattr(registry, "invalidate_mcp_tool_cache", None)
    if callable(invalidate):
        invalidate()
    if not search_env_changed(previous, new):
        return
    reload_all = getattr(registry, "reload_all", None)
    if not callable(reload_all):
        return

    async def _reload() -> None:
        try:
            await reload_all()
        except Exception:
            logger.exception("background agent reload after search env change failed")

    asyncio.create_task(_reload(), name="reload-agents-search-env")


@router.get("", summary="List global environment variables")
async def list_envs(
    _: Any = Depends(require_permission("envs")),
    server: Any = Depends(get_server),
) -> list[dict[str, str]]:
    path = env_file_path(server.paths.root)
    return list_env_items(path)


@router.put(
    "",
    summary="Replace global environment variables",
    description=(
        "Overwrite ~/.octop/env and align the Octop process environment "
        "(including deleting keys removed from the list). Running execute "
        "shells and Docker sandboxes pick up keys on the next command without "
        "an agent reload. Agents reload in the background only when search "
        "API keys (Tavily, Brave, …) change."
    ),
)
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
    previous = load_env_file(path)
    save_env_file(path, cleaned)
    apply_env_file_replace(path, previous=previous)
    _after_env_sync(server, previous, cleaned)
    return list_env_items(path)


@router.delete(
    "/{key}",
    summary="Delete one global environment variable",
    description="Remove a key from ~/.octop/env and the process environment.",
)
async def delete_env(
    key: str,
    _: Any = Depends(require_permission("envs")),
    server: Any = Depends(get_server),
) -> list[dict[str, str]]:
    k = key.strip()
    if not _KEY_RE.match(k):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid env key: {k!r}")
    path = env_file_path(server.paths.root)
    previous = load_env_file(path)
    values = dict(previous)
    values.pop(k, None)
    save_env_file(path, values)
    apply_env_file_replace(path, previous=previous)
    _after_env_sync(server, previous, values)
    return list_env_items(path)
