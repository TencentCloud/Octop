"""Portable launcher scripts must not persist bind overrides (issue #1816).

``octop run --host/--port`` writes the flags into config.json, so a launcher
that unconditionally passes its defaults rewrites a hand-edited ``bind_host``
on every start. ``desktop/portable/templates/start.sh`` must therefore only
forward ``--host``/``--port`` when the user passed them explicitly.

The tests run the real script with a stubbed portable Python on a tmp ROOT,
so nothing is started and no repo file is written.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
START_SH = REPO_ROOT / "desktop" / "portable" / "templates" / "start.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="requires bash")

PY_STUB = """#!/bin/sh
printf 'ARGV %s\\n' "$*" > "$LAUNCH_STUB_LOG"
"""


def _run_launcher(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], str]:
    root = tmp_path / "green"
    (root / "runtime" / "bin").mkdir(parents=True)
    py = root / "runtime" / "bin" / "python3"
    py.write_text(PY_STUB, encoding="utf-8")
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    shutil.copy(START_SH, root / "start.sh")
    log = tmp_path / "argv.log"
    env = dict(os.environ)
    env["OCTOP_HOME"] = str(tmp_path / "home")
    env["LAUNCH_STUB_LOG"] = str(log)
    result = subprocess.run(
        [str(BASH), str(root / "start.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    argv_log = log.read_text(encoding="utf-8") if log.exists() else ""
    return result, argv_log


def test_default_launch_passes_no_host_or_port(tmp_path: Path) -> None:
    result, argv_log = _run_launcher(tmp_path)

    assert result.returncode == 0, result.stderr
    assert argv_log.strip().endswith("launch.py run"), argv_log
    assert "--host" not in argv_log
    assert "--port" not in argv_log


def test_explicit_host_and_port_are_forwarded(tmp_path: Path) -> None:
    result, argv_log = _run_launcher(tmp_path, "--host", "0.0.0.0", "--port", "9001")

    assert result.returncode == 0, result.stderr
    assert argv_log.strip().endswith("launch.py run --host 0.0.0.0 --port 9001"), argv_log


def test_unset_host_keeps_port_only(tmp_path: Path) -> None:
    result, argv_log = _run_launcher(tmp_path, "--port", "9002")

    assert result.returncode == 0, result.stderr
    assert argv_log.strip().endswith("launch.py run --port 9002"), argv_log
