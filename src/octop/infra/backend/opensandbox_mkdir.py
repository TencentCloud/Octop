"""Compatibility filesystem helpers for older OpenSandbox backends.

Older harness builds have ``execute`` but not ``mkdir_path``, ``delete_path``,
or ``move_path``, and no host mount. ``BackendWorkspace`` then raises
``BackendOperationNotSupportedError`` for bootstrap, skill removal, and rename.
Each helper is attached only when the installed class does not already have it.
"""

from __future__ import annotations

import shlex
from pathlib import PurePosixPath
from typing import Any


def install_opensandbox_fs() -> None:
    """Attach missing filesystem helpers on the installed ``OpenSandbox`` class."""
    try:
        from octop_harness.backends.opensandbox_sandbox import OpenSandbox
    except ImportError:
        return

    def _require(self: Any, command: str, failure: str) -> None:
        result = self.execute(command)
        if result.exit_code not in (0, None):
            raise OSError(result.output or failure)

    if not callable(getattr(OpenSandbox, "mkdir_path", None)):

        def mkdir_path(self: Any, path: str) -> None:
            _require(self, f"mkdir -p {shlex.quote(path)}", f"mkdir failed for {path!r}")

        OpenSandbox.mkdir_path = mkdir_path  # type: ignore[method-assign]

    if not callable(getattr(OpenSandbox, "delete_path", None)):

        def delete_path(self: Any, path: str) -> None:
            _require(self, f"rm -rf {shlex.quote(path)}", f"delete failed for {path!r}")

        OpenSandbox.delete_path = delete_path  # type: ignore[method-assign]

    if not callable(getattr(OpenSandbox, "move_path", None)):

        def move_path(self: Any, src: str, dest: str) -> None:
            parent = str(PurePosixPath(dest).parent)
            command = f"mkdir -p {shlex.quote(parent)} && mv {shlex.quote(src)} {shlex.quote(dest)}"
            _require(self, command, f"move failed for {src!r} -> {dest!r}")

        OpenSandbox.move_path = move_path  # type: ignore[method-assign]
