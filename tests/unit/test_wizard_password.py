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


def _saved_dacl(path: Path) -> str:
    """The file's DACL in SDDL form via ``icacls /save`` — locale-independent.

    Only the DACL is returned (the part after ``D:``), so the assertions below
    do not depend on how an individual runner renders the owner section.
    """
    import subprocess

    out = path.parent / "acl-save.txt"
    subprocess.run(
        ["icacls", str(path), "/save", str(out)],
        check=True,
        capture_output=True,
    )
    raw = out.read_bytes()
    for encoding in ("utf-16", "mbcs"):
        try:
            sddl = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        return sddl.split("D:", 1)[1]
    return raw.decode("utf-8", errors="replace").split("D:", 1)[1]


def test_windows_dacl_restricted_to_owner_system_admins(tmp_path: Path) -> None:
    """On Windows the wizard password file must not rely on ``os.chmod``:
    a plain chmod'ed file keeps its inherited DACL, so any local user that
    can reach the directory can read the plaintext password. The fix swaps
    in a protected DACL granting only SYSTEM, Administrators and the file's
    owner (#2370)."""
    if os.name != "nt":
        pytest.skip("Windows NTFS DACL")

    ensure_password(tmp_path)
    dacl = _saved_dacl(_file(tmp_path))

    # Protected: no inherited ACEs flow in from the parent directory.
    assert dacl.startswith("P")
    assert ";ID;" not in dacl
    # Exactly three full-control grantees: SYSTEM, Administrators, owner.
    assert dacl.count(";FA;;;") == 3
    assert ";FA;;;SY)" in dacl
    assert ";FA;;;BA)" in dacl
    # S-1-3-4 (Owner Rights) resolves to whoever owns the file, so the grant
    # holds even when the owner is a group such as Administrators.
    assert ";FA;;;OW)" in dacl
    for trustee in ("WD", "BU", "AU"):  # Everyone / Users / Authenticated Users
        assert f";FA;;;{trustee})" not in dacl


def test_windows_chmod_alone_leaves_dacl_unprotected(tmp_path: Path) -> None:
    """Red control for the DACL test: ``os.open(0o600)`` + ``os.chmod`` do
    not protect a file on Windows — the DACL keeps inheriting from the parent
    directory, which is the bug the fix addresses."""
    if os.name != "nt":
        pytest.skip("Windows NTFS DACL")

    fd = os.open(
        str(_file(tmp_path)),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    os.write(fd, b"pw\n")
    os.close(fd)
    os.chmod(_file(tmp_path), 0o600)

    dacl = _saved_dacl(_file(tmp_path))
    assert not dacl.startswith("P")  # still inheriting: chmod never protects


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
