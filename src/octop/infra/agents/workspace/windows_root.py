"""New Windows experts store one real directory root.

Only a fully qualified absolute path is accepted: a drive plus a root
separator (``C:/work``, ``D:/``), or a UNC path under a share
(``\\\\server\\share\\data``). Relative inputs (``work``, ``./work``,
``.``, ``..``), drive-relative inputs (``D:``, ``D:work``), and paths with
no drive (``/``, ``\\foo``) are rejected before ``realpath`` can fill them
in from the process current directory or current drive. Omitted ``root_dir``
is filled by the server with the policy root, or the process account home,
and that filled value must pass the same check.
"""

from __future__ import annotations

import ntpath
import os
import re
from collections.abc import Callable
from typing import Any

_LOCAL_KINDS = frozenset({"local_shell", "filesystem"})
# Other built-in backend types. They keep their existing create path and are
# not stamped with subtree semantics. Kept aligned with
# octop_harness.backends._BUILTIN_TYPES.
_OTHER_BACKEND_KINDS = frozenset(
    {
        "state",
        "store",
        "composite",
        "s3",
        "postgres",
        "cos",
        "oss",
        "obs",
        "docker",
        "opensandbox",
    }
)
_DRIVE_ROOT = re.compile(r"^[A-Za-z]:[/\\]$")


def windows_new_expert_subtree_enabled() -> bool:
    """New Windows experts take the subtree path. POSIX create does not."""
    return os.name == "nt"


def is_fully_qualified_windows_path(raw: str) -> bool:
    """True only when *raw* is absolute without consulting the process cwd."""
    if not isinstance(raw, str):
        return False
    text = raw.strip()
    if not text or text in {".", ".."}:
        return False
    drive, tail = ntpath.splitdrive(text)
    if drive.startswith("\\\\") or drive.startswith("//"):
        body = drive[2:].replace("/", "\\")
        parts = [part for part in body.split("\\") if part]
        if len(parts) < 2:
            return False
        return tail.startswith("\\") or tail.startswith("/")
    if len(drive) == 2 and drive[1] == ":" and drive[0].isalpha():
        return tail.startswith("\\") or tail.startswith("/")
    return False


def windows_root_input_ambiguous(raw: str) -> bool:
    """True when *raw* is not a fully qualified Windows absolute path."""
    return not is_fully_qualified_windows_path(raw)


def normalize_volume_root(drive: str) -> str:
    """Turn ``C:\\`` or ``d:`` into ``C:/``."""
    text = drive.strip().replace("\\", "/")
    if len(text) >= 2 and text[1] == ":":
        return text[0].upper() + ":/"
    if text and not text.endswith("/"):
        text += "/"
    return text


def windows_picker_defaults(
    *,
    home: str,
    drives: list[str],
    legacy_tree_root: str,
) -> dict[str, Any]:
    """Unrestricted Windows picker: one collapsed row per ready drive.

    The preselect is the home drive (``C:/``), not the profile directory.
    Opening the list then shows every volume, with that drive highlighted,
    instead of expanding ``C:/Users/...`` and pushing the other drives away.
    """
    roots = normalize_volume_roots(drives)
    if not roots and legacy_tree_root:
        roots = [normalize_volume_root(legacy_tree_root)]
    return {
        "default_root_dir": _preselect_volume(home, legacy_tree_root, roots),
        "tree_root": legacy_tree_root,
        "tree_roots": roots,
    }


def _preselect_volume(home: str, legacy_tree_root: str, roots: list[str]) -> str:
    """Prefer the volume that contains *home* when that volume is in the forest."""
    candidate = ""
    if len(home) >= 2 and home[1] == ":":
        candidate = normalize_volume_root(home)
    elif legacy_tree_root:
        candidate = normalize_volume_root(legacy_tree_root)
    if candidate and (not roots or candidate in roots):
        return candidate
    if roots:
        return roots[0]
    return candidate or home


def normalize_volume_roots(drives: list[str]) -> list[str]:
    seen: list[str] = []
    for drive in drives:
        root = normalize_volume_root(drive)
        if root and root not in seen:
            seen.append(root)
    return seen


def classify_new_windows_backend(config: dict[str, Any]) -> str:
    """Classify a create-time backend before any subtree checks.

    Returns ``"local"`` after normalizing ``None``, ``"local_shell"``,
    ``"filesystem"``, and dicts of those types. Returns ``"other"`` for a
    known non-local type and leaves that config unchanged. Raises
    ``ValueError`` for a malformed or unknown representation.
    """
    backend = config.get("backend")
    if backend is None:
        config["backend"] = {"type": "local_shell"}
        return "local"
    if isinstance(backend, str):
        kind = backend.strip().lower()
        if kind in _LOCAL_KINDS:
            config["backend"] = {"type": kind}
            return "local"
        if kind in _OTHER_BACKEND_KINDS:
            return "other"
        raise ValueError(f"unsupported backend representation {backend!r}")
    if isinstance(backend, dict):
        raw_type = backend.get("type")
        if not isinstance(raw_type, str) or not raw_type.strip():
            raise ValueError("unsupported backend representation")
        kind = raw_type.strip().lower()
        if kind in _LOCAL_KINDS:
            normalized = dict(backend)
            normalized["type"] = kind
            config["backend"] = normalized
            return "local"
        if kind in _OTHER_BACKEND_KINDS:
            return "other"
        raise ValueError(f"unsupported backend representation {raw_type!r}")
    raise ValueError(f"unsupported backend representation {type(backend).__name__}")


def stamp_new_windows_subtree(
    config: dict[str, Any],
    *,
    home: str,
    policy_root: str | None = None,
    resolve: Callable[[str], str] | None = None,
) -> None:
    """Mark a newly created Windows local expert as a real single-root subtree.

    Existing rows are not passed through here. A missing semantics flag on a
    new local request still takes this path, because the server calls it.
    Known non-local backends are left unchanged. Validation finishes before
    any directory is created; this function does not mkdir.
    """
    if classify_new_windows_backend(config) != "local":
        return
    backend = config["backend"]
    raw = backend.get("root_dir")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        chosen = (policy_root or "").strip() or home.strip()
    else:
        chosen = str(raw).strip()
    if not is_fully_qualified_windows_path(chosen):
        raise ValueError("windows root must be a fully qualified path")
    if _DRIVE_ROOT.match(chosen):
        chosen = normalize_volume_root(chosen)
    if "virtual_mode" in backend and backend["virtual_mode"] is not True:
        raise ValueError("subtree experts require virtual_mode")
    if resolve is not None:
        stored = resolve(chosen)
    elif os.name == "nt":
        stored = os.path.realpath(os.path.expanduser(chosen)).replace("\\", "/")
    else:
        stored = chosen.replace("\\", "/")
    if not is_fully_qualified_windows_path(stored):
        raise ValueError("windows root must be a fully qualified path")
    backend["root_dir"] = stored
    backend["virtual_mode"] = True
    config["root_semantics"] = "subtree"
