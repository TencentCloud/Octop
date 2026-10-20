"""Tests for package version resolution."""

from __future__ import annotations

import re
from pathlib import Path

from octop_harness import __version__ as package_version
from octop_harness._version import __version__ as module_version


def _pyproject_version() -> str:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert match is not None
    return match.group(1)


def test_version_matches_pyproject() -> None:
    expected = _pyproject_version()
    assert module_version == expected
    assert package_version == expected
    assert module_version != "0.0.0+unknown"
