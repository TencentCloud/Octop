#!/usr/bin/env python3
"""Stamp the Octop version into Wails desktop metadata copies."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import sys
from pathlib import Path

_MANIFEST_IDENTITY = re.compile(
    r'(<assemblyIdentity\b[^>]*\bname="com\.tencent\.octop"[^>]*\bversion=")[^"]+(")',
    re.IGNORECASE,
)


def should_stamp(version: str) -> bool:
    """Skip placeholders that are not a product version (NSIS needs x.y.z)."""
    return bool(version) and version != "dev"


def four_part_version(version: str) -> str | None:
    """Windows assemblyIdentity requires four numeric components."""
    parts = version.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])


def stamp_plist(path: Path, version: str) -> None:
    if not should_stamp(version):
        return
    data = plistlib.loads(path.read_bytes())
    data["CFBundleVersion"] = version
    data["CFBundleShortVersionString"] = version
    path.write_bytes(plistlib.dumps(data))


def stamp_info_json(src: Path, dest: Path, version: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    if not should_stamp(version):
        return
    data = json.loads(dest.read_text(encoding="utf-8"))
    data["fixed"]["file_version"] = version
    data["info"]["0000"]["ProductVersion"] = version
    dest.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


def stamp_manifest(src: Path, dest: Path, version: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    if not should_stamp(version):
        return
    dotted = four_part_version(version)
    if dotted is None:
        return
    text = dest.read_text(encoding="utf-8")
    updated, n = _MANIFEST_IDENTITY.subn(rf"\g<1>{dotted}\2", text, count=1)
    if n != 1:
        raise SystemExit(f"octop assemblyIdentity not found in {dest}")
    dest.write_text(updated, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    plist_p = sub.add_parser("plist", help="Set CFBundleVersion keys on a copied Info.plist")
    plist_p.add_argument("path", type=Path)
    plist_p.add_argument("version")

    json_p = sub.add_parser("json", help="Copy windows/info.json and set file/product version")
    json_p.add_argument("src", type=Path)
    json_p.add_argument("dest", type=Path)
    json_p.add_argument("version")

    man_p = sub.add_parser("manifest", help="Copy wails.exe.manifest and set assembly version")
    man_p.add_argument("src", type=Path)
    man_p.add_argument("dest", type=Path)
    man_p.add_argument("version")

    args = parser.parse_args(argv)
    if args.cmd == "plist":
        stamp_plist(args.path, args.version)
    elif args.cmd == "json":
        stamp_info_json(args.src, args.dest, args.version)
    else:
        stamp_manifest(args.src, args.dest, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
