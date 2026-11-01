"""Shared self-delete guard for destructive root wipes.

`octop init --force` and `octop clean --all` remove the whole install root
(``~/.octop``). Official ``install.sh`` puts the runtime venv at
``~/.octop/venv``: wiping that directory deletes the interpreter the running
CLI depends on, so every later ``octop`` command fails with
``ModuleNotFoundError`` / ``command not found`` (TencentCloud/Octop#2611).

The guard refuses to wipe when the active runtime or the running CLI lives
inside the target root and points the user at the data-only alternative.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:  # pragma: no cover - unresolvable path cannot equal root
        return p


def ensure_root_not_runtime(root: Path) -> None:
    """Refuse to wipe *root* when the running CLI's venv lives inside it.

    Checks ``sys.prefix`` / ``sys.exec_prefix`` (venv location) and the
    resolved ``sys.executable`` so a ``pip``-checkout install, a venv dir,
    and macOS-style ``bin/python`` nested layouts are all covered.
    """
    resolved_root = _resolve(root)
    live = [Path(sys.prefix), Path(sys.exec_prefix), Path(sys.executable)]
    for path in live:
        resolved = _resolve(path)
        if resolved == resolved_root or resolved_root in resolved.parents:
            raise SystemExit(
                f"error: refusing to wipe {resolved_root}: the running Octop "
                f"runtime lives inside it ({resolved}). Deleting it would "
                "disable the CLI itself. Move the venv out of "
                f"{resolved_root}, or use 'octop clean' without --all (CLI "
                "state only) and reinstall instead.",
            )
