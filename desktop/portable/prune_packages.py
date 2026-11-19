#!/usr/bin/env python3
"""Strip files the desktop and green packages do not need at runtime.

Both artifacts are built from the tree ``package.sh`` assembles, so this runs
once before the zip is written. Removed:

- ``googleapiclient/discovery_cache/documents`` (the offline discovery corpus)
- ``PyObjCTest``
- ``*.dSYM`` debug symbols
- third-party ``tests``, ``test``, and ``testing`` directories

``octop`` is left intact (its subagent library has a directory named
``testing``). ``numpy/testing`` stays because it is a public module.

``discovery.build()`` defaults to ``static_discovery=True`` and raises when the
static document is missing, so the matching branch in ``discovery.py`` is
rewritten to fall through to the network fetch.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_TEST_DIR_NAMES = frozenset({"tests", "test", "testing"})

_STATIC_MISS = """        if content:
            return content
        else:
            raise UnknownApiNameOrVersion(
                "name: %s  version: %s" % (serviceName, version)
            )
"""

_STATIC_FALLTHROUGH = """        if content:
            return content
        # portable-prune: a missing static document falls through to the network.
"""


def prune_packages(packages: Path) -> list[str]:
    """Delete packaged bloat under ``packages`` and return removed relative paths."""
    removed: list[str] = []
    documents = packages / "googleapiclient" / "discovery_cache" / "documents"
    if documents.is_dir():
        _remove_tree(documents)
        removed.append("googleapiclient/discovery_cache/documents")
    pyobjc_test = packages / "PyObjCTest"
    if pyobjc_test.exists():
        _remove_tree(pyobjc_test)
        removed.append("PyObjCTest")

    for current, dirnames, _filenames in _walk_topdown(packages):
        kept: list[str] = []
        for name in dirnames:
            child = current / name
            rel = child.relative_to(packages)
            if name.endswith(".dSYM") or _is_packaged_test_dir(rel):
                _remove_tree(child)
                removed.append(rel.as_posix())
                continue
            kept.append(name)
        dirnames[:] = kept

    _relax_static_discovery(packages / "googleapiclient" / "discovery.py")
    return removed


def _walk_topdown(packages: Path):
    for dirpath, dirnames, filenames in os.walk(packages, topdown=True):
        yield Path(dirpath), dirnames, filenames


def _is_packaged_test_dir(rel: Path) -> bool:
    if rel.name not in _TEST_DIR_NAMES:
        return False
    if rel.parts[0] == "octop":
        return False
    return rel.parts != ("numpy", "testing")


def _relax_static_discovery(discovery_py: Path) -> None:
    if not discovery_py.is_file():
        return
    text = discovery_py.read_text(encoding="utf-8")
    if _STATIC_FALLTHROUGH in text:
        return
    count = text.count(_STATIC_MISS)
    if count != 1:
        raise SystemExit(
            f"[prune] {discovery_py} has {count} static-discovery miss branches; "
            "expected 1. google-api-python-client changed, update prune_packages.py."
        )
    discovery_py.write_text(text.replace(_STATIC_MISS, _STATIC_FALLTHROUGH, 1), encoding="utf-8")


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit(f"usage: {argv[0]} <site-packages>")
    packages = Path(argv[1])
    if not packages.is_dir():
        raise SystemExit(f"[prune] not a directory: {packages}")
    removed = prune_packages(packages)
    print(f"[prune] removed {len(removed)} paths under {packages}")


if __name__ == "__main__":
    main(sys.argv)
