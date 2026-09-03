"""tests/unit/test_release_download_links.py"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_download_links.py"


def _load():
    spec = importlib.util.spec_from_file_location("release_download_links", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_split_tag_accepts_with_or_without_v() -> None:
    mod = _load()
    assert mod.split_tag("0.9.31") == ("v0.9.31", "0.9.31")
    assert mod.split_tag("v0.9.31") == ("v0.9.31", "0.9.31")


def test_render_download_section_matches_github_asset_names() -> None:
    mod = _load()
    body = mod.render_download_section("0.9.31")
    base = "https://github.com/TencentCloud/Octop/releases/download/v0.9.31"
    assert f"{base}/Octop-desktop-windows-amd64-0.9.31.exe" in body
    assert f"{base}/Octop-desktop-windows-arm64-0.9.31.exe" in body
    assert f"{base}/Octop-portable-windows-amd64-0.9.31.zip" in body
    assert f"{base}/Octop-portable-windows-arm64-0.9.31.zip" in body
    assert f"{base}/Octop-desktop-darwin-arm64-0.9.31.dmg" in body
    assert f"{base}/Octop-desktop-darwin-amd64-0.9.31.dmg" in body
    assert f"{base}/Octop-portable-darwin-arm64-0.9.31.zip" in body
    assert f"{base}/Octop-portable-darwin-amd64-0.9.31.zip" in body
    assert f"{base}/Octop-desktop-linux-amd64-0.9.31.tar.gz" in body
    assert f"{base}/Octop-desktop-linux-arm64-0.9.31.tar.gz" in body
    assert f"{base}/Octop-portable-linux-amd64-0.9.31.zip" in body
    assert f"{base}/Octop-portable-linux-arm64-0.9.31.zip" in body
    assert f"{base}/Octop-fnos-docker-0.9.31.fpk" in body
    assert f"{base}/Octop-fnos-native-0.9.31.fpk" in body
    assert "pip install" not in body
    assert "## 下载地址" in body
