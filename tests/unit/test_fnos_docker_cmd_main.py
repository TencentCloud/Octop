"""FnOS Docker `cmd/main` must resolve its paths when TRIM_APPDEST is absent.

`scripts/fnos/common.sh:9` turns on `set -u`, and `scripts/build-fpk.sh:130`
copies that file into the package as `cmd/common.sh`, which `cmd/main` sources
before using any FnOS-provided variable.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash lifecycle scripts")

REPO = Path(__file__).resolve().parents[2]
FNOS_DOCKER = REPO / "fnos" / "docker"
MAIN = FNOS_DOCKER / "cmd" / "main"
COMPOSE = FNOS_DOCKER / "app" / "docker" / "docker-compose.yaml"
COMMON_SH = REPO / "scripts" / "fnos" / "common.sh"


def _install_package(tmp_path: Path) -> Path:
    """Recreate the cmd/ layout that scripts/build-fpk.sh ships inside the .fpk."""
    cmd = tmp_path / "cmd"
    cmd.mkdir()
    shutil.copy(MAIN, cmd / "main")
    shutil.copy(COMMON_SH, cmd / "common.sh")
    docker_dir = tmp_path / "target" / "docker"
    docker_dir.mkdir(parents=True)
    shutil.copy(COMPOSE, docker_dir / "docker-compose.yaml")
    return cmd


def _run_status(cmd_dir: Path, appdest: str | None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("TRIM_APPDEST", None)
    if appdest is not None:
        env["TRIM_APPDEST"] = appdest
    return subprocess.run(
        ["bash", str(cmd_dir / "main"), "status"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


@posix_only
def test_status_survives_missing_trim_appdest(tmp_path: Path) -> None:
    cmd_dir = _install_package(tmp_path)
    result = _run_status(cmd_dir, appdest=None)
    assert "unbound variable" not in result.stderr, result.stderr
    assert result.returncode in {0, 3}, result.stderr


@posix_only
def test_status_matches_explicit_appdest(tmp_path: Path) -> None:
    cmd_dir = _install_package(tmp_path)
    missing = _run_status(cmd_dir, appdest=None)
    explicit = _run_status(cmd_dir, appdest=str(tmp_path / "target"))
    assert explicit.returncode in {0, 3}, explicit.stderr
    assert missing.returncode == explicit.returncode


def test_no_fnos_cmd_expands_trim_vars_without_fallback() -> None:
    bare = re.compile(r"\$\{TRIM_[A-Z0-9_]+\}")
    offenders: list[str] = []
    for script in sorted(REPO.glob("fnos/*/cmd/*")):
        if not script.is_file():
            continue
        for lineno, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            if bare.search(line):
                offenders.append(f"{script.relative_to(REPO)}:{lineno}: {line.strip()}")
    assert not offenders, "cmd scripts run under `set -u` from common.sh: " + "; ".join(offenders)
