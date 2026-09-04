"""harness-browser media paths aligned with IM ``outbound/`` layout."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

OUTBOUND_SCREENSHOTS_REL = "outbound/screenshots"
BROWSER_PROFILES_REL = "browser-profiles"


def parse_octop_user_id(raw: object) -> int | None:
    """Return a positive Octop ``users.id``, or ``None`` if *raw* is unusable."""
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        return None
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        return None
    if user_id <= 0:
        return None
    return user_id


def user_browser_profile(user_id: int) -> str:
    """Stable harness-browser profile name for one Octop user.

    Dashboard and CLI turns use the logged-in user. IM turns use the agent
    owner (the same id already stored on the thread). A leftover on-disk
    ``default`` directory is not migrated and must not be reused.
    """
    return f"user-{user_id}"


def agent_outbound_screenshots_dir(workspace_dir: Path) -> Path:
    """``{workspace_dir}/outbound/screenshots`` — same convention as IM ``outbound/``."""
    dest = Path(workspace_dir) / OUTBOUND_SCREENSHOTS_REL
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def legacy_harness_profiles_dir() -> Path:
    """Pre-Octop default: ``~/.harness-browser/profiles``."""
    return Path.home() / ".harness-browser" / "profiles"


def _profile_dir_is_empty(directory: Path) -> bool:
    if not directory.is_dir():
        return True
    for child in directory.iterdir():
        if child.name.startswith("."):
            continue
        return False
    return True


def _maybe_migrate_legacy_profiles(dest: Path) -> None:
    """One-shot move from ``~/.harness-browser/profiles`` when *dest* is empty."""
    legacy = legacy_harness_profiles_dir()
    if not _profile_dir_is_empty(dest):
        return
    if not legacy.is_dir() or _profile_dir_is_empty(legacy):
        return
    logger.info("Migrating browser profiles %s → %s", legacy, dest)
    try:
        for child in legacy.iterdir():
            target = dest / child.name
            if target.exists():
                continue
            shutil.move(str(child), str(target))
    except OSError as exc:
        logger.warning("Legacy browser profile migration skipped: %s", exc)


def octop_browser_profiles_dir(paths: PathLayout | None = None) -> Path:
    """Shared Chrome profiles root: ``~/.octop/browser-profiles``.

    Profiles live under one Octop-owned root and are named ``user-<id>``.
    A pre-isolation ``default`` directory, if present, is left untouched.
    Prefer this directory over ``~/.harness-browser/profiles`` or system
    ``/tmp``.

    When the Octop dir is empty and a legacy harness-browser profiles tree
    exists, contents are moved once so login cookies survive the cutover.
    """
    if paths is None:
        from octop.infra.utils.paths import PathLayout  # noqa: PLC0415

        paths = PathLayout.from_env()
    dest = paths.root / BROWSER_PROFILES_REL
    dest.mkdir(parents=True, exist_ok=True)
    _maybe_migrate_legacy_profiles(dest)
    return dest


def configure_browser_screenshots_dir(screenshots_dir: Path) -> None:
    """Point harness-browser screenshot actions at an agent workspace directory."""
    resolved = screenshots_dir.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    os.environ["BROWSER_USE_SCREENSHOTS_DIR"] = str(resolved)
    logger.debug("BROWSER_USE_SCREENSHOTS_DIR=%s", resolved)


def configure_browser_profiles_dir(profiles_dir: Path | None = None) -> Path:
    """Point harness-browser at a profiles directory; return the resolved root.

    When *profiles_dir* is omitted, uses :func:`octop_browser_profiles_dir`
    (including legacy migration). Also updates ``BROWSER_USE_PROFILES_DIR``
    and in-process harness-browser settings.
    """
    root = Path(profiles_dir) if profiles_dir is not None else octop_browser_profiles_dir()
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve()
    os.environ["BROWSER_USE_PROFILES_DIR"] = str(resolved)
    with contextlib.suppress(Exception):
        from harness_browser.settings import settings as hb_settings  # noqa: PLC0415

        hb_settings.profiles_dir = resolved
    logger.debug("BROWSER_USE_PROFILES_DIR=%s", resolved)
    return resolved


def configure_browser_idle_timeout(timeout_minutes: int) -> None:
    """Apply Octop's browser idle policy to harness-browser."""
    timeout = max(int(timeout_minutes), 0)
    os.environ["BROWSER_USE_IDLE_TIMEOUT_MINUTES"] = str(timeout)
    with contextlib.suppress(Exception):
        from harness_browser.settings import settings as hb_settings  # noqa: PLC0415

        runtime_settings: Any = hb_settings
        runtime_settings.idle_timeout_minutes = float(timeout)
    logger.debug("BROWSER_USE_IDLE_TIMEOUT_MINUTES=%s", timeout)


def harness_settings_for_screenshots_dir(screenshots_dir: Path) -> Any | None:
    """Build :class:`HarnessSettings` when harness-browser is installed."""
    try:
        from harness_browser.settings import HarnessSettings
    except ImportError:
        return None
    return HarnessSettings(screenshots_dir=screenshots_dir.resolve())


def legacy_harness_screenshots_dir() -> Path:
    return Path.home() / ".harness-browser" / "screenshots"
