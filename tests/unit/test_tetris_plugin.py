"""Tetris start hint must name the keys the card actually binds."""

from __future__ import annotations

import importlib.util
import json
import re
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

# ui/index.js binds ArrowUp to `tryMove(s, 0, 0, 1)` (rotate) and " " to
# `hardDropY(s)` + place, so Space is a hard drop and never a rotation.


def _load_tetris() -> Any:
    path = default_bundled_plugins_root() / "tetris" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_tetris", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clauses(text: str) -> list[str]:
    return [part for part in re.split("[、。]", text) if part.strip()]


async def test_space_is_only_offered_for_hard_drop() -> None:
    text = json.loads(await _load_tetris().start_tetris())["text"]
    rotate = [c for c in _clauses(text) if "旋转" in c]
    space = [c for c in _clauses(text) if "空格" in c]
    assert rotate and space, text
    assert all("空格" not in c for c in rotate), rotate
    assert all("硬降" in c for c in space), space
