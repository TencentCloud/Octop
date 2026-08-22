"""Best-effort bubblewrap (``bwrap``) provisioning for scoped ``root_dir``.

Used when saving agent backends with a non-host-root ``root_dir``. Install
failure is never fatal — harness only constructs ``BubbledLocalShellBackend``
when Linux + ``virtual_mode`` + non-host root + ``bwrap``; otherwise plain
``local_shell`` (no execute path rewrite).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT_SEC = 90

_PKG_MANAGERS: tuple[tuple[str, str], ...] = (
    ("apt-get", "apt"),
    ("apt", "apt"),
    ("dnf", "dnf"),
    ("yum", "yum"),
    ("pacman", "pacman"),
    ("zypper", "zypper"),
)


def _detect_package_manager() -> str | None:
    for binary, kind in _PKG_MANAGERS:
        if shutil.which(binary):
            return kind
    return None


def _can_install_without_password() -> bool:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    sudo = shutil.which("sudo")
    if sudo is None:
        return False
    try:
        result = subprocess.run(
            [sudo, "-n", "true"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _run_install(argv: list[str]) -> bool:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_INSTALL_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logger.warning("bubblewrap install timed out: %s", argv)
        return False
    except OSError as exc:
        logger.warning("bubblewrap install failed to start: %s", exc)
        return False
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.warning(
            "bubblewrap install exited %s: %s",
            result.returncode,
            stderr[:500] if stderr else "(no stderr)",
        )
        return False
    return True


def _install_argv(manager: str, *, use_sudo: bool) -> list[str] | None:
    prefix: list[str] = []
    if use_sudo:
        sudo = shutil.which("sudo")
        if sudo is None:
            return None
        prefix = [sudo, "-n"]

    if manager == "apt":
        apt = shutil.which("apt-get") or shutil.which("apt")
        if apt is None:
            return None
        # update is best-effort; ignore failure by chaining separately in caller
        return [
            *prefix,
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            apt,
            "install",
            "-y",
            "-qq",
            "bubblewrap",
        ]
    if manager == "dnf":
        dnf = shutil.which("dnf")
        return None if dnf is None else [*prefix, dnf, "install", "-y", "bubblewrap"]
    if manager == "yum":
        yum = shutil.which("yum")
        return None if yum is None else [*prefix, yum, "install", "-y", "bubblewrap"]
    if manager == "pacman":
        pacman = shutil.which("pacman")
        return None if pacman is None else [*prefix, pacman, "-Sy", "--noconfirm", "bubblewrap"]
    if manager == "zypper":
        zypper = shutil.which("zypper")
        return None if zypper is None else [*prefix, zypper, "install", "-y", "bubblewrap"]
    return None


def _install_bubblewrap(manager: str) -> bool:
    use_sudo = not (hasattr(os, "geteuid") and os.geteuid() == 0)
    if manager == "apt":
        apt = shutil.which("apt-get") or shutil.which("apt")
        if apt is not None:
            if use_sudo:
                sudo = shutil.which("sudo")
                update_argv = (
                    None
                    if sudo is None
                    else [
                        sudo,
                        "-n",
                        "env",
                        "DEBIAN_FRONTEND=noninteractive",
                        apt,
                        "update",
                        "-qq",
                    ]
                )
            else:
                update_argv = [
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    apt,
                    "update",
                    "-qq",
                ]
            if update_argv is not None:
                # Best-effort index refresh; install may still succeed without it.
                _run_install(update_argv)

    argv = _install_argv(manager, use_sudo=use_sudo)
    if argv is None:
        return False
    return _run_install(argv)


def ensure_bubblewrap() -> dict[str, Any]:
    """Best-effort ensure ``bwrap`` is on PATH.

    Returns a status dict suitable for ``POST /api/filesystem/ensure-bwrap``.
    Never raises for missing packages / privilege — callers must not block save.
    """
    if not sys.platform.startswith("linux"):
        return {
            "status": "skipped",
            "reason": "not_linux",
            "detail": "bubblewrap jail is Linux-only; execute uses plain local_shell",
        }

    if shutil.which("bwrap"):
        return {
            "status": "ready",
            "reason": "already_present",
            "detail": "",
        }

    manager = _detect_package_manager()
    if manager is None:
        return {
            "status": "degraded",
            "reason": "no_package_manager",
            "detail": "no apt/dnf/yum/pacman/zypper; install bubblewrap manually",
        }

    if not _can_install_without_password():
        return {
            "status": "degraded",
            "reason": "no_privilege",
            "detail": "need root or passwordless sudo to install bubblewrap",
        }

    if not _install_bubblewrap(manager):
        return {
            "status": "degraded",
            "reason": "install_failed",
            "detail": f"failed to install bubblewrap via {manager}",
        }

    if shutil.which("bwrap"):
        return {
            "status": "installed",
            "reason": "install_ok",
            "detail": "",
        }

    return {
        "status": "degraded",
        "reason": "install_failed",
        "detail": "package manager reported success but bwrap still missing",
    }


__all__ = ["ensure_bubblewrap"]
