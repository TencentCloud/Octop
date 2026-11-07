"""Harness built-in tool sources materialized into every agent workspace.

The harness ships its built-in tools (``browser_use``, ``web_fetch``, …) as
Python modules inside the installed package. Agents periodically want to read
those sources at runtime (for example to review which ``browser_use`` actions
exist), and a workspace that never materialized them fails those reads with
``File .../builtin/tools/browser_use.py not found``. This module copies the
packaged sources into the workspace system tree the same way
:mod:`octop.infra.agents.builtin_skills` does for Skills.
"""

from __future__ import annotations

import logging
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

logger = logging.getLogger(__name__)

BUILTIN_TOOLS_ROOT = "builtin/tools"
VERSION_FILE = ".version"
_HARNESS_TOOLS_PACKAGE = "octop_harness.builtin.tools"


def _collect_tool_sources(source: Traversable, prefix: str, out: list[tuple[str, bytes]]) -> None:
    for entry in source.iterdir():
        if entry.name.startswith((".", "__")):
            continue
        path = f"{prefix}/{entry.name}"
        if entry.is_dir():
            _collect_tool_sources(entry, path, out)
        elif entry.name.endswith(".py"):
            out.append((path, entry.read_bytes()))


async def sync_builtin_tool_sources(workspace: Any) -> list[str]:
    """Copy harness built-in tool scripts under ``{system}/builtin/tools``.

    Returns the workspace-relative paths written this call; an empty list
    means the ``.version`` stamp already matches the installed harness and
    nothing was re-uploaded (keeps agent restarts cheap on remote backends).
    """
    from octop_harness._version import __version__ as harness_version  # noqa: PLC0415

    # ``builtin`` is not one of the harness well-known system dirs that
    # ``system_rel`` auto-prefixes, so spell the system-files prefix out.
    prefix = str(workspace.system_files_path or "").strip("/")
    root = f"{prefix}/{BUILTIN_TOOLS_ROOT}" if prefix else BUILTIN_TOOLS_ROOT
    stamp_path = f"{root}/{VERSION_FILE}"
    stamped = await workspace.aread_text(stamp_path)
    if stamped is not None and stamped.strip() == harness_version:
        return []

    package_root = resources.files(_HARNESS_TOOLS_PACKAGE)
    uploads: list[tuple[str, bytes]] = []
    _collect_tool_sources(package_root, root, uploads)
    if uploads:
        await workspace.aupload_many(uploads)
    await workspace.awrite_text(stamp_path, harness_version, force=True)
    written = sorted(path for path, _ in uploads)
    logger.debug("Materialized %d built-in tool source(s) under %s", len(written), root)
    return written


__all__ = ["BUILTIN_TOOLS_ROOT", "sync_builtin_tool_sources"]
