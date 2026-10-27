"""Setup wizard password file at ``<home>/octop-login.txt``."""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

WIZARD_FILE_NAME = "octop-login.txt"
_TOKEN_BYTES = 16
_PASSWORD_LABEL_PREFIX = "Password:"

# Module-level so tests can flip it without faking ``os.name``.
_IS_WINDOWS = os.name == "nt"


def _restrict_permissions(target: Path) -> None:
    """Restrict the password file to its owner.

    POSIX: plain ``0o600``. Windows: ``os.chmod`` cannot express a DACL — it
    only toggles the read-only attribute from the owner-write bit — so the
    plaintext wizard password stayed readable by every local account that
    can reach the directory. Reset inherited ACEs and grant access to the
    current user plus LOCAL SYSTEM only (#2370). Failures are logged, never
    raised: password creation must not break first boot.
    """
    if not _IS_WINDOWS:
        os.chmod(target, 0o600)
        return
    user = os.environ.get("USERNAME", "").strip()
    domain = os.environ.get("USERDOMAIN", "").strip()
    principal = f"{domain}\\{user}" if domain and user else user
    grants = ["*S-1-5-18:F"]  # LOCAL SYSTEM, locale-independent SID form
    if principal:
        grants.insert(0, f"{principal}:F")
    try:
        proc = subprocess.run(
            ["icacls", str(target), "/inheritance:r", "/grant:r", *grants],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()[:200]
            logger.warning(
                "could not restrict wizard password file ACL (icacls rc=%s): %s",
                proc.returncode,
                detail,
            )
    except OSError as exc:
        logger.warning("could not restrict wizard password file ACL: %s", exc)


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
    """Generate the file if missing; return password or ``None`` if present.

    If ``<home>/octop-login.txt`` is missing but a legacy password exists at
    ``<legacy_home>/octop-login.txt`` (defaulting to the OS home), reuse that
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
                _restrict_permissions(target)
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
    _restrict_permissions(target)
    return pw


def read_password(home: Path, legacy_home: Path | None = None) -> str | None:
    """Return the wizard password, or ``None`` if the file is absent/empty.

    Checks ``<home>/octop-login.txt`` first. If absent, falls back to
    ``<legacy_home>/octop-login.txt`` (defaulting to the OS home).

    Supports two layouts:
      * Plain — the password is the file's first non-empty line, as written
        by :func:`ensure_password`.
      * Labeled — a ``Password: <value>`` line, used by deployment scripts
        (e.g. the Lighthouse image builder) that rewrite the plain file into
        a human-readable "URL / Password" card after first boot. Checked
        first so a labeled file always wins; falls back to the plain layout
        so existing callers/tests are unaffected.
    """
    target = resolve_password_path(home, legacy_home=legacy_home)
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


def boot_self_heal(home: Path, user_count: int, legacy_home: Path | None = None) -> str | None:
    """Reconcile the wizard password file at server boot.

    When setup is still open (``user_count == 0``), ensure a password file exists
    and return the password so the CLI can print it — including when the file
    already exists (e.g. the DB was wiped but ``octop-login.txt`` was not).

    The file is intentionally kept forever as a permanent record and is never
    deleted, even after setup completes.
    """
    if user_count > 0:
        return None
    created = ensure_password(home, legacy_home=legacy_home)
    return created if created is not None else read_password(home, legacy_home=legacy_home)
