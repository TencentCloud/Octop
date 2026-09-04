"""Tests for desktop Wails version stamping."""

from __future__ import annotations

import importlib.util
import json
import plistlib
from pathlib import Path

_STAMP = Path(__file__).resolve().parents[3] / "desktop" / "src" / "build" / "stamp_version.py"
_SPEC = importlib.util.spec_from_file_location("octop_desktop_stamp_version", _STAMP)
assert _SPEC is not None and _SPEC.loader is not None
stamp_version = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stamp_version)


def test_stamp_plist_sets_bundle_versions(tmp_path: Path) -> None:
    src = (
        Path(__file__).resolve().parents[3] / "desktop" / "src" / "build" / "darwin" / "Info.plist"
    )
    dest = tmp_path / "Info.plist"
    dest.write_bytes(src.read_bytes())
    stamp_version.stamp_plist(dest, "1.2.3")
    data = plistlib.loads(dest.read_bytes())
    assert data["CFBundleVersion"] == "1.2.3"
    assert data["CFBundleShortVersionString"] == "1.2.3"
    assert data["LSMinimumSystemVersion"] == "12.0.0"


def test_stamp_plist_skips_dev_placeholder(tmp_path: Path) -> None:
    dest = tmp_path / "Info.plist"
    dest.write_bytes(
        plistlib.dumps({"CFBundleVersion": "0.9.31", "CFBundleShortVersionString": "0.9.31"})
    )
    stamp_version.stamp_plist(dest, "dev")
    data = plistlib.loads(dest.read_bytes())
    assert data["CFBundleVersion"] == "0.9.31"


def test_stamp_info_json_copies_and_sets_version(tmp_path: Path) -> None:
    src = (
        Path(__file__).resolve().parents[3] / "desktop" / "src" / "build" / "windows" / "info.json"
    )
    dest = tmp_path / "info.generated.json"
    stamp_version.stamp_info_json(src, dest, "1.2.3")
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["fixed"]["file_version"] == "1.2.3"
    assert data["info"]["0000"]["ProductVersion"] == "1.2.3"
    original = json.loads(src.read_text(encoding="utf-8"))
    assert original["info"]["0000"]["CompanyName"] == data["info"]["0000"]["CompanyName"]


def test_stamp_info_json_dev_keeps_source_version(tmp_path: Path) -> None:
    src = (
        Path(__file__).resolve().parents[3] / "desktop" / "src" / "build" / "windows" / "info.json"
    )
    dest = tmp_path / "info.generated.json"
    stamp_version.stamp_info_json(src, dest, "dev")
    data = json.loads(dest.read_text(encoding="utf-8"))
    original = json.loads(src.read_text(encoding="utf-8"))
    assert data["fixed"]["file_version"] == original["fixed"]["file_version"]


def test_four_part_version_pads_semver() -> None:
    assert stamp_version.four_part_version("1.2.3") == "1.2.3.0"
    assert stamp_version.four_part_version("1.2.3.4") == "1.2.3.4"
    assert stamp_version.four_part_version("dev") is None


def test_stamp_manifest_sets_octop_identity_only(tmp_path: Path) -> None:
    src = (
        Path(__file__).resolve().parents[3]
        / "desktop"
        / "src"
        / "build"
        / "windows"
        / "wails.exe.manifest"
    )
    dest = tmp_path / "wails.exe.generated.manifest"
    stamp_version.stamp_manifest(src, dest, "1.2.3")
    text = dest.read_text(encoding="utf-8")
    assert 'name="com.tencent.octop" version="1.2.3.0"' in text
    assert 'name="Microsoft.Windows.Common-Controls" version="6.0.0.0"' in text
