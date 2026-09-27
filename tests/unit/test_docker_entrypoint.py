"""Docker entrypoint must not reinitialize a persisted non-default database."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "posix", reason="Docker entrypoint requires POSIX shell")
@pytest.mark.parametrize(
    "database_env",
    [
        {"OCTOP_DATABASE_URL": "postgresql://octop:secret@localhost/octop"},
        {"OCTOP_DATABASE_SQLITE_PATH": "custom.db"},
    ],
    ids=["postgresql", "custom-sqlite"],
)
@pytest.mark.parametrize("restored", [False, True], ids=["first-boot", "restored"])
def test_entrypoint_initializes_only_once(
    tmp_path: Path, database_env: dict[str, str], restored: bool
) -> None:
    entrypoint = Path(__file__).resolve().parents[2] / "docker" / "docker-entrypoint.sh"
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    fake_octop = bin_dir / "octop"
    fake_octop.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = init ]; then\n'
        '    if [ -f "$HOME/.octop/initialized" ]; then exit 1; fi\n'
        '    mkdir -p "$HOME/.octop"\n'
        '    touch "$HOME/.octop/initialized"\n'
        '    if [ -n "${OCTOP_DATABASE_SQLITE_PATH:-}" ]; then\n'
        '        touch "$HOME/.octop/$OCTOP_DATABASE_SQLITE_PATH"\n'
        "    fi\n"
        "fi\n"
        'printf "%s\\n" "$1" >> "$OCTOP_TEST_CALLS"\n',
        encoding="utf-8",
    )
    fake_octop.chmod(0o755)
    fake_python = bin_dir / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'if [ -f "$HOME/.octop/initialized" ]; then echo yes; else echo no; fi\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    if restored:
        (home / ".octop").mkdir(parents=True)
        (home / ".octop" / "initialized").touch()
    env = {
        **os.environ,
        **database_env,
        "HOME": str(home),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "OCTOP_DEFAULT_PASSWORD": "StrongPass123",
        "OCTOP_TEST_CALLS": str(calls),
    }

    for attempt in range(1 if restored else 3):
        result = subprocess.run(
            ["bash", str(entrypoint)], env=env, capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, result.stderr
        if attempt == 0 and not restored:
            (home / ".octop" / "credential.txt").unlink()

    expected = ["run"] if restored else ["init", "run", "run", "run"]
    assert calls.read_text(encoding="utf-8").splitlines() == expected
    assert not (home / ".octop" / "credential.txt").exists()
    assert not (home / ".octop" / "octop.db").exists()


@pytest.mark.skipif(os.name != "posix", reason="Docker entrypoint requires POSIX shell")
def test_entrypoint_does_not_initialize_when_database_probe_fails(tmp_path: Path) -> None:
    entrypoint = Path(__file__).resolve().parents[2] / "docker" / "docker-entrypoint.sh"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    python.chmod(0o755)
    octop = bin_dir / "octop"
    octop.write_text("#!/bin/sh\ntouch \"$OCTOP_TEST_CALLED\"\n", encoding="utf-8")
    octop.chmod(0o755)
    called = tmp_path / "called"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "OCTOP_TEST_CALLED": str(called),
    }

    result = subprocess.run(
        ["bash", str(entrypoint)], env=env, capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
    assert not called.exists()
