"""Explicit virtual-path conversion for subtree experts.

File tools already reject native drive paths in ``validate_path`` and then
resolve the normalized virtual path. This module runs that same chain for a
caller-supplied virtual path. It does not scan shell commands.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.tools import StructuredTool

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")

# Soft policy for the model only. Shell still does not rewrite commands.
EXPLICIT_VIRTUAL_PATH_PROMPT = (
    "This expert uses explicit virtual paths: `/` is the selected storage root, "
    "not a host drive letter. Filesystem tools already accept virtual paths such "
    "as `/data/a.txt`. execute/shell is not rewritten — first call "
    "`virtual_to_native_path` and pass only the returned native path to the "
    "command. Never give filesystem tools a drive-letter path."
)


def require_explicit_virtual_absolute(path: str) -> str:
    """Reject anything that is not already a virtual absolute path."""
    if not isinstance(path, str):
        raise ValueError("virtual path must be a string")
    text = path.strip()
    if not text.startswith("/") or text.startswith("//") or "\\" in text or _DRIVE_PREFIX.match(text) is not None:
        raise ValueError("path must be an explicit virtual absolute path such as /data/a.txt")
    return text


def resolve_explicit_virtual_path(path: str, backend: Any) -> str:
    """Return the native path for one explicit virtual path.

    The chain is: explicit-virtual check, ``validate_path`` (its return value,
    not the original string), then the bound backend's ``_resolve_path``.
    """
    from deepagents.backends.utils import validate_path

    explicit = require_explicit_virtual_absolute(path)
    normalized = validate_path(explicit)
    resolve_fn = getattr(backend, "_resolve_path", None)
    if not callable(resolve_fn):
        default = getattr(backend, "default", None)
        resolve_fn = getattr(default, "_resolve_path", None)
    if not callable(resolve_fn):
        raise ValueError("backend cannot resolve virtual paths")
    native = resolve_fn(normalized)
    text = os.fspath(native) if isinstance(native, os.PathLike) else native
    if not isinstance(text, str):
        raise ValueError("backend did not return a path")
    return text


def build_virtual_to_native_tool(backend: Any) -> StructuredTool:
    """Tool bound to *backend*. The caller passes only the virtual path."""

    def virtual_to_native_path(path: str) -> dict[str, str]:
        native = resolve_explicit_virtual_path(path, backend)
        return {"kind": "native_path", "path": native}

    return StructuredTool.from_function(
        func=virtual_to_native_path,
        name="virtual_to_native_path",
        description=(
            "Convert one explicit virtual absolute path, such as /data/a.txt, "
            "to the native host path inside this expert's root. "
            "Use this before execute/shell. Pass only the virtual path — not a "
            "drive letter, backslash, or relative path. "
            "The result is {kind: native_path, path}; quote path yourself in the command."
        ),
    )
