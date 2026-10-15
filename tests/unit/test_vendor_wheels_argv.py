"""``desktop/portable/vendor-wheels.sh`` must reach ``uv pip download``.

The optional ``--overrides`` argv is built into ``extra=()`` (line 30), which stays
empty for every platform where ``write_green_overrides`` prints no override file —
that is all of them except ``windows-arm64`` and ``darwin-amd64``. Under the
script's ``set -euo pipefail`` (line 7), bash 3.2 — the default ``/bin/bash`` on
macOS, and the shell ``desktop/portable/README.md:78`` tells you to run this with —
expands an empty array as an unbound variable and aborts before ``uv`` is called.

The tests run the real script with a stubbed ``uv`` on ``PATH`` and ``GREEN_ROOT``
pointed at ``tmp_path``, so nothing is downloaded and no repo file is written.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "desktop" / "portable" / "vendor-wheels.sh"
BASH = shutil.which("bash")

# ``extra`` is empty for these; only the two override platforms add an argument.
NO_OVERRIDE_PLATS = ["darwin-arm64", "linux-amd64", "windows-amd64"]
OVERRIDE_PLATS = ["darwin-amd64"]

# The installers and packaging scripts are POSIX shell entry points.
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only shell scripts")

UV_STUB = """#!/bin/sh
printf 'CMD %s\\n' "$*" >> "$VW_STUB_LOG"
i=0
for arg in "$@"; do
  i=$((i + 1))
  printf 'ARG%d=[%s]\\n' "$i" "$arg" >> "$VW_STUB_LOG"
done
if [ "$1" = "export" ]; then
  for arg in "$@"; do
    case "$arg" in
      *.txt) : > "$arg" ;;
    esac
  done
fi
exit 0
"""


def _run_vendor(plat: str, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    assert SCRIPT.is_file(), SCRIPT
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    uv = stub_dir / "uv"
    uv.write_text(UV_STUB, encoding="utf-8")
    uv.chmod(0o755)
    log = tmp_path / "uv-stub.log"

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env.get('PATH', '')}"
    env["GREEN_ROOT"] = str(tmp_path / "green")
    env["VW_STUB_LOG"] = str(log)

    result = subprocess.run(
        [str(BASH), str(SCRIPT), plat],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    argv_log = log.read_text(encoding="utf-8") if log.exists() else ""
    return result, argv_log


@posix_only
@pytest.mark.parametrize("plat", NO_OVERRIDE_PLATS + OVERRIDE_PLATS)
def test_download_line_is_reached(plat: str, tmp_path: Path) -> None:
    result, argv_log = _run_vendor(plat, tmp_path)

    assert "unbound variable" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert any(line.startswith("CMD pip download") for line in argv_log.splitlines())


@posix_only
@pytest.mark.parametrize("plat", NO_OVERRIDE_PLATS)
def test_empty_optional_argv_adds_no_argument(plat: str, tmp_path: Path) -> None:
    result, argv_log = _run_vendor(plat, tmp_path)

    download = [line for line in argv_log.splitlines() if line.startswith("CMD pip download")]
    assert download, result.stderr
    assert "--overrides" not in download[0]
    assert "=[]" not in argv_log, argv_log


@posix_only
@pytest.mark.parametrize("plat", OVERRIDE_PLATS)
def test_override_platform_still_passes_its_file(plat: str, tmp_path: Path) -> None:
    result, argv_log = _run_vendor(plat, tmp_path)

    assert "--overrides" in argv_log
    assert f"overrides-{plat}.txt]" in argv_log
