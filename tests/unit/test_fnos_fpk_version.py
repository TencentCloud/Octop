"""``scripts/build-fpk.sh`` must resolve a PEP 440 prerelease version.

Regression guard for 494a921 ("fix(fnos): parse prerelease versions for FPK
builds"). The .fpk version comes from ``pyproject.toml`` through a sed pattern
that used to accept only digits and dots. A prerelease such as ``1.0.2b1`` (the
version on ``develop`` and the tag ``v1.0.2b1``) did not match, and because sed
passes a non-matching line through unchanged, ``$VER`` became the whole
``version = "1.0.2b1"`` line. The ``[ -n "$VER" ]`` guard on the next line only
rejects an empty value, so packaging continued and produced
``Octop-fnos-docker-version = "1.0.2b1".fpk`` whose manifest reads
``version = version = "1.0.2b1"``.

The pattern is read back out of the script rather than duplicated here, so this
fails if the parse ever regresses and cannot drift from the shipped line.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_BUILD_FPK_SH = _REPO / "scripts" / "build-fpk.sh"


def _find_bash() -> str | None:
    """Locate a working bash. CI runs on Linux/Windows; skip when unusable."""
    for cand in (os.environ.get("BASH"), shutil.which("bash")):
        if cand and Path(cand).exists():
            return cand
    # Windows fallback: Git for Windows ships bash next to git.
    for cand in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if Path(cand).exists():
            return cand
    return None


_BASH = _find_bash()

requires_bash = pytest.mark.skipif(_BASH is None, reason="bash not available on this host")


def _to_posix(p: Path) -> str:
    """Convert D:\\dir\\x to /d/dir/x so MSYS bash resolves it."""
    s = str(p).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        s = "/" + s[0].lower() + s[2:]
    return s


def _version_line() -> str:
    """The real ``VER=`` assignment from the script, so the test cannot drift."""
    lines = _BUILD_FPK_SH.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith('VER="'):
            # Follow shell line continuations so reformatting cannot break this.
            while line.endswith("\\") and index + 1 < len(lines):
                line = line[:-1] + " " + lines[index + 1].strip()
                index += 1
            return line
    raise AssertionError(f"{_BUILD_FPK_SH} no longer assigns VER=")


def _resolve_version(tmp_path: Path, version: str) -> str:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(f'[project]\nname = "octop"\nversion = "{version}"\n')
    script = "\n".join(
        [
            "set -euo pipefail",
            f'ROOT="{_to_posix(root)}"',
            _version_line(),
            'printf "%s" "$VER"',
        ]
    )
    assert _BASH is not None
    done = subprocess.run([_BASH, "-c", script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@requires_bash
@pytest.mark.parametrize(
    "version",
    ["1.0.1", "1.0.2", "1.0.2b1", "1.0.2rc1", "0.9.35"],
)
def test_build_fpk_resolves_pyproject_version(tmp_path: Path, version: str) -> None:
    assert _resolve_version(tmp_path, version) == version


@requires_bash
def test_resolved_version_is_safe_for_filenames_and_manifest(tmp_path: Path) -> None:
    """$VER is interpolated into the .fpk file name and a key=value manifest."""
    ver = _resolve_version(tmp_path, "1.0.2b1")
    assert re.fullmatch(r"[0-9]+(\.[0-9]+)*[0-9A-Za-z.\-+]*", ver), (
        f"resolved version {ver!r} must be a bare version token: no spaces, "
        "quotes or '=' may reach the file name or the fnOS manifest"
    )
