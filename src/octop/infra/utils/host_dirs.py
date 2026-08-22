"""Host filesystem directory helpers for dashboard root_dir pickers."""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path
from typing import Any, Literal

ProbeCode = Literal[
    "not_directory",
    "permission_denied",
    "write_failed",
    "not_allowed",
    "outside_home",
]

_MAX_LIST_ENTRIES = 1000

# Host paths that must not be browsed or used as workspace roots (POSIX).
_DENIED_PREFIXES_POSIX = ("/proc", "/sys", "/dev", "/etc", "/root")

_OUTSIDE_HOME_MSG = "path outside home"
_NOT_ALLOWED_MSG = "path not allowed"


def host_path_text(path: Path) -> str:
    """Serialize a host path for API/UI (POSIX separators, even on Windows)."""
    return Path(os.path.realpath(os.path.expanduser(str(path)))).as_posix()


def host_home_dir() -> Path:
    """Absolute home directory of the OS user running the Octop process."""
    return Path(os.path.realpath(os.path.expanduser(str(Path.home()))))


def host_fs_tree_root(*, allow_outside_home: bool) -> str:
    """Browse-tree root for the root_dir picker.

    When *allow_outside_home* is true (current API default for all users):
    host ``/`` on POSIX, or the home drive root (e.g. ``C:/``) on Windows.
    Otherwise: the process home directory (legacy helper mode).
    """
    home = host_home_dir()
    if not allow_outside_home:
        return host_path_text(home)
    if os.name == "posix":
        return "/"
    return host_path_text(Path(home.anchor))


def _path_within_base(resolved: str, base: str) -> bool:
    """True when *resolved* equals *base* or is a subdirectory (normcase-safe).

    Uses ``startswith`` after ``os.path.realpath`` so CodeQL treats this as a
    path-injection containment barrier (``Path.resolve`` / ``relative_to`` are
    not modeled as sanitizers).
    """
    resolved_n = os.path.normcase(resolved)
    base_n = os.path.normcase(base)
    if resolved_n == base_n:
        return True
    if base_n.endswith(os.sep):
        return resolved_n.startswith(base_n)
    return resolved_n.startswith(base_n + os.sep)


def is_within_host_home(resolved: Path, *, home: Path | None = None) -> bool:
    """True when *resolved* is the host home directory or a subdirectory."""
    base = os.path.realpath(str(home or host_home_dir()))
    target = os.path.realpath(str(resolved))
    return _path_within_base(target, base)


def normalize_host_path(path: str) -> Path:
    """Canonical absolute path via ``os.path.realpath`` (CodeQL-recognized)."""
    raw = path.strip() or ("/" if os.name == "posix" else str(Path.home().anchor))
    return Path(os.path.realpath(os.path.expanduser(raw)))


def _browse_tree_base(*, restrict_to_home: bool) -> str:
    """Containment root for picker paths (home jail or host/drive root)."""
    if restrict_to_home:
        return os.path.realpath(str(host_home_dir()))
    if os.name == "posix":
        return os.path.realpath("/")
    return os.path.realpath(str(Path.home().anchor))


def _is_denied_host_path(resolved: Path) -> bool:
    if os.name != "posix":
        return False
    # Process home may coincide with a denylist prefix (uid 0 → ``/root``).
    # The UI defaults ``root_dir`` to home, so home and its subdirs must stay
    # selectable; ``/root`` remains denied for non-root process homes.
    if is_within_host_home(resolved):
        return False
    text = resolved.as_posix()
    # macOS resolves /etc → /private/etc (and similar). Strip that prefix so
    # denied policy still matches the logical system locations.
    if text == "/private" or text.startswith("/private/"):
        text = text[len("/private") :] or "/"
    return any(text == denied or text.startswith(f"{denied}/") for denied in _DENIED_PREFIXES_POSIX)


def assert_safe_host_path(path: str, *, restrict_to_home: bool = False) -> Path:
    """Resolve *path* and reject traversal tricks / disallowed host locations.

    When *restrict_to_home* is true, only the process home directory and its
    subdirectories are allowed. The HTTP filesystem / expert APIs pass
    ``False`` so any authenticated user may pick outside home (denylist still
    applies).

    Normalization uses ``os.path.realpath`` and containment uses ``startswith``
    against the browse-tree base — the pattern CodeQL recognizes for
    ``py/path-injection`` (unlike ``Path.resolve`` alone).
    """
    if not path or "\0" in path:
        raise ValueError("invalid path")
    try:
        # normalize_host_path already realpath's; keep a str for startswith
        # so CodeQL sees a containment sanitizer on the FS path we return.
        resolved_s = os.fspath(normalize_host_path(path))
    except OSError as exc:
        raise ValueError("invalid path") from exc
    if not os.path.isabs(resolved_s):
        raise ValueError("path must be absolute")
    base = _browse_tree_base(restrict_to_home=restrict_to_home)
    if not _path_within_base(resolved_s, base):
        raise ValueError(_OUTSIDE_HOME_MSG if restrict_to_home else "path must be absolute")
    resolved = Path(resolved_s)
    if _is_denied_host_path(resolved):
        raise ValueError(_NOT_ALLOWED_MSG)
    return resolved


