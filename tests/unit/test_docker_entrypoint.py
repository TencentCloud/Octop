"""Docker entrypoint: password policy + setup-wizard fallback (no silent admin swap)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from octop.infra.errors import OctopError
from octop.infra.setup.password_file import read_password
from octop.infra.users.password import _COMMON_PASSWORDS, validate_password_policy

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash entrypoint helpers")
# Same tests, but runnable anywhere a bash is on PATH (e.g. Git Bash on Windows).
bash_exe = shutil.which("bash")
bash_only = pytest.mark.skipif(bash_exe is None, reason="requires a bash shell")

REPO = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO / "docker" / "docker-entrypoint.sh"


def _source_helpers() -> str:
    return f'OCTOP_ENTRYPOINT_LIB=1; source "{ENTRYPOINT}"'


def _bash(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
        timeout=15,
    )


@posix_only
def test_entrypoint_common_passwords_match_python() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(r'^_OCTOP_COMMON_PASSWORDS="([^"]+)"$', text, re.MULTILINE)
    assert match, "entrypoint must declare _OCTOP_COMMON_PASSWORDS"
    shell_set = set(match.group(1).split())
    assert shell_set == set(_COMMON_PASSWORDS)


_VALID_PASSWORDS = (
    "Str0ngPass!",
    "WizardPass1",
    "GoodPass1",
    "abcdefgh1",
    "A1b2c3d4",
    "MyOctop2026",
)

_INVALID_PASSWORDS = (
    "",
    "Ab1",
    "short1A",
    "abcdefgh",
    "ABCDEFGH",
    "12345678",
    "87654321",
    "password",
    "password1",
    "password12",
    "password123",
    "123456789",
    "qwerty123",
    "admin123",
    "welcome1",
    "letmein1",
    "changeme1",
    "octop123",
    "abc12345",
    "iloveyou1",
    "Octop123",
    "ADMIN123",
    "PASSWORD1",
    "Welcome1",
)


@posix_only
@pytest.mark.parametrize("password", _VALID_PASSWORDS)
def test_entrypoint_accepts_passwords_that_meet_policy(password: str) -> None:
    validate_password_policy(password)
    result = _bash(_source_helpers() + f"\noctop_validate_password {password!r}\n")
    assert result.returncode == 0, result.stderr


@posix_only
@pytest.mark.parametrize("password", _INVALID_PASSWORDS)
def test_entrypoint_rejects_passwords_that_miss_policy(password: str) -> None:
    if password:
        with pytest.raises(OctopError):
            validate_password_policy(password)
    result = _bash(_source_helpers() + f"\noctop_validate_password {password!r}\n")
    assert result.returncode != 0
    assert result.stderr.strip()


@posix_only
def test_seed_wizard_password_writes_volume_and_home_link(tmp_path: Path) -> None:
    home = tmp_path / "data"
    octop_home = home / ".octop"
    home.mkdir()
    script = _source_helpers() + "\noctop_seed_wizard_password\noctop_write_setup_hint\n"
    result = _bash(
        script,
        env={
            "HOME": str(home),
            "OCTOP_HOME": str(octop_home),
            "PORT": "8088",
        },
    )
    assert result.returncode == 0, result.stderr
    wizard = octop_home / "octop-login.txt"
    assert wizard.is_file()
    pw = wizard.read_text(encoding="utf-8").strip()
    assert pw
    assert read_password(home) == pw
    hint = (octop_home / "credential.txt").read_text(encoding="utf-8")
    assert "Setup Required" in hint
    assert pw in hint
    assert "Username:" not in hint


@posix_only
def test_entrypoint_does_not_retry_init_with_random_admin() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "改用随机密码重试" not in text
    assert "octop_start_setup_wizard" in text
    assert "不自动创建管理员" in text


def _run_first_boot(
    tmp_path: Path,
    *,
    password: str | None,
    run_init: str = "",
    args: str = "true",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    home = tmp_path / "data"
    octop_home = home / ".octop"
    home.mkdir(exist_ok=True)
    stub = (
        run_init
        or """
