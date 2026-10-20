"""Backend utility helpers — I/O helpers and workspace path rules."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol

logger = logging.getLogger(__name__)

BACKEND_CALL_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
    json.JSONDecodeError,
    UnicodeDecodeError,
)

DEFENSIVE_OP_ERRORS: tuple[type[BaseException], ...] = (
    *BACKEND_CALL_ERRORS,
    LookupError,
    sqlite3.Error,
    ImportError,
    ModuleNotFoundError,
    TimeoutError,
    ConnectionError,
)

ASYNC_DEFENSIVE_OP_ERRORS: tuple[type[BaseException], ...] = (
    *DEFENSIVE_OP_ERRORS,
    asyncio.CancelledError,
)


def is_complete_storage_path(path: str) -> bool:
    """Return True when *path* is an opaque storage key that must not be anchored.

    Only ``~``-prefixed paths (e.g. ``~/.octop/agents/<id>/SOUL.md``) qualify.
    Root-anchored virtual paths such as ``/SOUL.md`` are **not** complete — they
    are keys under the backend virtual root ``/``.
    """
    return path.startswith("~")


def anchor_at_backend_root(entry: str | Path) -> str:
    """Anchor a root-relative *fragment* at ``/``; pass complete paths through."""
    s = str(entry)
    if is_complete_storage_path(s):
        return s
    if s.startswith("/"):
        return s
    if s.startswith("./"):
        s = s[2:]
    return f"/{s}"


class BackendOperationNotSupportedError(RuntimeError):
    """Raised when the active backend cannot perform delete/move."""

    def __init__(self, operation: str, backend_type: str) -> None:
        self.operation = operation
        self.backend_type = backend_type
        super().__init__(f"{operation} is not supported by backend type {backend_type!r}")


def materialize_storage_path(
    storage_path: str,
    *,
    host_mount: str | Path | None = None,
    backend: object | None = None,
    must_exist: bool = False,
) -> Path | None:
    """Map a backend storage key to a local filesystem path when possible.

    Supply either *host_mount* (explicit local-class backend disk mount) or
    *backend* (duck-typed for ``cwd`` / ``root_dir``).  When both are given,
    *host_mount* wins.  Returns ``None`` when no mount is available, or when
    *must_exist* is True and the path is not an existing file.

    This is an escape hatch for channel adapters and admin tooling — normal L1
    I/O should go through :class:`~octop_harness.backends.workspace.BackendWorkspace`.
    """
    mount: Path | None
    if host_mount is not None:
        mount = Path(host_mount).expanduser()
    elif backend is not None:
        mount_raw = getattr(backend, "root_dir", None) or getattr(backend, "cwd", None)
        if mount_raw is None:
            return None
        mount = Path(str(mount_raw)).expanduser()
    else:
        msg = "materialize_storage_path requires host_mount or backend"
        raise ValueError(msg)

    if is_complete_storage_path(storage_path):
        candidate = Path(storage_path).expanduser()
    else:
        candidate = mount / storage_path.lstrip("/")

    if must_exist and not candidate.is_file():
        return None
    return candidate


def backend_write_force(backend: BackendProtocol, path: str, content: str) -> None:
    """Write *content* to *path*, overwriting if the file already exists.

    The standard deepagents ``backend.write()`` refuses to overwrite an
    existing file (a guardrail for LLM-driven writes). This helper falls
    back to a full-content ``edit()`` when the file already exists.
    """
    write_result = backend.write(path, content)
    if write_result.error is None:
        return

    # File likely exists — read it and replace via edit.
    read_result = backend.read(path, offset=0, limit=10_000_000)
    if read_result.error is not None:
        raise OSError(
            f"backend_write_force failed for {path!r}: write={write_result.error}, read={read_result.error}",
        )

    file_data = read_result.file_data
    existing = file_data.get("content", "") if file_data is not None else ""
    if existing == content:
        return  # No-op: content unchanged.

    edit_result = backend.edit(path, existing, content, replace_all=False)
    if edit_result.error is not None:
        raise OSError(
            f"backend_write_force edit failed for {path!r}: {edit_result.error}",
        )


def relative_virtual_path(child: str, prefix: str) -> str | None:
    """Return the path of *child* relative to virtual directory *prefix*, or ``None``."""
    child_v = anchor_at_backend_root(child)
    prefix_v = anchor_at_backend_root(prefix).rstrip("/")
    if child_v == prefix_v:
        return ""
    needle = f"{prefix_v}/"
    if child_v.startswith(needle):
        return child_v[len(needle) :]
    return None


try:
    from deepagents.backends import FilesystemBackend, LocalShellBackend

    _LOCAL_BACKEND_TYPES: tuple[type, ...] = (FilesystemBackend, LocalShellBackend)
except ImportError:  # pragma: no cover
    _LOCAL_BACKEND_TYPES = ()


def is_local_class_backend(backend: object) -> bool:
    """Return True for filesystem / local_shell backends backed by a host mount."""
    if _LOCAL_BACKEND_TYPES:
        return isinstance(backend, _LOCAL_BACKEND_TYPES)
    return type(backend).__name__ in ("FilesystemBackend", "LocalShellBackend")


def delete_local_path(path: Path) -> None:
    """Remove a file or directory tree at *path* (must exist)."""
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def mkdir_local_path(path: Path) -> None:
    """Create a directory at *path* (``parents=True``, ``exist_ok=True``)."""
    if path.exists() and not path.is_dir():
        msg = f"cannot mkdir {path}: path exists as file"
        raise FileExistsError(msg)
    path.mkdir(parents=True, exist_ok=True)


def move_local_path(src: Path, dest: Path) -> None:
    """Move *src* to *dest* on the local filesystem."""
    if dest.exists():
        msg = f"destination already exists: {dest}"
        raise FileExistsError(msg)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def backend_file_exists(backend: BackendProtocol, path: str) -> bool:
    """Check whether *path* exists in the backend (without raising)."""
    try:
        result = backend.read(path, offset=0, limit=1)
    except BACKEND_CALL_ERRORS:
        return False
    return result.error is None and result.file_data is not None


__all__ = [
    "ASYNC_DEFENSIVE_OP_ERRORS",
    "BACKEND_CALL_ERRORS",
    "DEFENSIVE_OP_ERRORS",
    "BackendOperationNotSupportedError",
    "anchor_at_backend_root",
    "backend_file_exists",
    "backend_write_force",
    "delete_local_path",
    "is_complete_storage_path",
    "is_local_class_backend",
    "materialize_storage_path",
    "mkdir_local_path",
    "move_local_path",
    "relative_virtual_path",
]
