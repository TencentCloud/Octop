"""Setup wizard password file at octop-login.txt."""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

WIZARD_FILE_NAME = "octop-login.txt"
_TOKEN_BYTES = 16
_PASSWORD_LABEL_PREFIX = "Password:"
logger = logging.getLogger(__name__)


def _restrict_file_perms(path: Path) -> None:
    """Best-effort: make *path* readable only by the current user.

    POSIX: os.chmod(0o600) — the standard, correct approach.

    Windows: Python's os.chmod does not set NTFS DACLs, so the file stays
    readable by every local user who can traverse the directory. We shell out
    to icacls with full control for the current user and SYSTEM, while
    explicitly denying inherited ACLs from the parent (inheritance:r).
    icacls ships with every supported Windows version since Vista, so it is a
    zero-dependency path. Errors are logged but do not raise — the file still
    exists with its previous permissions.
    """
    if sys.platform == "win32":
        try:
            whoami = subprocess.run(
                ["whoami"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{whoami}:F",
                    "/grant:r",
                    "SYSTEM:F",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception:
            logger.warning(
                "failed to set DACL on wizard password file %s",
                path,
                exc_info=True,
            )
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        logger.warning(
            "failed to chmod 0o600 on wizard password file %s",
            path,
            exc_info=True,
        )


def _password_path(home: Path) -> Path:
    return home / WIZARD_FILE_NAME


def resolve_password_path(home: Path, legacy_home: Path | None = None) -> Path:
    """Return the primary password file path, or the legacy path if only the latter exists."""
    primary = _password_path(home)
    if primary.exists():
        return primary
    legacy = _password_path(legacy_home or Path.home())
    if legacy != primary and legacy.is_file():
        return legacy
    return primary


def ensure_password(home: Path, legacy_home: Path | None = None) -> str | None:
    """Generate the file if missing; return password or None if present.

    If home/octop-login.txt is missing but a legacy password exists at
    legacy_home/octop-login.txt (defaulting to the OS home), reuse that
    legacy password and write it to the primary path so both locations stay
    consistent and no conflicting secret is generated.
    """
    home.mkdir(parents=True, exist_ok=True)
    target = _password_path(home)
    if target.exists():
        return None
    legacy = _password_path(legacy_home or Path.home())
    if legacy != target and legacy.is_file():
        legacy_pw = read_password(legacy.parent)
        if legacy_pw is not None:
            try:
                fd = os.open(
                    str(target),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    os.write(fd, (legacy_pw + "\n").encode("utf-8"))
                finally:
                    os.close(fd)
                _restrict_file_perms(target)
                return legacy_pw
            except FileExistsError:
                return None
    pw = secrets.token_urlsafe(_TOKEN_BYTES)
    try:
        fd = os.open(
            str(target),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return None
    try:
        os.write(fd, (pw + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    _restrict_file_perms(target)
    return pw


def read_password(home: Path, legacy_home: Path | None = None) -> str | None:
    """Return the wizard password, or None if the file is absent/empty."""
    target = resolve_password_path(home, legacy_home=legacy_home)
    if not target.exists():
        return None
    lines = target.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(_PASSWORD_LABEL_PREFIX):
            value = stripped[len(_PASSWORD_LABEL_PREFIX):].strip()
            if value:
                return value
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def boot_self_heal(home: Path, user_count: int, legacy_home: Path | None = None) -> str | None:
    """Reconcile the wizard password file at server boot.

    When setup is still open (user_count == 0), ensure a password file exists
    and return the password so the CLI can print it — including when the file
    already exists (e.g. the DB was wiped but octop-login.txt was not).

    The file is intentionally kept forever as a permanent record and is never
    deleted, even after setup completes.
    """
    if user_count > 0:
        return None
    created = ensure_password(home, legacy_home=legacy_home)
    return created if created is not None else read_password(home, legacy_home=legacy_home)