octop_run_init() {
  printf '%s' "$1" > "$OCTOP_HOME/init-password.txt"
  : > "$2"
  return 0
}
"""
    )
    env = {
        "HOME": str(home),
        "OCTOP_HOME": str(octop_home),
        "PORT": "8088",
        "OCTOP_ADMIN_USERNAME": "admin",
        "OCTOP_DEFAULT_PASSWORD": "" if password is None else password,
    }
    script = _source_helpers() + "\n" + stub + f"\noctop_entrypoint_main {args}\n"
    return _bash(script, env=env), octop_home


@posix_only
@pytest.mark.parametrize("password", _VALID_PASSWORDS)
def test_first_boot_valid_password_creates_admin(tmp_path: Path, password: str) -> None:
    result, octop_home = _run_first_boot(tmp_path, password=password)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (octop_home / "init-password.txt").read_text(encoding="utf-8") == password
    cred = (octop_home / "credential.txt").read_text(encoding="utf-8")
    assert "Octop Login Credential" in cred
    assert f"Password: {password}" in cred
    assert "Username: admin" in cred
    assert not (octop_home / "octop-login.txt").exists()


@posix_only
@pytest.mark.parametrize(
    "password",
    [
        None,
        "",
        "Ab1",
        "abcdefgh",
        "12345678",
        "password1",
        "Octop123",
        "ADMIN123",
    ],
)
def test_first_boot_invalid_or_missing_password_starts_wizard(
    tmp_path: Path, password: str | None
) -> None:
    result, octop_home = _run_first_boot(tmp_path, password=password)
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (octop_home / "init-password.txt").exists()
    wizard = octop_home / "octop-login.txt"
    assert wizard.is_file()
    hint = (octop_home / "credential.txt").read_text(encoding="utf-8")
    assert "Setup Required" in hint
    assert "Username:" not in hint
    if password:
        assert "未通过密码策略" in result.stdout
    else:
        assert "未设置 OCTOP_DEFAULT_PASSWORD" in result.stdout


@posix_only
def test_first_boot_init_policy_rejection_falls_back_to_wizard(tmp_path: Path) -> None:
    result, octop_home = _run_first_boot(
        tmp_path,
        password="GoodPass1",
        run_init="""
octop_run_init() {
  printf '%s\\n' "Error: password is too common" > "$2"
  return 1
}
""",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "改为启动设置向导" in result.stdout
    assert (octop_home / "octop-login.txt").is_file()
    assert "Setup Required" in (octop_home / "credential.txt").read_text(encoding="utf-8")


@posix_only
def test_first_boot_non_policy_init_failure_exits(tmp_path: Path) -> None:
    result, octop_home = _run_first_boot(
        tmp_path,
        password="GoodPass1",
        run_init="""
octop_run_init() {
  printf '%s\\n' "database is locked" > "$2"
  return 1
}
""",
    )
    assert result.returncode != 0
    assert "不是密码策略问题" in result.stderr
    assert not (octop_home / "octop-login.txt").exists()


@posix_only
def test_existing_db_skips_password_init(tmp_path: Path) -> None:
    home = tmp_path / "data"
    octop_home = home / ".octop"
    octop_home.mkdir(parents=True)
    (octop_home / "octop.db").write_text("stub", encoding="utf-8")
    result, _ = _run_first_boot(tmp_path, password="GoodPass1")
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (octop_home / "init-password.txt").exists()


@posix_only
def test_random_wizard_password_meets_policy() -> None:
    script = (
        _source_helpers()
        + """
pw="$(octop_random_password)"
printf '%s\\n' "$pw"
octop_validate_password "$pw"
"""
    )
    result = _bash(script)
    assert result.returncode == 0, result.stderr
    pw = result.stdout.strip()
    assert pw
    validate_password_policy(pw)


# ---------------------------------------------------------------------------
# Init guard across restarts (issue #1866). PostgreSQL / external backends
# never create ``octop.db`` in the data volume, so "already bootstrapped"
# must be tracked with a backend-agnostic marker written by the entrypoint
# after a successful ``octop init``.
# ---------------------------------------------------------------------------

_STUB_OCTOP = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$OCTOP_STUB_LOG"
if [ "$1" = "init" ]; then
    if [ "${OCTOP_STUB_INIT_FAIL:-0}" = "1" ]; then
        echo "unexpected database error" >&2
        exit 1
    fi
    if [ "${OCTOP_STUB_INIT_ALREADY_EXISTS:-0}" = "1" ]; then
        printf "  admin user 'octop' already exists, skipping.\n"
    fi
fi
exit 0
"""


