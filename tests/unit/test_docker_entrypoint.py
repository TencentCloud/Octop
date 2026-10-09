"""Docker entrypoint: password policy + setup-wizard fallback (no silent admin swap)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from octop.infra.errors import OctopError
from octop.infra.setup.password_file import read_password
from octop.infra.users.password import _COMMON_PASSWORDS, validate_password_policy

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash entrypoint helpers")

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


@posix_only
@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("Str0ngPass!", True),
        ("WizardPass1", True),
        ("", False),
        ("Ab1", False),
        ("abcdefgh", False),
        ("12345678", False),
        ("password1", False),
        ("Octop123", False),
        ("ADMIN123", False),
    ],
)
def test_entrypoint_validate_password_matches_policy(password: str, ok: bool) -> None:
    script = _source_helpers() + f"\noctop_validate_password {password!r}\n"
    result = _bash(script)
    if ok:
        validate_password_policy(password)
        assert result.returncode == 0, result.stderr
    else:
        if password:
            with pytest.raises(OctopError):
                validate_password_policy(password)
        assert result.returncode != 0


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
