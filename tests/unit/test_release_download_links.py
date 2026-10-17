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
    base = f"https://github.com/{mod.GITHUB_REPO}/releases/download/v0.9.31"
    assert f"{base}/wkbuddy-desktop-windows-amd64-0.9.31.exe" in body
    assert f"{base}/wkbuddy-desktop-windows-arm64-0.9.31.exe" in body
    assert f"{base}/wkbuddy-portable-windows-amd64-0.9.31.zip" in body
    assert f"{base}/wkbuddy-portable-windows-arm64-0.9.31.zip" in body
    assert f"{base}/wkbuddy-desktop-darwin-arm64-0.9.31.dmg" in body
    assert f"{base}/wkbuddy-desktop-darwin-amd64-0.9.31.dmg" in body
    assert f"{base}/wkbuddy-portable-darwin-arm64-0.9.31.zip" in body
    assert f"{base}/wkbuddy-portable-darwin-amd64-0.9.31.zip" in body
    assert f"{base}/wkbuddy-desktop-linux-amd64-0.9.31.tar.gz" in body
    assert f"{base}/wkbuddy-desktop-linux-arm64-0.9.31.tar.gz" in body
    assert f"{base}/wkbuddy-portable-linux-amd64-0.9.31.zip" in body
    assert f"{base}/wkbuddy-portable-linux-arm64-0.9.31.zip" in body
    assert "Docker (recommended; x86 and ARM)" not in body
    assert "### fnOS NAS" not in body
    assert "pip install" not in body
    assert "## Downloads" in body
