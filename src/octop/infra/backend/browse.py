"""List directories on a configured storage backend (harness ``als``)."""

from __future__ import annotations

import contextlib
import tempfile
from typing import Any

from harness_agent.backends import resolve_backend

from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.db.repos.backends import BackendRow


def resolve_storage_backend(row: BackendRow) -> Any:
    """Instantiate a harness backend for *row* (ephemeral workspace dir)."""
    spec = row_to_backend_spec(row)
    if spec is None:
        raise ValueError("configuration incomplete")
    workspace = tempfile.mkdtemp(prefix="octop-storage-browse-")
    try:
        return resolve_backend(spec, workspace_dir=workspace)
    except ValueError:
        raise
    except Exception as exc:
        # ImportError (missing extra), RuntimeError (image/pull), DockerException, …
        raise ValueError(str(exc)) from exc


def _close_backend(backend: Any) -> None:
    """Best-effort close for backends that own external resources (e.g. Docker)."""
    close = getattr(backend, "close", None)
    if callable(close):
        with contextlib.suppress(Exception):
            close()


async def list_storage_backend_tree(row: BackendRow, path: str = "/") -> list[dict[str, Any]]:
    """Single-level listing under *path*; returns JSON-friendly file info dicts.

    For ``kind=docker``, starts a short-lived sandbox container, lists via
    ``als`` (in-container ``workspace_path``, default ``/workspace``), then
    stops the container.
    """
    backend = resolve_storage_backend(row)
    try:
        result = await backend.als(path)
        if err := getattr(result, "error", None):
            raise ValueError(str(err))
        entries = getattr(result, "entries", None) or []
        return [_entry_to_dict(e) for e in entries]
    finally:
        _close_backend(backend)


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
