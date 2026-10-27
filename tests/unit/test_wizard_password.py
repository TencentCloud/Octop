"""Unit tests for the wizard password file lifecycle."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from octop.infra.setup.password_file import (
    WIZARD_FILE_NAME,
    boot_self_heal,
    ensure_password,
    read_password,
    resolve_password_path,
)


def _file(home: Path) -> Path:
    return home / WIZARD_FILE_NAME


def test_ensure_password_writes_file_when_missing(tmp_path: Path) -> None:
    pw = ensure_password(tmp_path)
    assert pw is not None
    assert _file(tmp_path).read_text(encoding="utf-8").strip() == pw
    assert len(pw) >= 20  # token_urlsafe(16) ≈ 22 chars


def test_ensure_password_returns_none_when_present(tmp_path: Path) -> None:
    first = ensure_password(tmp_path)
    second = ensure_password(tmp_path)
    assert first is not None
    assert second is None
    assert _file(tmp_path).read_text(encoding="utf-8").strip() == first


def test_file_mode_is_0600(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX file mode bits")
    ensure_password(tmp_path)
    mode = stat.S_IMODE(os.stat(_file(tmp_path)).st_mode)
    assert mode == 0o600


def test_read_password_returns_stored_value(tmp_path: Path) -> None:
    pw = ensure_password(tmp_path)
    assert read_password(tmp_path) == pw


def test_read_password_returns_none_when_missing(tmp_path: Path) -> None:
    assert read_password(tmp_path) is None


def test_boot_self_heal_generates_when_no_users(tmp_path: Path) -> None:
    pw = boot_self_heal(tmp_path, user_count=0)
    assert pw is not None
    assert _file(tmp_path).exists()


def test_boot_self_heal_redisplays_existing_password_with_no_users(tmp_path: Path) -> None:
    first = boot_self_heal(tmp_path, user_count=0)
    second = boot_self_heal(tmp_path, user_count=0)
    assert first is not None
    assert second == first
    assert read_password(tmp_path) == first


def test_boot_self_heal_keeps_file_when_users_exist(tmp_path: Path) -> None:
    ensure_password(tmp_path)
    pw = boot_self_heal(tmp_path, user_count=1)
    assert pw is None
    assert _file(tmp_path).exists()


def test_boot_self_heal_no_op_when_users_exist_and_no_file(tmp_path: Path) -> None:
    pw = boot_self_heal(tmp_path, user_count=1)
    assert pw is None
    assert not _file(tmp_path).exists()


def test_resolve_password_path_prefers_primary(tmp_path: Path) -> None:
    primary_home = tmp_path / "octop_home"
    legacy_home = tmp_path / "legacy_user_home"
    primary_home.mkdir()
    legacy_home.mkdir()
    (primary_home / WIZARD_FILE_NAME).write_text("primary-pw\n", encoding="utf-8")
    (legacy_home / WIZARD_FILE_NAME).write_text("legacy-pw\n", encoding="utf-8")

    assert (
        resolve_password_path(primary_home, legacy_home=legacy_home)
        == primary_home / WIZARD_FILE_NAME
    )


def test_resolve_password_path_falls_back_to_legacy(tmp_path: Path) -> None:
    primary_home = tmp_path / "octop_home"
    legacy_home = tmp_path / "legacy_user_home"
    legacy_home.mkdir()
    (legacy_home / WIZARD_FILE_NAME).write_text("legacy-pw\n", encoding="utf-8")

    assert (
        resolve_password_path(primary_home, legacy_home=legacy_home)
        == legacy_home / WIZARD_FILE_NAME
    )


def test_read_password_falls_back_to_legacy_home(tmp_path: Path) -> None:
    primary_home = tmp_path / "octop_home"
    legacy_home = tmp_path / "legacy_user_home"
    legacy_home.mkdir()
    (legacy_home / WIZARD_FILE_NAME).write_text("legacy-secret-123\n", encoding="utf-8")

    assert read_password(primary_home, legacy_home=legacy_home) == "legacy-secret-123"


def test_ensure_password_migrates_legacy_secret(tmp_path: Path) -> None:
    primary_home = tmp_path / "octop_home"
    legacy_home = tmp_path / "legacy_user_home"
    legacy_home.mkdir()
    (legacy_home / WIZARD_FILE_NAME).write_text("legacy-secret-123\n", encoding="utf-8")

    pw = ensure_password(primary_home, legacy_home=legacy_home)
    assert pw == "legacy-secret-123"
    assert (primary_home / WIZARD_FILE_NAME).read_text(
        encoding="utf-8"
    ).strip() == "legacy-secret-123"


def test_boot_self_heal_migrates_legacy_secret(tmp_path: Path) -> None:
    primary_home = tmp_path / "octop_home"
    legacy_home = tmp_path / "legacy_user_home"
    legacy_home.mkdir()
    (legacy_home / WIZARD_FILE_NAME).write_text("legacy-secret-456\n", encoding="utf-8")

    pw = boot_self_heal(primary_home, user_count=0, legacy_home=legacy_home)
    assert pw == "legacy-secret-456"
    assert (primary_home / WIZARD_FILE_NAME).read_text(
        encoding="utf-8"
    ).strip() == "legacy-secret-456"


# --- Windows ACL restriction (#2370) ---------------------------------------


class _FakeIcacls:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._returncode = returncode

    def __call__(self, cmd: list[str], **_kwargs: object) -> object:
        self.calls.append(cmd)

        class _Proc:
            returncode = self._returncode
            stderr = b"refused"

        return _Proc()


def test_windows_restriction_runs_icacls_with_owner_and_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import password_file as pf

    target = tmp_path / WIZARD_FILE_NAME
    target.write_text("pw\n", encoding="utf-8")
    fake = _FakeIcacls()
    monkeypatch.setattr(pf, "_IS_WINDOWS", True)
    monkeypatch.setattr(pf.subprocess, "run", fake)
    monkeypatch.setenv("USERNAME", "octopTester")
    monkeypatch.delenv("USERDOMAIN", raising=False)

    pf._restrict_permissions(target)

    assert len(fake.calls) == 1
    cmd = fake.calls[0]
    assert cmd[0] == "icacls"
    assert str(target) in cmd
    assert "/inheritance:r" in cmd
    assert "octopTester:F" in cmd
    assert "*S-1-5-18:F" in cmd  # LOCAL SYSTEM


def test_windows_restriction_qualifies_domain_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import password_file as pf

    target = tmp_path / WIZARD_FILE_NAME
    target.write_text("pw\n", encoding="utf-8")
    fake = _FakeIcacls()
    monkeypatch.setattr(pf, "_IS_WINDOWS", True)
    monkeypatch.setattr(pf.subprocess, "run", fake)
    monkeypatch.setenv("USERNAME", "octopTester")
    monkeypatch.setenv("USERDOMAIN", "CORP")

    pf._restrict_permissions(target)

    assert "CORP\\octopTester:F" in fake.calls[0]


def test_windows_icacls_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ACL hardening must never break password creation."""
    from octop.infra.setup import password_file as pf

    target = tmp_path / WIZARD_FILE_NAME
    target.write_text("pw\n", encoding="utf-8")
    monkeypatch.setattr(pf, "_IS_WINDOWS", True)
    monkeypatch.setattr(pf.subprocess, "run", _FakeIcacls(returncode=1))

    pf._restrict_permissions(target)  # no raise


def test_windows_ensure_password_routes_through_icacls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.setup import password_file as pf

    fake = _FakeIcacls()
    monkeypatch.setattr(pf, "_IS_WINDOWS", True)
    monkeypatch.setattr(pf.subprocess, "run", fake)
    monkeypatch.setenv("USERNAME", "octopTester")
    monkeypatch.delenv("USERDOMAIN", raising=False)

    pw = pf.ensure_password(tmp_path)

    assert pw is not None
    assert len(fake.calls) == 1
    assert str(_file(tmp_path)) in fake.calls[0]


def test_posix_restriction_keeps_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.infra.setup.password_file as pf

    monkeypatch.setattr(pf, "_IS_WINDOWS", False)
    target = tmp_path / WIZARD_FILE_NAME
    target.write_text("pw\n", encoding="utf-8")
    pf._restrict_permissions(target)
    if os.name == "posix":
        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert mode == 0o600
