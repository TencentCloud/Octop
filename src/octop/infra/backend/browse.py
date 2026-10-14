"""List and read files on a configured storage backend (harness ``als`` / download)."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from octop_harness.backends import resolve_backend
from octop_harness.backends.storage_errors import (
    ClassifiedStorageError,
    classify_probe_exception,
    classify_storage_error,
)

from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.backend.compat import adapt_backend_protocol
from octop.infra.backend.tree_listing import dedupe_tree_rows
from octop.infra.db.repos.backends import BackendRow

TEXT_PREVIEW_LIMIT = 10_000_000
PREVIEW_BYTE_LIMIT = 32 * 1024 * 1024
DOWNLOAD_BYTE_LIMIT = 100 * 1024 * 1024
_SESSION_IDLE_SEC = 120.0
_BROWSE_WORKSPACE_ATTR = "_octop_browse_workspace"


class StorageBrowseError(ValueError):
    """Listing / read failed; *classified* is the user-facing reason."""

    def __init__(self, classified: ClassifiedStorageError) -> None:
        super().__init__(classified.message)
        self.classified = classified


@dataclass
class _BrowseSession:
    backend_id: int
    backend: Any
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)


_sessions: dict[int, _BrowseSession] = {}
_sessions_guard = asyncio.Lock()


def resolve_storage_backend(row: BackendRow) -> Any:
    """Instantiate a harness backend for *row* (ephemeral workspace dir)."""
    spec = row_to_backend_spec(row)
    if spec is None:
        raise ValueError("configuration incomplete")
    workspace = tempfile.mkdtemp(prefix="octop-storage-browse-")
    try:
        backend = adapt_backend_protocol(resolve_backend(spec, workspace_dir=workspace))
    except ValueError:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(workspace, ignore_errors=True)
        # ImportError (missing extra), RuntimeError (image/pull), DockerException, …
        raise ValueError(str(exc)) from exc
    setattr(backend, _BROWSE_WORKSPACE_ATTR, workspace)
    return backend


def _close_backend(backend: Any) -> None:
    """Best-effort close for backends that own external resources (e.g. Docker)."""
    close = getattr(backend, "close", None)
    if callable(close):
        with contextlib.suppress(Exception):
            close()


def _dispose_backend(backend: Any) -> None:
    _close_backend(backend)
    workspace = getattr(backend, _BROWSE_WORKSPACE_ATTR, None)
    if workspace:
        shutil.rmtree(workspace, ignore_errors=True)


def _dispose_session(session: _BrowseSession) -> None:
    _dispose_backend(session.backend)


def dispose_all_browse_sessions() -> None:
    """Drop every cached browse handle (tests / process shutdown)."""
    sessions = list(_sessions.values())
    _sessions.clear()
    for session in sessions:
        _dispose_session(session)


def normalize_browse_path(path: str) -> str:
    """Workspace-style ``/a/b`` path; reject ``..`` escapes."""
    raw = (path or "").strip() or "/"
    parts: list[str] = []
    for part in raw.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("invalid path")
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def _download_row_bytes(result: Any) -> bytes | None:
    err = getattr(result, "error", None)
    if err:
        return None
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        err = result.get("error")
        if err:
            return None
        content = result.get("content")
    if content is None:
        return None
    if isinstance(content, str):
        return content.encode("utf-8")
    return bytes(content)


def _download_row_error(result: Any) -> str | None:
    if result is None:
        return "file_not_found"
    err = getattr(result, "error", None)
    if err:
        return str(err)
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])
    return None


def _too_large(preview: bool) -> StorageBrowseError:
    if preview:
        message = "File is too large to preview."
    else:
        message = "File is too large to download in the browser."
    return StorageBrowseError(
        ClassifiedStorageError(message=message, message_key="browse_too_large"),
    )


async def acquire_browse_session(row: BackendRow) -> _BrowseSession:
    """Reuse one harness backend for a backend id until idle or released."""
    now = time.monotonic()
    async with _sessions_guard:
        existing = _sessions.get(row.id)
        if existing is not None and now - existing.last_used < _SESSION_IDLE_SEC:
            existing.last_used = now
            return existing
        stale = _sessions.pop(row.id, None)
    if stale is not None:
        _dispose_session(stale)
    try:
        backend = await asyncio.to_thread(resolve_storage_backend, row)
    except ValueError as exc:
        raise StorageBrowseError(classify_probe_exception(exc)) from exc
    created = _BrowseSession(backend_id=row.id, backend=backend)
    async with _sessions_guard:
        raced = _sessions.get(row.id)
        if raced is not None:
            _dispose_backend(backend)
            raced.last_used = time.monotonic()
            return raced
        _sessions[row.id] = created
        return created


async def release_browse_session(backend_id: int) -> None:
    """Close the cached backend and delete its temp workspace."""
    async with _sessions_guard:
        session = _sessions.pop(backend_id, None)
    if session is not None:
        _dispose_session(session)


async def _with_browse_backend[T](
    row: BackendRow,
    op: Callable[[Any], Awaitable[T]],
) -> T:
    session = await acquire_browse_session(row)
    async with session.lock:
        try:
            return await op(session.backend)
        finally:
            session.last_used = time.monotonic()


async def _list_backend_entries(backend: Any, path: str) -> list[Any]:
    """Single-level listing; tolerate both ``LsResult`` and ``als_info`` lists."""
    als_info = getattr(backend, "als_info", None)
    if callable(als_info):
        raw = als_info(path)
        if inspect.isawaitable(raw):
            raw = await raw
        if isinstance(raw, list):
            return raw
    try:
        result = await backend.als(path)
    except NotImplementedError:
        raise ValueError("listing is not implemented for this backend") from None
    if isinstance(result, list):
        return result
    if err := getattr(result, "error", None):
        raise StorageBrowseError(classify_storage_error(err))
    return list(getattr(result, "entries", None) or [])


async def _download_via_backend(backend: Any, path: str) -> bytes:
    adownload = getattr(backend, "adownload_files", None)
    download = getattr(backend, "download_files", None)
    if callable(adownload):
        results = await adownload([path])
    elif callable(download):
        results = await asyncio.to_thread(download, [path])
    else:
        raise StorageBrowseError(
            classify_storage_error("download is not supported on this backend"),
        )
    if not results:
        raise FileNotFoundError(f"cannot read {path!r}")
    first = results[0]
    err = _download_row_error(first)
    if err in {"file_not_found", "invalid_path", "is_directory"}:
        raise FileNotFoundError(f"cannot read {path!r}: {err}")
    if err:
        raise StorageBrowseError(classify_storage_error(err))
    data = _download_row_bytes(first)
    if data is None:
        raise FileNotFoundError(f"cannot read {path!r}")
    return data


async def download_storage_backend_file(
    row: BackendRow,
    path: str,
    *,
    preview: bool = False,
) -> bytes:
    """Return raw bytes for *path* (admin browse / preview)."""
    path = normalize_browse_path(path)
    if path == "/":
        raise FileNotFoundError("cannot read '/'")

    async def _op(backend: Any) -> bytes:
        return await _download_via_backend(backend, path)

    data = await _with_browse_backend(row, _op)
    limit = PREVIEW_BYTE_LIMIT if preview else DOWNLOAD_BYTE_LIMIT
    if len(data) > limit:
        raise _too_large(preview)
    return data


def _coerce_preview_text(content: str) -> str:
    # deepagents empty-file reminder is for LLM tools, not the dashboard.
    if content == "System reminder: File exists but has empty contents":
        return ""
    return content


async def read_storage_backend_text(row: BackendRow, path: str) -> str:
    """UTF-8 text for the workspace-style file viewer."""
    data = await download_storage_backend_file(row, path, preview=True)
    if len(data) > TEXT_PREVIEW_LIMIT:
        raise _too_large(True)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StorageBrowseError(
            ClassifiedStorageError(
                message="This file is not valid UTF-8 text. Download it instead.",
                message_key="browse_not_text",
            ),
        ) from exc
    return _coerce_preview_text(text)


async def list_storage_backend_tree(row: BackendRow, path: str = "/") -> list[dict[str, Any]]:
    """Single-level listing under *path*; returns JSON-friendly file info dicts.

    The harness backend is cached per storage-backend id so Docker sandboxes
    are not created and destroyed on every expand / preview.
    """
    path = normalize_browse_path(path)

    async def _op(backend: Any) -> list[dict[str, Any]]:
        entries = await _list_backend_entries(backend, path)
        return dedupe_tree_rows([_entry_to_dict(e) for e in entries], parent=path)

    return await _with_browse_backend(row, _op)


def _entry_to_dict(info: Any) -> dict[str, Any]:
    """Normalise a harness FileInfo (object or dict) to a plain dict."""
    get = info.get if isinstance(info, dict) else lambda k: getattr(info, k, None)
    out: dict[str, Any] = {"path": get("path")}  # type: ignore[no-untyped-call]
    if (is_dir := get("is_dir")) is not None:  # type: ignore[no-untyped-call]
        out["is_dir"] = bool(is_dir)
    if (size := get("size")) is not None:  # type: ignore[no-untyped-call]
        out["size"] = int(size)
    if (modified_at := get("modified_at")) is not None:  # type: ignore[no-untyped-call]
        out["modified_at"] = modified_at
    return out
