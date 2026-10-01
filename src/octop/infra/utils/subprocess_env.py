"""Environment for Python subprocesses that must import Octop's dependencies."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import octop


def distribution_root() -> str:
    """Directory holding the installed distributions next to the ``octop`` package.

    Portable (green) installs keep every wheel under ``packages/`` and put that
    directory on *this* process' ``sys.path`` only (see
    ``desktop/portable/templates/launch.py``); ``PYTHONPATH`` is deliberately
    left empty. For a regular install this resolves to the active
    ``site-packages``, which children already see.
    """
    return str(Path(octop.__file__).resolve().parent.parent)


def python_subprocess_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build an env dict so a ``sys.executable`` child can import our packages.

    ``sys.path`` edits made at runtime are not inherited by children, so the
    distribution root is forwarded explicitly and prepended to any existing
    ``PYTHONPATH``. ``PYTHONIOENCODING`` is pinned because these children emit
    NDJSON on a pipe that the parent decodes as UTF-8; without it a Windows
    child encodes to the ANSI code page (cp936/GBK) and dies on any character
    it cannot represent (e.g. ``✅``) before reporting its result.
    """
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    root = distribution_root()
    entries = [entry for entry in env.get("PYTHONPATH", "").split(os.pathsep) if entry]
    if root and root not in entries:
        entries.insert(0, root)
    if entries:
        env["PYTHONPATH"] = os.pathsep.join(entries)
    if overrides:
        env.update(overrides)
    return env
