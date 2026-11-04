"""Build GitHub Release download-section markdown from a version tag.

Same pattern as clash-verge-rev: interpolate TAG / VERSION into a fixed
filename table. Do not scrape the assets list.

    python3 scripts/release_download_links.py 0.9.31
    python3 scripts/release_download_links.py v0.9.31
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

GITHUB_REPO = "TencentCloud/Octop"
DOWNLOAD_BASE = f"https://github.com/{GITHUB_REPO}/releases/download"


def split_tag(raw: str) -> tuple[str, str]:
    """Return ``(tag, version)`` — tag always has a leading ``v``."""
    text = raw.strip()
    if not text:
        raise ValueError("version is empty")
    version = text[1:] if text.startswith("v") else text
    return f"v{version}", version


def asset_url(tag: str, filename: str) -> str:
    return f"{DOWNLOAD_BASE}/{tag}/{filename}"


def md_link(label: str, tag: str, filename: str) -> str:
    return f"[{label}]({asset_url(tag, filename)})"


def desktop_name(os_name: str, arch: str, version: str, ext: str) -> str:
    return f"Octop-desktop-{os_name}-{arch}-{version}.{ext}"


def portable_name(os_name: str, arch: str, version: str) -> str:
    return f"Octop-portable-{os_name}-{arch}-{version}.zip"


def fnos_assets(version: str) -> tuple[tuple[str, str], ...]:
    """FnOS download links in release-page order."""
    return (
        (f"Octop-fnos-docker-lite-{version}.fpk", "Docker lite (x86 and ARM)"),
        (
            f"Octop-fnos-docker-{version}.fpk",
            "Docker full (desktop, OCR, local models; x86 and ARM)",
        ),
        (f"Octop-fnos-native-amd64-{version}.fpk", "Native x86_64"),
        (f"Octop-fnos-native-arm64-{version}.fpk", "Native ARM64 (no Docker)"),
    )


def docker_image_section(version: str, *, lite: bool) -> str:
    lines = [
        "### Docker image",
        "",
        f"- Full: `ghcr.io/tencentcloud/octop:{version}` (`:latest`)",
    ]
    if lite:
        lines.append(f"- Lite: `ghcr.io/tencentcloud/octop:{version}-lite` (`:lite`)")
    return "\n".join(lines)


def fnos_section(version: str, present: set[str] | None) -> str:
    """Return the fnOS block. ``present is None`` keeps every package."""
    tag, _version = split_tag(version)
    links = [
        md_link(label, tag, filename)
        for filename, label in fnos_assets(version)
        if present is None or filename in present
    ]
    if not links:
        return ""
    return "### fnOS NAS\n- " + " | ".join(links)


def render_download_section(raw_version: str) -> str:
    tag, version = split_tag(raw_version)
    win64 = md_link("64-bit (Recommended)", tag, desktop_name("windows", "amd64", version, "exe"))
    win_arm = md_link("ARM64", tag, desktop_name("windows", "arm64", version, "exe"))
    win64_zip = md_link("64-bit", tag, portable_name("windows", "amd64", version))
    win_arm_zip = md_link("ARM64", tag, portable_name("windows", "arm64", version))
    mac_arm = md_link("Apple Silicon", tag, desktop_name("darwin", "arm64", version, "dmg"))
    mac_intel = md_link("Intel", tag, desktop_name("darwin", "amd64", version, "dmg"))
    mac_arm_zip = md_link("Apple Silicon", tag, portable_name("darwin", "arm64", version))
    mac_intel_zip = md_link("Intel", tag, portable_name("darwin", "amd64", version))
    linux64 = md_link("64-bit", tag, desktop_name("linux", "amd64", version, "tar.gz"))
    linux_arm = md_link("ARM64", tag, desktop_name("linux", "arm64", version, "tar.gz"))
    linux64_zip = md_link("64-bit", tag, portable_name("linux", "amd64", version))
    linux_arm_zip = md_link("ARM64", tag, portable_name("linux", "arm64", version))
    return "\n".join(
        [
            "",
            "## Downloads",
            "",
            "### Windows",
            "",
            "#### Desktop installer (Recommended)",
            f"- {win64} | {win_arm}",
            "",
            "#### Portable",
            f"- {win64_zip} | {win_arm_zip}",
            "",
            "### macOS",
            "",
            "#### Desktop installer (Recommended)",
            f"- {mac_arm} | {mac_intel}",
            "",
            "#### Portable",
            f"- {mac_arm_zip} | {mac_intel_zip}",
            "",
            "### Linux",
            "",
            "#### Desktop installer (Recommended)",
            f"- {linux64} | {linux_arm}",
            "",
            "#### Portable",
            f"- {linux64_zip} | {linux_arm_zip}",
            "",
            docker_image_section(version, lite=True),
            "",
            fnos_section(version, None),
            "",
        ]
    )


def _replace_section(body: str, heading: str, replacement: str) -> str:
    """Replace one ``###`` block. An empty replacement removes that block."""
    marker = f"### {heading}\n"
    start = body.find(marker)
    if start < 0:
        if not replacement.strip():
            return body
        return body.rstrip() + "\n\n" + replacement.strip() + "\n"
    rest_at = start + len(marker)
    consumed = 0
    for line in body[rest_at:].splitlines(keepends=True):
        if line.startswith("## ") or line.startswith("### "):
            break
        consumed += len(line)
    end = rest_at + consumed
    prefix = body[:start].rstrip()
    suffix = body[end:].lstrip("\n")
    parts = [part for part in (prefix, replacement.strip(), suffix) if part]
    return "\n\n".join(parts) + "\n"


def patch_release_body(body: str, raw_version: str, present: Iterable[str]) -> str:
    """Keep desktop links, and keep only the FnOS packages that were uploaded.

    The lite image line follows the lite FnOS package: that tag is published
    only when both CPU architectures exist, which is also when the package is built.
    """
    _tag, version = split_tag(raw_version)
    names = {Path(name).name for name in present}
    lite_name = f"Octop-fnos-docker-lite-{version}.fpk"
    updated = _replace_section(
        body, "Docker image", docker_image_section(version, lite=lite_name in names)
    )
    return _replace_section(updated, "fnOS NAS", fnos_section(version, names))


def _asset_names(payload: dict[str, object]) -> list[str]:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("release JSON has no assets list")
    names: list[str] = []
    for asset in assets:
        if isinstance(asset, str):
            names.append(asset)
            continue
        if isinstance(asset, dict) and isinstance(asset.get("name"), str):
            names.append(asset["name"])
            continue
        raise ValueError("release asset is missing a name")
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print Octop GitHub Release download markdown.")
    parser.add_argument("version", help="Package version, with or without a leading v")
    parser.add_argument(
        "--sync-notes",
        type=Path,
        help="Rewrite Docker/fnOS sections from a `gh release view --json body,assets` file.",
    )
    args = parser.parse_args(argv)
    if args.sync_notes is None:
        sys.stdout.write(render_download_section(args.version))
        return 0
    payload = json.loads(args.sync_notes.read_text(encoding="utf-8"))
    body = payload.get("body")
    if not isinstance(body, str):
        raise ValueError("release JSON has no body")
    sys.stdout.write(patch_release_body(body, args.version, _asset_names(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
