"""Environment variables API — backed by ``~/.octop/env`` (inherited by all agents)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Depends

from octop.api.common.env_sync import reload_agents_after_env_change
from octop.api.deps import get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.env_file import (
    apply_env_file_replace,
    env_file_path,
    list_env_items,
    load_env_file,
    save_env_file,
)

router = APIRouter(prefix="/envs", tags=["envs"])

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CAPTCHA_SECRET_KEYS = frozenset({"OCTOP_CAPTCHA_SECRET", "OCTOP_CAPTCHA_CAM_SECRET_KEY"})
_SECRET_SENTINEL = "********"


def _redact_env_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {**item, "value": _SECRET_SENTINEL} if item["key"] in _CAPTCHA_SECRET_KEYS else item
        for item in items
    ]


def _restore_secret_sentinel(cleaned: dict[str, str], previous: dict[str, str]) -> None:
    for key in _CAPTCHA_SECRET_KEYS:
        if cleaned.get(key) != _SECRET_SENTINEL:
            continue
        if key in previous:
            cleaned[key] = previous[key]
        else:
            cleaned.pop(key, None)


@router.get("", summary="List global environment variables")
async def list_envs(
    _: Any = Depends(require_permission("envs")),
    server: Any = Depends(get_server),
) -> list[dict[str, str]]:
    path = env_file_path(server.paths.root)
    return _redact_env_items(list_env_items(path))


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
    _restore_secret_sentinel(cleaned, previous)
    save_env_file(path, cleaned)
    apply_env_file_replace(path, previous=previous)
    reload_agents_after_env_change(server, previous, cleaned)
    return _redact_env_items(list_env_items(path))


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
    reload_agents_after_env_change(server, previous, values)
    return _redact_env_items(list_env_items(path))
