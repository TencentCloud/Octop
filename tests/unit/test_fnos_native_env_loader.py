"""The native fnOS launchers must read ``PKGVAR/.env`` as data, not as shell.

The wizard accepts an admin password verbatim (``octop_sanitize_value`` only
drops CR/LF/quote/backslash, and ``octop_validate_password`` asks for length,
one letter and one digit), and ``octop_env_set`` writes it as a bare
``KEY=value`` line.  Loading that file with ``.`` therefore re-parses whatever
the user typed: a ``$`` reference aborts the launcher under ``set -u``, a
reference to a live variable silently rewrites the password, and ``$( )`` runs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only launcher semantics")


def _find_bash() -> str | None:
    """Locate a working bash. CI runs on Linux/Windows; skip when unusable."""
    for cand in (os.environ.get("BASH"), shutil.which("bash")):
        if cand and Path(cand).exists():
            return cand
    return None


_BASH = _find_bash()
requires_bash = pytest.mark.skipif(_BASH is None, reason="bash not available on this host")

pytestmark = [posix_only, requires_bash]

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHERS = {
    "octop": REPO_ROOT / "fnos" / "native" / "app" / "bin" / "octop",
    "octop-cli": REPO_ROOT / "fnos" / "native" / "app" / "bin" / "octop-cli",
}

# Enough of scripts/fnos/common.sh for the launcher to reach the exec line:
# the packaged common.sh is injected by scripts/build-fpk.sh and is absent in a
# checkout, so the stub is what `$0/../cmd/common.sh` resolves to here.
STUB_COMMON = """\
find_python312() {
    printf '%s' "$OCTOP_STUB_PYTHON"
}
"""

STUB_PYTHON = """\
#!/bin/sh
if [ "$1" = "-c" ]; then
    exit 0
fi
printf 'ENV_VALUE=%s\\n' "$OCTOP_DEFAULT_PASSWORD"
printf 'ENV_VALUE=%s\\n' "$OCTOP_PORT"
"""


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    """Lay out an installed native package: app/bin, app/cmd, app/var, data."""
    app = tmp_path / "apps" / "octop-native"
    (app / "bin").mkdir(parents=True)
    (app / "cmd").mkdir(parents=True)
    (app / "var").mkdir(parents=True)
    stub_py = tmp_path / "python3"
    stub_py.write_text(STUB_PYTHON, encoding="utf-8")
    stub_py.chmod(0o755)
    (app / "cmd" / "common.sh").write_text(STUB_COMMON, encoding="utf-8")
    return app


def _prepare(app: Path, name: str, env_text: str, tmp_path: Path) -> Path:
    env_file = app / "var" / ".env"
    env_file.write_text(env_text, encoding="utf-8")
    # An existing database skips the first-run `octop init` branch entirely.
    home = app / "shares" / "octop-native" / "data" / ".octop"
    home.mkdir(parents=True, exist_ok=True)
    (home / "octop.db").write_text("", encoding="utf-8")
    target = app / "bin" / name
    target.write_text(LAUNCHERS[name].read_text(encoding="utf-8"), encoding="utf-8")
    return target


def run_launcher(
    app: Path, name: str, value: str, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    target = _prepare(app, name, f"OCTOP_DEFAULT_PASSWORD={value}\nOCTOP_PORT=8089\n", tmp_path)
    return _exec(target, app, tmp_path)


def _exec(target: Path, app: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    assert _BASH is not None
    return subprocess.run(
        [_BASH, str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "TRIM_APPDEST": str(app),
            "TRIM_PKGVAR": str(app / "var"),
            "OCTOP_STUB_PYTHON": str(tmp_path / "python3"),
            # TRIM_DATA_SHARE_PATHS is left unset: the launcher then falls back
            # to `$TRIM_APPDEST/shares/octop-native/data`.
        },
    )


@pytest.mark.parametrize("name", sorted(LAUNCHERS))
def test_unknown_variable_reference_does_not_abort(name: str, staged: Path, tmp_path: Path) -> None:
    result = run_launcher(staged, name, "Sun$OCTOP_NOT_SET1x", tmp_path)
    assert "unbound variable" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "ENV_VALUE=Sun$OCTOP_NOT_SET1x" in result.stdout


@pytest.mark.parametrize("name", sorted(LAUNCHERS))
def test_reference_to_a_live_variable_stays_literal(
    name: str, staged: Path, tmp_path: Path
) -> None:
    result = run_launcher(staged, name, "a$HOME-b", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ENV_VALUE=a$HOME-b" in result.stdout, result.stdout


@pytest.mark.parametrize("name", sorted(LAUNCHERS))
def test_command_substitution_is_not_executed(name: str, staged: Path, tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    result = run_launcher(staged, name, f"p$(touch {marker})w", tmp_path)
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), f".env loading executed {marker} via command substitution"
    assert f"ENV_VALUE=p$(touch {marker})w" in result.stdout, result.stdout


def test_ordinary_values_still_load(staged: Path, tmp_path: Path) -> None:
    result = run_launcher(staged, "octop", "Sunfl0wer", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ENV_VALUE=Sunfl0wer" in result.stdout
    assert "ENV_VALUE=8089" in result.stdout


def test_comments_and_malformed_lines_are_skipped(staged: Path, tmp_path: Path) -> None:
    """A hand-edited .env may carry comments or lines `.` would have run as commands."""
    target = _prepare(
        staged,
        "octop",
        "# written by the wizard\n\nOCTOP_PORT=8089\nBAD KEY=x\n1BAD=y\n"
        "OCTOP_DEFAULT_PASSWORD=Sunfl0wer\n",
        tmp_path,
    )
    result = _exec(target, staged, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "command not found" not in result.stderr, result.stderr
    assert "ENV_VALUE=8089" in result.stdout
    assert "ENV_VALUE=Sunfl0wer" in result.stdout
