"""Pre-flight helpers before spawning Chrome.

Host environments (containers, root sessions, security agents) often break
Chrome's defaults:

* ``XDG_RUNTIME_DIR=/run/user/<uid>`` is missing or unwritable
* stale ``SingletonLock`` leftovers cause exit code 21
* the configured user-data-dir is writable by Python but not by the Chrome
  binary (AppArmor / host agents under ``/root/...``)

These helpers run inside :func:`launch_or_attach` so every caller (CLI, MCP,
Octop) gets the same self-heal path.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from octop_browser.profile import Profile

logger = logging.getLogger(__name__)

_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _temp_scope_token(uid: int | None = None) -> str:
    """Stable per-user suffix for temp dirs (never process id).

    Linux/macOS use ``uid`` / ``getuid()``. Windows has no ``getuid`` — use
    ``USERNAME`` / ``USER`` so relocated profiles survive process restarts.
    """
    if uid is not None:
        return str(uid)
    getuid = getattr(os, "getuid", None)
    if callable(getuid):
        return str(getuid())
    for key in ("USERNAME", "USER"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return "default"


def _runtime_dir_for_uid(uid: int | None = None) -> Path:
    token = _temp_scope_token(uid)
    if _is_linux():
        return Path(f"/tmp/runtime-octop-browser-{token}")
    return Path(tempfile.gettempdir()) / f"runtime-octop-browser-{token}"


def ensure_xdg_runtime_dir(env: dict[str, str] | None = None) -> Path | None:
    """Force a writable ``XDG_RUNTIME_DIR`` into *env* (and ``os.environ``).

    Linux-only: Chrome on Windows/macOS does not rely on ``XDG_RUNTIME_DIR``.
    Returns ``None`` on non-Linux.
    """
    if not _is_linux():
        return None
    target = env if env is not None else os.environ
    path = _runtime_dir_for_uid()
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)
    target["XDG_RUNTIME_DIR"] = str(path)
    if env is not None:
        os.environ["XDG_RUNTIME_DIR"] = str(path)
    return path


def clear_profile_locks(profile_dir: Path) -> list[str]:
    """Remove Chrome ProcessSingleton lock files. Returns cleared names."""
    cleared: list[str] = []
    for lock_name in _LOCK_NAMES:
        lock_path = profile_dir / lock_name
        try:
            if lock_path.exists() or lock_path.is_symlink():
                with contextlib.suppress(OSError):
                    if not lock_path.is_symlink():
                        lock_path.chmod(0o644)
                lock_path.unlink()
                cleared.append(lock_name)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Failed to remove stale %s: %s", lock_name, exc)
    return cleared


def _probe_writable(directory: Path) -> bool:
    """Return True when Chrome can use *directory* as a user-data-dir.

    On Linux also probes symlink creation because Chrome ProcessSingleton
    creates a symlink (SingletonLock). Windows/macOS skip the symlink
    probe — normal Windows users lack SeCreateSymbolicLinkPrivilege, so a
    failed symlink must not force a bogus profile relocation.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".octop-write-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        if _is_linux():
            link = directory / f".octop-link-{os.getpid()}"
            link.symlink_to("probe-target")
            link.unlink()
        return True
    except OSError:
        return False


def _alt_profiles_root() -> Path:
    """Fallback profiles root when the configured dir is not Chrome-safe.

    Never use a drive-relative ``\\tmp\\...`` path on Windows — Chrome
    resolves that against its own working directory and fails to start.
    """
    token = _temp_scope_token()
    if _is_linux():
        return Path(f"/tmp/octop-browser-profiles-{token}")
    return Path(tempfile.gettempdir()) / f"octop-browser-profiles-{token}"


def _under_root_home(path: Path) -> bool:
    try:
        path = path.resolve()
        root_home = Path("/root").resolve()
        return path == root_home or root_home in path.parents
    except OSError:
        return False


def ensure_profile_writable(profile: Profile) -> Profile:
    """Ensure *profile*.data_dir is usable; relocate under a temp root if needed.

    Returns the (possibly updated) profile. Does **not** mutate process-global
    ``BROWSER_USE_PROFILES_DIR`` / ``settings.profiles_dir`` — multi-user hosts
    (e.g. Octop) share one process, and a relocate for one profile must not
    redirect every subsequent profile. Callers that spawn Chrome should pass
    the updated ``profile.data_dir`` (see :func:`prepare_chrome_launch`).
    """
    data_dir = Path(profile.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        data_dir.chmod(0o700)

    # /root/... is frequently blocked for the Chrome binary by host security
    # agents even when the Octop/Python process can write there.
    needs_relocate = (
        sys.platform.startswith("linux") and _under_root_home(data_dir)
    ) or (not _probe_writable(data_dir))
    if not needs_relocate:
        return profile

    alt_root = _alt_profiles_root()
    alt_root.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(alt_root, 0o700)
    alt = alt_root / profile.name
    if data_dir.exists() and data_dir.resolve() != alt.resolve():
        stamp = int(time.time())
        stale = data_dir.with_name(f"{data_dir.name}.stale-{stamp}")
        with contextlib.suppress(OSError):
            data_dir.rename(stale)
    alt.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        alt.chmod(0o700)

    logger.warning(
        "Browser profile %s is not Chrome-safe; using %s",
        data_dir,
        alt,
    )
    profile.data_dir = alt
    return profile


def pkill_chrome_profile(profile_dir: Path) -> bool:
    """Best-effort kill of Chromium processes bound to this user-data-dir."""
    if os.name != "posix":
        return False
    pattern = f"user-data-dir={profile_dir}"
    try:
        result = subprocess.run(
            ["pkill", "-9", "-f", pattern],
            check=False,
            capture_output=True,
            timeout=5,
            shell=False,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False


def prepare_chrome_launch(profile: Profile) -> tuple[Profile, dict[str, str]]:
    """Make *profile* safe to launch and return ``(profile, env)`` for Popen."""
    env = os.environ.copy()
    ensure_xdg_runtime_dir(env)

    profile = ensure_profile_writable(profile)
    # user-data-dir flag is baked into the command from profile.data_dir; keep
    # env profiles dir in sync for any child tooling (process-global settings
    # stay untouched so other profiles in this process are not redirected).
    env["BROWSER_USE_PROFILES_DIR"] = str(profile.data_dir.parent)
    if "XDG_RUNTIME_DIR" in env:
        os.environ["XDG_RUNTIME_DIR"] = env["XDG_RUNTIME_DIR"]

    pkill_chrome_profile(profile.data_dir)
    cleared = clear_profile_locks(profile.data_dir)
    if cleared:
        logger.info(
            "Cleared stale Chrome locks for %s: %s",
            profile.name,
            ", ".join(cleared),
        )
    return profile, env


def recover_profile(profile: Profile) -> Profile:
    """Last-resort wipe/relocate after a failed Chrome launch (exit 21)."""
    data_dir = Path(profile.data_dir)
    if data_dir.exists():
        stamp = int(time.time())
        stale = data_dir.with_name(f"{data_dir.name}.stale-{stamp}")
        try:
            data_dir.rename(stale)
        except OSError:
            clear_profile_locks(data_dir)
            with contextlib.suppress(OSError):
                shutil.rmtree(data_dir)
    # Force temp relocate on Linux root-home layouts (profile only — no global
    # BROWSER_USE_PROFILES_DIR mutation).
    if sys.platform.startswith("linux"):
        alt_root = _alt_profiles_root()
        profile.data_dir = alt_root / profile.name
    profile.data_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        profile.data_dir.chmod(0o700)
    return ensure_profile_writable(profile)