def list_host_subdirs(path: str, *, restrict_to_home: bool = False) -> list[dict[str, Any]]:
    """List readable child directories under *path*."""
    root = assert_safe_host_path(path, restrict_to_home=restrict_to_home)
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
            resolved = Path(os.path.realpath(str(child)))
            if not resolved.is_dir():
                continue
            if _is_denied_host_path(resolved):
                continue
            if restrict_to_home and not is_within_host_home(resolved):
                continue
            if not os.access(resolved, os.R_OK | os.X_OK):
                continue
        except OSError:
            continue
        entries.append({"path": host_path_text(resolved), "name": child.name})
    return entries


def probe_host_root_dir(path: str, *, restrict_to_home: bool = False) -> dict[str, Any]:
    """Verify *path* exists; write-probe only when not filesystem root ``/``."""
    try:
        root = assert_safe_host_path(path, restrict_to_home=restrict_to_home)
    except ValueError as exc:
        message = str(exc)
        if _OUTSIDE_HOME_MSG in message:
            code: ProbeCode = "outside_home"
        elif _NOT_ALLOWED_MSG in message:
            code = "not_allowed"
        else:
            code = "not_directory"
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

    return {"ok": True, "path": host_path_text(root)}


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


def mkdir_host_subdir(
    parent: str, *, base_name: str = "New Folder", restrict_to_home: bool = False
) -> dict[str, Any]:
    """Create a child directory under *parent* with an unused name from *base_name*."""
    root = assert_safe_host_path(parent, restrict_to_home=restrict_to_home)
    if not root.is_dir():
        raise ValueError(f"not a directory: {parent}")
    name = _unique_child_name(root, _validate_dir_basename(base_name))
    target = root / name
    # Re-check after composing path (deny creating into denied prefixes).
    assert_safe_host_path(str(target), restrict_to_home=restrict_to_home)
    try:
        target.mkdir(exist_ok=False)
    except OSError as exc:
        raise ValueError(f"mkdir failed: {exc}") from exc
    return {"path": host_path_text(target), "name": name}


def rename_host_dir(path: str, new_name: str, *, restrict_to_home: bool = False) -> dict[str, Any]:
    """Rename a host directory in place (basename only)."""
    source = assert_safe_host_path(path, restrict_to_home=restrict_to_home)
    if not source.is_dir():
        raise ValueError(f"not a directory: {path}")
    name = _validate_dir_basename(new_name)
    target = source.parent / name
    assert_safe_host_path(str(target), restrict_to_home=restrict_to_home)
    if target.exists():
        raise ValueError("already exists")
    try:
        source.rename(target)
    except OSError as exc:
        raise ValueError(f"rename failed: {exc}") from exc
    return {"path": host_path_text(target), "name": name}


def iter_local_backend_root_dirs(spec: Any) -> list[str]:
    """Collect ``root_dir`` values from local_shell / filesystem backend specs."""
    if not isinstance(spec, dict):
        return []
    kind = str(spec.get("type") or "").strip()
    found: list[str] = []
    if kind in {"local_shell", "filesystem"}:
        root = spec.get("root_dir")
        if isinstance(root, str) and root.strip():
            found.append(root.strip())
        elif root is None or (isinstance(root, str) and not root.strip()):
            # Missing root_dir historically meant host root ``/``.
            found.append("/")
    elif kind == "composite":
        default = spec.get("default")
        found.extend(iter_local_backend_root_dirs(default))
        routes = spec.get("routes")
        if isinstance(routes, dict):
            for route_spec in routes.values():
                found.extend(iter_local_backend_root_dirs(route_spec))
    return found


def assert_backend_root_dirs_allowed(spec: Any, *, restrict_to_home: bool) -> None:
    """Raise ``ValueError`` when a local backend ``root_dir`` is not browsable."""
    for root_dir in iter_local_backend_root_dirs(spec):
        assert_safe_host_path(root_dir, restrict_to_home=restrict_to_home)
