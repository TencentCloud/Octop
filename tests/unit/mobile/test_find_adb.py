"""Unit tests for adb discovery (PATH + SDK env only)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from octop.infra.mobile.adb import find_adb


def test_find_adb_prefers_path() -> None:
    with (
        patch("octop.infra.mobile.adb.shutil.which", return_value="/usr/bin/adb"),
        patch.dict("os.environ", {"ANDROID_HOME": "/sdk"}, clear=False),
    ):
        assert find_adb() == "/usr/bin/adb"


def test_find_adb_from_android_home(tmp_path: Path) -> None:
    tools = tmp_path / "platform-tools"
    tools.mkdir()
    adb = tools / ("adb.exe" if os.name == "nt" else "adb")
    adb.write_text("", encoding="utf-8")
    with (
        patch("octop.infra.mobile.adb.shutil.which", return_value=None),
        patch.dict(
            "os.environ",
            {"ANDROID_HOME": str(tmp_path), "ANDROID_SDK_ROOT": ""},
            clear=False,
        ),
    ):
        assert find_adb() == str(adb)


def test_find_adb_from_android_sdk_root(tmp_path: Path) -> None:
    tools = tmp_path / "platform-tools"
    tools.mkdir()
    adb = tools / ("adb.exe" if os.name == "nt" else "adb")
    adb.write_text("", encoding="utf-8")
    with (
        patch("octop.infra.mobile.adb.shutil.which", return_value=None),
        patch.dict(
            "os.environ",
            {"ANDROID_HOME": "", "ANDROID_SDK_ROOT": str(tmp_path)},
            clear=False,
        ),
    ):
        assert find_adb() == str(adb)


def test_find_adb_missing_returns_none() -> None:
    with (
        patch("octop.infra.mobile.adb.shutil.which", return_value=None),
        patch.dict(
            "os.environ",
            {"ANDROID_HOME": "", "ANDROID_SDK_ROOT": ""},
            clear=False,
        ),
    ):
        assert find_adb() is None


def test_find_adb_ignores_empty_env_roots() -> None:
    with (
        patch("octop.infra.mobile.adb.shutil.which", return_value=None),
        patch.dict(
            "os.environ",
            {"ANDROID_HOME": "   ", "ANDROID_SDK_ROOT": ""},
            clear=False,
        ),
    ):
        assert find_adb() is None
