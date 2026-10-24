"""Setup wizard password file at ``<home>/octop-login.txt``."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

WIZARD_FILE_NAME = "octop-login.txt"
_TOKEN_BYTES = 16
_PASSWORD_LABEL_PREFIX = "Password:"


def _password_path(home: Path) -> Path:
    return home / WIZARD_FILE_NAME


logger = logging.getLogger(__name__)


def _harden_password_file(target: Path) -> None:
    """Apply the ``0o600`` intent to the written password file.

    POSIX: mode bits only. Windows: also swap the inherited DACL for a
    protected one granting full control to SYSTEM, Administrators and the
    file's owner — ``os.chmod`` cannot express that on NTFS, so a plain
    chmod'ed file stays readable by any local user that can reach the
    directory (#2370).
    """
    os.chmod(target, 0o600)
    if os.name == "nt" and not _restrict_windows_dacl(target):
        logger.warning(
            "Could not restrict the DACL on %s; the wizard password "
            "file may be readable by other local users.",
            target,
        )


def _restrict_windows_dacl(target: Path) -> bool:
    """Replace the inherited NTFS DACL on ``target`` with a protected one
    (SYSTEM, Administrators, owner). True when the DACL was set."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    SE_FILE_OBJECT = 1
    OWNER_SECURITY_INFORMATION = 0x1
    DACL_SECURITY_INFORMATION = 0x4
    PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
    SDDL_REVISION_1 = 1

    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.ULONG),
    ]
    advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]

    def _free(handle) -> None:
        if handle:
            kernel32.LocalFree(handle)

    owner_sid = ctypes.c_void_p()
    sd = ctypes.c_void_p()
    path = str(target)
    if (
        advapi32.GetNamedSecurityInfoW(
            path,
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION,
            ctypes.byref(owner_sid),
            None,
            None,
            None,
            ctypes.byref(sd),
        )
        != 0
    ):
        return False
    _free(sd)
    sid_string = wintypes.LPWSTR()
    if (
        advapi32.ConvertSidToStringSidW(
            owner_sid,
            ctypes.byref(sid_string),
        )
        == 0
        or not sid_string.value
    ):
        return False
    owner = sid_string.value
    _free(sid_string)

    # Protected DACL: no inherited ACEs, full control for SYSTEM,
    # Administrators and the file's owner only.
    sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{owner})"
    dacl_sd = ctypes.c_void_p()
    dacl_len = wintypes.ULONG()
    if (
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl,
            SDDL_REVISION_1,
            ctypes.byref(dacl_sd),
            ctypes.byref(dacl_len),
        )
        == 0
        or not dacl_sd.value
    ):
        return False

    dacl = ctypes.c_void_p()
    dacl_present = wintypes.BOOL()
    defaulted = wintypes.BOOL()
    if (
        advapi32.GetSecurityDescriptorDacl(
            dacl_sd,
            ctypes.byref(dacl_present),
            ctypes.byref(dacl),
            ctypes.byref(defaulted),
        )
        == 0
        or not dacl_present.value
    ):
        _free(dacl_sd)
        return False

    ok = (
        advapi32.SetNamedSecurityInfoW(
            path,
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            dacl,
            None,
        )
        == 0
    )
    _free(dacl_sd)
    return ok


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
                _harden_password_file(target)
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
    _harden_password_file(target)
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
