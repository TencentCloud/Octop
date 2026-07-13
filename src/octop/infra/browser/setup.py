"""Browser environment setup: profile prep before Chrome launch, uninstall SSE."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def ensure_chrome_runtime_env() -> Path:
    """Ensure ``XDG_RUNTIME_DIR`` is a writable directory for the current uid.

    Chrome on Linux often tries ``/run/user/<uid>``. On headless / root /
    container hosts that path may be missing or unwritable (``mkdir: cannot
    create directory '/run/user/0': Permission denied``). Point the process
    env at a private ``/tmp`` runtime dir instead.
    """
    uid = os.getuid() if hasattr(os, "getuid") else 0
    current = (os.environ.get("XDG_RUNTIME_DIR") or "").strip()
    if current:
        path = Path(current)
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o700)
            if os.access(path, os.W_OK | os.X_OK):
                return path
        except OSError:
            pass

    path = Path(f"/tmp/runtime-harness-browser-{uid}")
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)
    os.environ["XDG_RUNTIME_DIR"] = str(path)
    return path


def clear_profile_locks(profile_dir: Path) -> list[str]:
    """Remove stale Chrome ProcessSingleton lock files. Returns cleared names."""
    cleared: list[str] = []
    for lock_name in _LOCK_NAMES:
        lock_path = profile_dir / lock_name
        try:
            if lock_path.exists() or lock_path.is_symlink():
                lock_path.unlink()
                cleared.append(lock_name)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Failed to remove stale %s: %s", lock_name, exc)
    return cleared


def pkill_chrome_profile(profile_dir: Path) -> bool:
    """Best-effort kill of Chromium processes bound to ``user-data-dir=…``."""
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
    except Exception:  # noqa: BLE001
        return False


def _profiles_root() -> Path:
    try:
        from harness_browser.settings import settings as _settings  # noqa: PLC0415

        return Path(_settings.profiles_dir)
    except Exception:  # noqa: BLE001
        return Path.home() / ".harness-browser" / "profiles"


def _playwright_cache_roots() -> list[Path]:
    roots: list[Path] = []
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        roots.append(Path(env_path))
    if sys.platform == "darwin":
        roots.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    elif sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "ms-playwright")
    else:
        roots.append(Path.home() / ".cache" / "ms-playwright")
    return roots


def list_playwright_chromium_dirs() -> list[Path]:
    """Return Playwright-managed ``chromium-*`` install directories (ours only)."""
    found: list[Path] = []
    for cache in _playwright_cache_roots():
        if not cache.is_dir():
            continue
        found.extend(sorted(p for p in cache.glob("chromium-*") if p.is_dir()))
    return found


def playwright_chromium_installed() -> bool:
    """True when at least one Playwright Chromium revision directory exists."""
    return bool(list_playwright_chromium_dirs())


def chrome_source_for_path(chrome_path: str | None) -> str | None:
    """Classify a resolved browser binary as ``system`` or ``playwright``."""
    if not chrome_path:
        return None
    resolved = Path(chrome_path).resolve()
    for cache in _playwright_cache_roots():
        try:
            resolved.relative_to(cache.resolve())
            return "playwright"
        except (ValueError, OSError):
            continue
    # Also match when chromium_executable() reports the same path.
    try:
        from harness_browser.install import chromium_executable  # noqa: PLC0415

        pw = chromium_executable()
        if pw and Path(pw).resolve() == resolved:
            return "playwright"
    except Exception:  # noqa: BLE001
        pass
    return "system"


async def _cdp_port_listening(port: int) -> bool:
    try:
        import aiohttp  # noqa: PLC0415
        from harness_browser.settings import settings as _settings  # noqa: PLC0415

        host = _settings.cdp_host
        timeout = aiohttp.ClientTimeout(total=1)
        async with (
            aiohttp.ClientSession() as session,
            session.get(f"http://{host}:{port}/json/version", timeout=timeout) as resp,
        ):
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def _profile_port(profile_name: str) -> int | None:
    try:
        from harness_browser.profile import ProfileManager  # noqa: PLC0415

        pm = ProfileManager()
        profile = pm.get_or_create(profile_name)
        return int(profile.cdp_port)
    except Exception:  # noqa: BLE001
        return None


def _profile_data_dir(profile_name: str) -> Path:
    try:
        from harness_browser.profile import ProfileManager  # noqa: PLC0415

        return Path(ProfileManager().get_or_create(profile_name).data_dir)
    except Exception:  # noqa: BLE001
        return _profiles_root() / profile_name


def recover_stale_profile(profile_dir: Path) -> None:
    """Last-resort: move an unusable profile aside so Chrome can start fresh."""
    if not profile_dir.exists():
        profile_dir.mkdir(parents=True, exist_ok=True)
        return
    stamp = int(time.time())
    stale = profile_dir.with_name(f"{profile_dir.name}.stale-{stamp}")
    try:
        profile_dir.rename(stale)
        logger.warning("Moved unusable browser profile %s → %s", profile_dir, stale)
    except OSError as exc:
        logger.warning("Could not rename stale profile %s: %s", profile_dir, exc)
        # Best effort wipe of lock files only; leave the rest.
        clear_profile_locks(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)


async def prepare_harness_profile_for_launch(
    profile_name: str,
    *,
    force_recover: bool = False,
) -> Path:
    """Make a harness-browser profile safe to (re)launch Chrome against.

    - Ensures a writable ``XDG_RUNTIME_DIR``
    - If CDP is already listening, leaves the running browser alone
    - Otherwise kills leftover Chrome for this profile and clears Singleton locks
    - Optionally recovers a non-writable / corrupt profile directory
    """
    ensure_chrome_runtime_env()
    data_dir = await asyncio.to_thread(_profile_data_dir, profile_name)
    data_dir.mkdir(parents=True, exist_ok=True)

    port = await asyncio.to_thread(_profile_port, profile_name)
    if port is not None and await _cdp_port_listening(port):
        return data_dir

    killed = await asyncio.to_thread(pkill_chrome_profile, data_dir)
    if killed:
        await asyncio.sleep(0.4)
    cleared = await asyncio.to_thread(clear_profile_locks, data_dir)
    if cleared:
        logger.info(
            "Cleared stale Chrome locks for profile %r: %s",
            profile_name,
            ", ".join(cleared),
        )

    if force_recover or not os.access(data_dir, os.W_OK):
        await asyncio.to_thread(recover_stale_profile, data_dir)
    else:
        # If locks still remain (Permission denied), recover so launch can proceed.
        remaining = [
            name
            for name in _LOCK_NAMES
            if (data_dir / name).exists() or (data_dir / name).is_symlink()
        ]
        if remaining:
            logger.warning(
                "Chrome locks still present for %r (%s); recovering profile dir",
                profile_name,
                ", ".join(remaining),
            )
            await asyncio.to_thread(recover_stale_profile, data_dir)

    return data_dir


async def _close_harness_registry() -> int:
    closed = 0
    try:
        from harness_browser.tool_interface import _registry  # noqa: PLC0415
    except ImportError:
        return 0

    for name, sess in list(_registry.items()):
        _registry.pop(name, None)
        with contextlib.suppress(Exception):
            await sess.close()
            closed += 1
    return closed


async def uninstall_browser_stream(*, locale: str = "en") -> AsyncIterator[str]:
    """Remove Playwright-installed Chromium only (SSE).

    Does **not** touch the user's system Chrome/Chromium, and does **not**
    delete ``~/.harness-browser`` profile data (login cookies etc.).

    ``locale`` is reserved for future i18n of log lines.
    """
    _ = locale
    yield _sse({"log": "Closing Octop browser sessions…"})
    closed = await _close_harness_registry()
    if closed:
        yield _sse({"log": f"Closed {closed} in-process session(s)."})

    # Stop Chrome processes that were launched with our harness profiles so
    # the Playwright binary can be deleted safely. Does not target system
    # Chrome windows the user opened themselves.
    profiles_root = _profiles_root()
    if profiles_root.is_dir():
        yield _sse({"log": "Stopping Octop-managed browser processes…"})
        for child in sorted(profiles_root.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                await asyncio.to_thread(pkill_chrome_profile, child)
                await asyncio.to_thread(clear_profile_locks, child)

    chromium_dirs = list_playwright_chromium_dirs()
    if not chromium_dirs:
        yield _sse({"log": "No Playwright Chromium install found (nothing to remove)."})
        yield _sse({"done": True, "success": True})
        return

    removed_any = False
    for cdir in chromium_dirs:
        yield _sse({"log": f"Removing Playwright Chromium: {cdir}…"})
        try:
            await asyncio.to_thread(shutil.rmtree, cdir)
            removed_any = True
            yield _sse({"log": f"Removed {cdir.name}."})
        except OSError as exc:
            yield _sse({"log": f"Failed to remove {cdir}: {exc}"})
            yield _sse(
                {
                    "done": True,
                    "success": False,
                    "error": str(exc),
                    "log": str(exc),
                }
            )
            return

    if removed_any:
        yield _sse(
            {
                "log": (
                    "Removed Playwright Chromium. "
                    "System Chrome/Chromium (if any) was left untouched."
                )
            }
        )
    yield _sse({"done": True, "success": True})
