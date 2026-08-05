"""Host filesystem directory helpers for dashboard root_dir pickers."""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path
from typing import Any, Literal

ProbeCode = Literal["not_directory", "permission_denied", "write_failed", "not_allowed"]

_MAX_LIST_ENTRIES = 1000

# Host paths that must not be browsed or used as workspace roots (POSIX).
_DENIED_PREFIXES_POSIX = ("/proc", "/sys", "/dev", "/etc", "/root")


def normalize_host_path(path: str) -> Path:
    raw = path.strip() or "/"
    return Path(raw).expanduser().resolve()


def _is_denied_host_path(resolved: Path) -> bool:
    if os.name != "posix":
        return False
    text = resolved.as_posix()
    # macOS resolves /etc → /private/etc (and similar). Strip that prefix so
    # denied policy still matches the logical system locations.
    if text == "/private" or text.startswith("/private/"):
        text = text[len("/private") :] or "/"
    return any(text == denied or text.startswith(f"{denied}/") for denied in _DENIED_PREFIXES_POSIX)


def assert_safe_host_path(path: str) -> Path:
    """Resolve *path* and reject traversal tricks / disallowed host locations."""
    if not path or "\0" in path:
        raise ValueError("invalid path")
    try:
        resolved = normalize_host_path(path)
    except OSError as exc:
        raise ValueError("invalid path") from exc
    if not resolved.is_absolute():
        raise ValueError("path must be absolute")
    if _is_denied_host_path(resolved):
        raise ValueError("path not allowed")
    return resolved


def list_host_subdirs(path: str) -> list[dict[str, Any]]:
    """List readable child directories under *path*."""
    root = assert_safe_host_path(path)
    if not root.is_dir():
        raise ValueError(f"not a directory: {path}")

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise ValueError(f"permission denied: {path}") from exc

    for child in children:
        if len(entries) >= _MAX_LIST_ENTRIES:
            break
        if not child.is_dir():
            continue
        try:
            resolved = child.resolve()
            if not resolved.is_dir():
                continue
            if _is_denied_host_path(resolved):
                continue
            if not os.access(resolved, os.R_OK | os.X_OK):
                continue
        except OSError:
            continue
        entries.append({"path": str(resolved), "name": child.name})
    return entries


def probe_host_root_dir(path: str) -> dict[str, Any]:
    """Verify *path* exists; write-probe only when not filesystem root ``/``."""
    try:
        root = assert_safe_host_path(path)
    except ValueError as exc:
        message = str(exc)
        code: ProbeCode = "not_allowed" if "not allowed" in message else "not_directory"
        return {"ok": False, "code": code, "detail": message}

    if not root.is_dir():
        return {"ok": False, "code": "not_directory"}

    if os.name == "posix" and root.as_posix() == "/":
        return {"ok": True, "path": "/"}

    if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        return {"ok": False, "code": "permission_denied"}

    probe_file = root / f".octop-root-probe-{uuid.uuid4().hex}"
    try:
        probe_file.write_text("", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "code": "write_failed", "detail": str(exc)}
    finally:
        with contextlib.suppress(OSError):
            probe_file.unlink(missing_ok=True)

    return {"ok": True, "path": str(root)}


def _validate_dir_basename(name: str) -> str:
    """Reject empty names, path segments, and traversal tokens."""
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("invalid name")
    if "/" in cleaned or "\\" in cleaned or "\0" in cleaned:
        raise ValueError("invalid name")
    if cleaned != Path(cleaned).name:
        raise ValueError("invalid name")
    return cleaned


def _unique_child_name(parent: Path, base_name: str) -> str:
    candidate = base_name
    index = 2
    while (parent / candidate).exists():
        candidate = f"{base_name} ({index})"
        index += 1
    return candidate


def mkdir_host_subdir(parent: str, *, base_name: str = "New Folder") -> dict[str, Any]:
    """Create a child directory under *parent* with an unused name from *base_name*."""
    root = assert_safe_host_path(parent)
    if not root.is_dir():
        raise ValueError(f"not a directory: {parent}")
    name = _unique_child_name(root, _validate_dir_basename(base_name))
    target = root / name
    # Re-check after composing path (deny creating into denied prefixes).
    assert_safe_host_path(str(target))
    try:
        target.mkdir(exist_ok=False)
    except OSError as exc:
        raise ValueError(f"mkdir failed: {exc}") from exc
    return {"path": str(target.resolve()), "name": name}


def rename_host_dir(path: str, new_name: str) -> dict[str, Any]:
    """Rename a host directory in place (basename only)."""
    source = assert_safe_host_path(path)
    if not source.is_dir():
        raise ValueError(f"not a directory: {path}")
    name = _validate_dir_basename(new_name)
    target = source.parent / name
    assert_safe_host_path(str(target))
    if target.exists():
        raise ValueError("already exists")
    try:
        source.rename(target)
    except OSError as exc:
        raise ValueError(f"rename failed: {exc}") from exc
    return {"path": str(target.resolve()), "name": name}
