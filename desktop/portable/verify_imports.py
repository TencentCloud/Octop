#!/usr/bin/env python3
"""Smoke-check a green packages/ tree against frozen requirements.

Usage:
  python desktop/portable/verify_imports.py \\
    --packages desktop/portable/release/Octop-<plat>/packages \\
    --requirements desktop/portable/requirements-<plat>.txt \\
    [--overrides desktop/portable/overrides-<plat>.txt]
"""
from __future__ import annotations

import argparse
import ast
import importlib
import re
import site
import sys
from pathlib import Path

_REQ_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\s*==\s*(?P<ver>[^\s;#]+))?"
)

# Import names that have historically drifted across lock/install environments.
_SMOKE_IMPORTS = (
    "octop",
    "fastapi",
    "cryptography.fernet",
    "langchain_core",
    "langchain_openai",
)


def _parse_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = _REQ_RE.match(line)
        if match is None:
            continue
        name = match.group("name").replace("_", "-").lower()
        ver = match.group("ver")
        if ver:
            pins[name] = ver
    return pins


def _parse_override_pins(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ";" in line:
            continue
        match = _REQ_RE.match(line)
        if match is None or not match.group("ver"):
            continue
        pins[match.group("name").replace("_", "-").lower()] = match.group("ver")
    return pins


def _installed_version(mod_name: str) -> str | None:
    try:
        mod = importlib.import_module(mod_name)
    except Exception:
        return None
    ver = getattr(mod, "__version__", None)
    if isinstance(ver, str):
        return ver
    return None


def _dist_version(dist_name: str) -> str | None:
    try:
        from importlib.metadata import version
    except ImportError:
        return None
    try:
        return version(dist_name)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--overrides", type=Path, default=None)
    args = parser.parse_args()

    packages = args.packages.resolve()
    if not packages.is_dir():
        print(f"packages/ missing: {packages}", file=sys.stderr)
        return 1
    site.addsitedir(str(packages))

    req_pins = _parse_pins(args.requirements)
    override_pins = _parse_override_pins(args.overrides)
    pins = {**req_pins, **override_pins}

    errors: list[str] = []
    for dist in ("langchain-core", "langchain-openai", "cryptography"):
        expected = pins.get(dist)
        if expected is None:
            continue
        got = _dist_version(dist)
        if got is None:
            errors.append(f"{dist}: not installed (want {expected})")
        elif got != expected:
            errors.append(f"{dist}: installed {got}, want {expected}")

    for mod in _SMOKE_IMPORTS:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            errors.append(f"import {mod}: {type(exc).__name__}: {exc}")

    # Sanity: launch.py must stay importable as a file (no compile errors).
    try:
        ast.parse(Path(__file__).read_text(encoding="utf-8"))
    except SyntaxError as exc:
        errors.append(f"self-parse: {exc}")

    if errors:
        print("verify_imports FAILED:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_imports OK")
    langchain_core_ver = _installed_version("langchain_core")
    if langchain_core_ver:
        print(f"langchain_core={langchain_core_ver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
