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
    assert f"{base}/Octop-fnos-docker-lite-0.9.31.fpk" in body
    assert f"{base}/Octop-fnos-native-amd64-0.9.31.fpk" in body
    assert f"{base}/Octop-fnos-native-arm64-0.9.31.fpk" in body
    assert "ghcr.io/tencentcloud/octop:0.9.31` (`:latest`)" in body
    assert "ghcr.io/tencentcloud/octop:0.9.31-full" in body
    assert "Docker lite (x86 and ARM)" in body
    assert "Docker full (desktop, OCR, local models; x86 and ARM)" in body
    assert "Native x86_64" in body
    assert "Native ARM64 (no Docker)" in body
    assert "pip install" not in body
    assert "## Downloads" in body


def test_patch_release_body_drops_unpublished_fnos_packages() -> None:
    mod = _load()
    body = mod.render_download_section("0.9.31") + "\n## What's Changed\n\n- kept\n"
    present = [
        "Octop-fnos-docker-0.9.31.fpk",
        "Octop-fnos-native-amd64-0.9.31.fpk",
        "Octop-desktop-windows-amd64-0.9.31.exe",
    ]
    patched = mod.patch_release_body(body, "0.9.31", present)
    assert "Octop-fnos-docker-lite-0.9.31.fpk" not in patched
    assert "ghcr.io/tencentcloud/octop:0.9.31` (`:latest`)" not in patched
    assert "ghcr.io/tencentcloud/octop:0.9.31-full" in patched
    assert "Octop-fnos-docker-0.9.31.fpk" in patched
    assert "Octop-fnos-native-amd64-0.9.31.fpk" in patched
    assert "Native ARM64" not in patched
    assert "Octop-desktop-windows-amd64-0.9.31.exe" in patched
    assert "## What's Changed" in patched
    assert "- kept" in patched


def test_patch_release_body_keeps_lite_when_its_package_shipped() -> None:
    mod = _load()
    body = mod.render_download_section("0.9.31")
    names = [filename for filename, _label in mod.fnos_assets("0.9.31")]
    patched = mod.patch_release_body(body, "v0.9.31", names)
    assert patched == body if body.endswith("\n") else patched == body + "\n"
    assert "ghcr.io/tencentcloud/octop:0.9.31` (`:latest`)" in patched
    assert "ghcr.io/tencentcloud/octop:0.9.31-full" in patched
