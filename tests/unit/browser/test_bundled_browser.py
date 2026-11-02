"""Bundled Chromium stays off until the user confirms."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.control.browser.bundled import (
    browser_enabled,
    bundled_browser,
    confirm_browser_enabled,
)


def test_missing_marker_is_already_enabled(tmp_path: Path) -> None:
    marker = tmp_path / "missing.json"
    assert bundled_browser(marker) is False
    assert browser_enabled(marker=marker, root=tmp_path) is True


def test_bundled_browser_requires_confirm(tmp_path: Path) -> None:
    marker = tmp_path / "bundled.json"
    marker.write_text(json.dumps({"browser": True}), encoding="utf-8")
    home = tmp_path / "home"
    assert browser_enabled(marker=marker, root=home) is False
    confirm_browser_enabled(home, marker=marker)
    assert (home / "browser.enabled").is_file()
    assert browser_enabled(marker=marker, root=home) is True


def test_confirm_is_a_noop_without_a_bundled_browser(tmp_path: Path) -> None:
    home = tmp_path / "home"
    confirm_browser_enabled(home, marker=tmp_path / "missing.json")
    assert not (home / "browser.enabled").exists()