def _init_marker(tmp_path: Path) -> Path:
    return tmp_path / "data" / ".octop" / ".initialized"


def _run_entrypoint(
    tmp_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
    args: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the real entrypoint with a stub ``octop`` on PATH; return (result, octop argv lines)."""
    assert bash_exe is not None
    home = tmp_path / "data"
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / "octop"
    if not stub.exists():
        stub.write_text(_STUB_OCTOP, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    log = tmp_path / "octop-calls.log"
    log.write_text("", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "OCTOP_HOME": str(home / ".octop"),
            "PATH": str(stub_dir) + os.pathsep + env.get("PATH", ""),
            "OCTOP_STUB_LOG": str(log),
            "OCTOP_DEFAULT_PASSWORD": "Str0ngPass1",
            "OCTOP_PORT": "8088",
        }
    )
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [bash_exe, str(ENTRYPOINT), *args],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    return result, calls


@bash_only
def test_entrypoint_restart_skips_init_for_external_db(tmp_path: Path) -> None:
    """Issue #1866: with PostgreSQL there is no octop.db; a restart must not re-run init."""
    pg_env = {
        "OCTOP_DATABASE_DRIVER": "postgresql",
        "OCTOP_DATABASE_URL": "postgresql://octop:octop@postgres:5432/octop",
    }
    first, calls = _run_entrypoint(tmp_path, extra_env=pg_env)
    assert first.returncode == 0, first.stderr
    assert any(call.startswith("init ") for call in calls), calls
    assert any(call.startswith("run --host") for call in calls), calls
    assert not (tmp_path / "data" / ".octop" / "octop.db").exists()
    assert _init_marker(tmp_path).is_file(), first.stdout

    second, calls = _run_entrypoint(tmp_path, extra_env=pg_env)
    assert second.returncode == 0, second.stderr
    assert not any(call.startswith("init") for call in calls), calls
    assert any(call.startswith("run --host") for call in calls), calls


@bash_only
def test_entrypoint_sqlite_install_skips_init_without_marker(tmp_path: Path) -> None:
    """Backward compat: an existing octop.db still short-circuits the guard."""
    octop_home = tmp_path / "data" / ".octop"
    octop_home.mkdir(parents=True)
    (octop_home / "octop.db").write_text("", encoding="utf-8")

    result, calls = _run_entrypoint(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not any(call.startswith("init") for call in calls), calls
    assert any(call.startswith("run --host") for call in calls), calls


@bash_only
def test_entrypoint_adopts_existing_admin_without_rewriting_credentials(tmp_path: Path) -> None:
    """Upgrade path: init now no-ops on an already-bootstrapped DB; the credential card must survive."""
    octop_home = tmp_path / "data" / ".octop"
    octop_home.mkdir(parents=True)
    credential = octop_home / "credential.txt"
    credential.write_text("ORIGINAL CREDENTIALS\n", encoding="utf-8")

    result, _ = _run_entrypoint(tmp_path, extra_env={"OCTOP_STUB_INIT_ALREADY_EXISTS": "1"})
    assert result.returncode == 0, result.stderr
    assert credential.read_text(encoding="utf-8") == "ORIGINAL CREDENTIALS\n"
    assert _init_marker(tmp_path).is_file()

    second, calls = _run_entrypoint(tmp_path)
    assert second.returncode == 0, second.stderr
    assert not any(call.startswith("init") for call in calls), calls


@bash_only
def test_entrypoint_init_failure_leaves_no_marker_and_retries_next_boot(tmp_path: Path) -> None:
    first, _ = _run_entrypoint(tmp_path, extra_env={"OCTOP_STUB_INIT_FAIL": "1"})
    assert first.returncode == 1, first.stdout
    assert not _init_marker(tmp_path).exists()

    second, calls = _run_entrypoint(tmp_path)
    assert second.returncode == 0, second.stderr
    assert any(call.startswith("init ") for call in calls), calls


def test_init_skip_message_couples_entrypoint_and_init_command() -> None:
    """The entrypoint greps init output for this message — keep both sides in sync."""
    marker_text = "already exists, skipping"
    assert marker_text in ENTRYPOINT.read_text(encoding="utf-8")
    init_cmd = REPO / "src" / "octop" / "cli" / "commands" / "init.py"
    assert marker_text in init_cmd.read_text(encoding="utf-8")
