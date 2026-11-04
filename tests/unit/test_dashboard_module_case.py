"""Vite resolves extensionless imports as ``.ts`` before ``.tsx``.

On a case-insensitive volume, ``BackendFlag.tsx`` and ``backendFlag.ts`` are
the same stem, so the ``.ts`` file wins and the component default export
disappears. Linux CI does not see that; this scan does.
"""

from __future__ import annotations

import os
from pathlib import Path

_VITE_EXTENSIONS = {".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json"}
_DASHBOARD_SRC = Path(__file__).resolve().parents[2] / "dashboard" / "src"


def test_dashboard_module_stems_are_case_distinct() -> None:
    collisions: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(_DASHBOARD_SRC):
        seen: dict[str, str] = {}
        for name in filenames:
            suffix = Path(name).suffix
            if suffix not in _VITE_EXTENSIONS:
                continue
            stem = Path(name).stem.lower()
            previous = seen.get(stem)
            if previous is not None:
                collisions.append(f"{dirpath}: {previous} vs {name}")
            else:
                seen[stem] = name
    assert collisions == []
