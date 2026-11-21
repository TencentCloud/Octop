"""Dashboard en.json / zh.json must keep the same leaf-key tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _leaf_keys(obj: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for name, value in obj.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            if isinstance(value, dict):
                keys |= _leaf_keys(value, path)
            else:
                keys.add(path)
    return keys


def test_dashboard_en_and_zh_share_leaf_keys() -> None:
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    en_keys = _leaf_keys(en)
    zh_keys = _leaf_keys(zh)
    assert en_keys - zh_keys == set()
    assert zh_keys - en_keys == set()
