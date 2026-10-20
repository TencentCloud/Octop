"""Browser launch mode: auto / headed / headless.

The ``auto`` mode inspects the local environment for a usable display server:

- macOS / Windows: always treat as having a desktop → headed
- Linux: headed if ``$DISPLAY`` or ``$WAYLAND_DISPLAY`` is set, otherwise headless

This avoids surprising users who run the same script on a developer laptop
(headed) and a CI box or container (headless) without a code change.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Literal

logger = logging.getLogger(__name__)

BrowserMode = Literal["auto", "headed", "headless"]

_VALID_MODES: tuple[BrowserMode, ...] = ("auto", "headed", "headless")


def normalize_mode(value: str | None) -> BrowserMode:
    """Validate and normalize a mode string. Defaults to ``auto``.

    Raises:
        ValueError: if ``value`` is not one of the supported modes.
    """
    if value is None or value == "":
        return "auto"
    v = value.strip().lower()
    if v not in _VALID_MODES:
        raise ValueError(
            f"Invalid browser mode {value!r}. "
            f"Expected one of: {', '.join(_VALID_MODES)}"
        )
    return v


def has_desktop_environment() -> bool:
    """Best-effort detection of an interactive display server.

    On macOS and Windows we assume yes. On Linux we look for ``DISPLAY`` (X11)
    or ``WAYLAND_DISPLAY``. Headless servers, SSH sessions without X
    forwarding, and most container images will return False.
    """
    if sys.platform == "darwin" or sys.platform.startswith("win"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def resolve_headless(mode: BrowserMode) -> bool:
    """Resolve a ``BrowserMode`` to the boolean ``--headless`` flag.

    - ``headless`` → True
    - ``headed`` → False (the caller is responsible for ensuring a display
      exists; we do not silently downgrade)
    - ``auto`` → ``not has_desktop_environment()``
    """
    if mode == "headless":
        return True
    if mode == "headed":
        return False
    # auto
    headed = has_desktop_environment()
    logger.debug(
        "browser mode=auto resolved to %s (DISPLAY=%r WAYLAND_DISPLAY=%r)",
        "headed" if headed else "headless",
        os.environ.get("DISPLAY"),
        os.environ.get("WAYLAND_DISPLAY"),
    )
    return not headed
