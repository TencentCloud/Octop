"""Dashboard en.json / zh.json must keep the same leaf-key tree."""

from __future__ import annotations

import json
import re
from collections import Counter
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


def test_korean_bundle_keeps_keys_and_interpolation_tokens() -> None:
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    ko = json.loads((repo / "dashboard/src/locales/ko.json").read_text(encoding="utf-8"))
    tokens = re.compile(r"\{\{.*?\}\}|\$t\([^)]*\)|</?[A-Za-z][^>]*>")

    def compare(original: Any, translated: Any, path: str = "") -> None:
        assert type(original) is type(translated), path
        if isinstance(original, dict):
            assert original.keys() == translated.keys(), path
            for key, value in original.items():
                compare(value, translated[key], f"{path}.{key}")
        elif isinstance(original, list):
            assert len(original) == len(translated), path
            for index, value in enumerate(original):
                compare(value, translated[index], f"{path}[{index}]")
        elif isinstance(original, str):
            assert Counter(tokens.findall(original)) == Counter(tokens.findall(translated)), path

    compare(en, ko)
