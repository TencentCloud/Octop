"""Setup wizard password file at ``<home>/octop-login.txt``."""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path

WIZARD_FILE_NAME = "octop-login.txt"
_TOKEN_BYTES = 16
_PASSWORD_LABEL_PREFIX = "Password:"


def _password_path(home: Path) -> Path:
    return home / WIZARD_FILE_NAME


def ensure_password(home: Path) -> str | None:
    """Generate the file if missing; return password or ``None`` if present."""
    home.mkdir(parents=True, exist_ok=True)
    target = _password_path(home)
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
    os.chmod(target, 0o600)
    return pw


def read_password(home: Path) -> str | None:
    """Return the wizard password, or ``None`` if the file is absent/empty.

    Supports two layouts:
      * Plain — the password is the file's first non-empty line, as written
        by :func:`ensure_password`.
      * Labeled — a ``Password: <value>`` line, used by deployment scripts
        (e.g. the Lighthouse image builder) that rewrite the plain file into
        a human-readable "URL / Password" card after first boot. Checked
        first so a labeled file always wins; falls back to the plain layout
        so existing callers/tests are unaffected.
    """
    target = _password_path(home)
    if not target.exists():
        return None
    lines = target.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(_PASSWORD_LABEL_PREFIX):
            value = stripped[len(_PASSWORD_LABEL_PREFIX) :].strip()
            if value:
                return value
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def remove_password(home: Path) -> None:
    target = _password_path(home)
    with contextlib.suppress(FileNotFoundError):
        target.unlink()


def boot_self_heal(home: Path, user_count: int) -> str | None:
    """Reconcile the wizard password file at server boot.

    When setup is still open (``user_count == 0``), ensure a password file exists
    and return the password so the CLI can print it — including when the file
    already exists (e.g. the DB was wiped but ``octop-login.txt`` was not).
    """
    if user_count > 0:
        remove_password(home)
        return None
    created = ensure_password(home)
    return created if created is not None else read_password(home)
