"""Bounded workspace file index for chat ``@`` mentions.

The composer used to glob ``**/*query*`` on every keystroke. Mention lookup
only needs names, so this module asks ``BackendWorkspace.als`` once per
directory, skips dependency and system trees, and stops at a cap. Results are
cached briefly per workspace object. Path rules stay inside ``BackendWorkspace``.
"""

from __future__ import annotations

import asyncio
import time
import weakref
from collections import deque
from collections.abc import Iterable
from typing import Any

from octop.infra.backend.tree_listing import is_listing_self

# Keep in step with ``SKIP_SEGMENTS`` in ``dashboard/src/pages/Chat/utils/fileMention.ts``.
MENTION_SKIP_DIRS = frozenset(
    {
        ".octop",
        ".octop-auth",
        "_builtin_skills",
        "node_modules",
        ".git",
        ".venv",
        "__pycache__",
        "inbound",
        "outbound",
    }
)

MENTION_INDEX_LIMIT = 4000
_MAX_LISTED_DIRS = 800
_CACHE_TTL_S = 30.0

# (monotonic time, paths, limit, truncated)
_CacheEntry = tuple[float, tuple[str, ...], int, bool]
_cache: weakref.WeakKeyDictionary[Any, _CacheEntry] = weakref.WeakKeyDictionary()
_inflight: weakref.WeakKeyDictionary[Any, tuple[int, asyncio.Task[tuple[list[str], bool]]]] = (
    weakref.WeakKeyDictionary()
)


def clear_mention_index_cache() -> None:
    _cache.clear()
    _inflight.clear()


def _skipped(rel: str) -> bool:
    return any(part in MENTION_SKIP_DIRS or part == ".." for part in rel.split("/"))


def _entry_path_and_dir(item: Any) -> tuple[str, bool]:
    if isinstance(item, dict):
        raw = str(item.get("path") or "")
        is_dir = bool(item.get("is_dir"))
    else:
        raw = str(getattr(item, "path", "") or "")
        is_dir = bool(getattr(item, "is_dir", False))
    text = raw.replace("\\", "/").strip()
    if text.endswith("/"):
        is_dir = True
    return text, is_dir


def _child_rel(parent: str, entry_path: str) -> str:
    """Re-anchor one listing row under *parent*.

    ``BackendWorkspace.als`` may return a basename or a workspace-relative path.
    Only the final segment is the child name.
    """
    name = entry_path.rstrip("/").rsplit("/", 1)[-1]
    base = parent.strip().replace("\\", "/").rstrip("/")
    if base in {"", "."}:
        return name
    return f"{base}/{name}" if name else base


def _rows_from_listing(entries: Iterable[Any], *, parent: str) -> tuple[list[str], list[str]]:
    files: list[str] = []
    dirs: list[str] = []
    for item in entries:
        raw, is_dir = _entry_path_and_dir(item)
        if not raw or is_listing_self(raw, parent=parent):
            continue
        rel = _child_rel(parent, raw)
        if not rel or _skipped(rel):
            continue
        if is_dir:
            dirs.append(rel)
        else:
            files.append(rel)
    return files, dirs


async def list_workspace_mention_paths(
    workspace: Any,
    *,
    limit: int = MENTION_INDEX_LIMIT,
    max_dirs: int = _MAX_LISTED_DIRS,
) -> tuple[list[str], bool]:
    """List via ``workspace.als``, pruning the same trees. Never walks the host itself."""
    als = getattr(workspace, "als", None)
    if als is None or limit < 1 or max_dirs < 1:
        return [], False
    paths: list[str] = []
    seen: set[str] = set()
    truncated = False
    queue: deque[str] = deque(["."])
    listed = 0
    while queue:
        if listed >= max_dirs:
            truncated = True
            break
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        listed += 1
        result = await als(current)
        if result is None:
            continue
        entries = getattr(result, "entries", None) or []
        files, dirs = _rows_from_listing(entries, parent=current)
        for rel in files:
            paths.append(rel)
            if len(paths) >= limit:
                truncated = True
                break
        if truncated:
            break
        for rel in dirs:
            if rel not in seen:
                queue.append(rel)
    paths.sort()
    return paths, truncated


async def _load_and_store(
    workspace: Any,
    *,
    limit: int,
) -> tuple[list[str], bool]:
    task = asyncio.current_task()
    try:
        paths, truncated = await list_workspace_mention_paths(workspace, limit=limit)
    finally:
        slot = _inflight.get(workspace)
        if slot is not None and slot[1] is task:
            _inflight.pop(workspace, None)
    _cache[workspace] = (time.monotonic(), tuple(paths), limit, truncated)
    return paths, truncated


async def collect_mention_paths(
    workspace: Any,
    *,
    limit: int = MENTION_INDEX_LIMIT,
) -> tuple[list[str], bool]:
    """Workspace-relative file paths for one ``@`` menu.

    Repeated calls for the same workspace object reuse a short-lived cache.
    """
    now = time.monotonic()
    cached = _cache.get(workspace)
    if cached is not None and cached[2] == limit and now - cached[0] < _CACHE_TTL_S:
        return list(cached[1]), cached[3]
    slot = _inflight.get(workspace)
    if slot is not None and slot[0] == limit:
        task = slot[1]
    else:
        task = asyncio.create_task(_load_and_store(workspace, limit=limit))
        _inflight[workspace] = (limit, task)
    # A cancelled HTTP request must not cancel the shared walk.
    return await asyncio.shield(task)


__all__ = [
    "MENTION_INDEX_LIMIT",
    "MENTION_SKIP_DIRS",
    "clear_mention_index_cache",
    "collect_mention_paths",
    "list_workspace_mention_paths",
]
