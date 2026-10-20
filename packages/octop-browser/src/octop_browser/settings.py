"""Global configuration loaded from environment variables.

All settings can be overridden by:
1. Setting environment variables before importing the package (highest priority)
2. Instantiating OctopSettings with explicit values and passing it to
   BrowserSession.create()
3. Module-level defaults (lowest priority)

Environment variables (all optional):

  BROWSER_USE_PROFILES_DIR   - base directory for Chrome user-data-dirs
                          default: ~/.octop-browser/profiles
  BROWSER_USE_SCREENSHOTS_DIR - base directory where the screenshot action writes
                          PNG files. Defaults to ~/.octop-browser/screenshots.
  BROWSER_USE_CDP_HOST       - host or IP serving Chrome's HTTP/WebSocket CDP endpoint
                          default: localhost
  BROWSER_USE_CDP_PORT_START - first CDP debug port assigned to profiles
                          default: 9222
  BROWSER_USE_MODE   - launch mode: "auto" | "headed" | "headless"
                          default: auto (uses headed when DISPLAY/WAYLAND_DISPLAY
                          is set or on macOS/Windows, headless otherwise)
  BROWSER_USE_CHROME_BIN     - absolute path to Chrome/Chromium executable
                          default: auto-detect
  BROWSER_USE_CDP_TIMEOUT    - seconds to wait for a CDP command response
                          default: 30.0
  BROWSER_USE_LAUNCH_RETRIES - number of times to poll Chrome after launch
                          default: 20
  BROWSER_USE_LAUNCH_DELAY   - seconds between launch poll attempts
                          default: 0.25
  BROWSER_USE_NO_SANDBOX     - if "1"/"true"/"yes", force --no-sandbox on every
                          Chrome launch. If "0"/"false", force-disable the
                          auto-detection (Chrome runs with its full sandbox).
                          When unset, Chrome is launched with --no-sandbox iff
                          we detect that the host kernel will not allow
                          unprivileged user namespaces (typical inside
                          containers / restricted sandboxes).
  BROWSER_USE_VIEWPORT_WIDTH - viewport width in CSS pixels applied via
                          Emulation.setDeviceMetricsOverride after connect.
                          Controls the default screenshot/page render size.
                          default: 1440
  BROWSER_USE_VIEWPORT_HEIGHT - viewport height in CSS pixels.
                          default: 900
  BROWSER_USE_CDP_MAX_MESSAGE_SIZE - max CDP WebSocket frame size in bytes.
                          ``websockets`` defaults to 1 MiB; raise this so
                          ``Page.captureScreenshot`` of large pages does
                          not trip code 1009 (message too big). Set to 0
                          to disable the cap entirely.
                          default: 33554432 (32 MiB)
  BROWSER_USE_CDP_WS_URL     - if set, bypass launcher and connect directly to this
                          Chrome DevTools WebSocket URL (e.g. for remote/Docker Chrome)
                          default: None
  BROWSER_USE_IDLE_TIMEOUT_MINUTES - stop a locally managed Chrome profile after
                          this many minutes without real CDP activity. 0 disables.
                          default: 0
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from octop_browser.mode import BrowserMode, normalize_mode


def _env_path(key: str, default: Path) -> Path:
    val = os.environ.get(key)
    return Path(val) if val else default


#: State directory under ``$HOME``. Prefer ``.octop-browser``; fall back to a
#: previously used alternate name when that directory already exists so login
#: cookies and recordings are not orphaned.
_STATE_DIR = ".octop-browser"
_LEGACY_STATE_DIR = ".harness-browser"


def state_dir() -> Path:
    """Return the base directory holding profiles, screenshots and recordings.

    Fresh installs use ``~/.octop-browser``. If that path does not exist but an
    older alternate state directory is already present, that one is reused so
    existing Chrome profiles (cookies) and recordings stay attached.
    """
    home = Path.home()
    current = home / _STATE_DIR
    if current.exists():
        return current
    legacy = home / _LEGACY_STATE_DIR
    if legacy.exists():
        return legacy
    return current


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    return float(val) if val else default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val else default


def _env_str(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


@dataclass
class OctopSettings:
    """
    Runtime configuration for octop-browser.

    Instantiate with no arguments to read from environment variables.
    Pass explicit values to override individual settings::

        from octop_browser import OctopSettings, BrowserSession

        custom = OctopSettings(cdp_port_start=9300, cdp_timeout=60.0)
        sess = await BrowserSession.create(profile="work", settings=custom)

    Or point to a remote Chrome::

        import os
        os.environ["BROWSER_USE_CDP_WS_URL"] = "ws://remote-host:9222/devtools/browser/..."
    """

    profiles_dir: Path = field(
        default_factory=lambda: _env_path(
            "BROWSER_USE_PROFILES_DIR", state_dir() / "profiles"
        )
    )
    screenshots_dir: Path = field(
        default_factory=lambda: _env_path(
            "BROWSER_USE_SCREENSHOTS_DIR",
            state_dir() / "screenshots",
        )
    )
    cdp_host: str = field(
        default_factory=lambda: (
            _env_str("BROWSER_USE_CDP_HOST", "localhost") or "localhost"
        )
    )
    cdp_port_start: int = field(
        default_factory=lambda: _env_int("BROWSER_USE_CDP_PORT_START", 9222)
    )
    chrome_bin: str | None = field(
        default_factory=lambda: _env_str("BROWSER_USE_CHROME_BIN")
    )
    cdp_timeout: float = field(
        default_factory=lambda: _env_float("BROWSER_USE_CDP_TIMEOUT", 30.0)
    )
    launch_retries: int = field(
        default_factory=lambda: _env_int("BROWSER_USE_LAUNCH_RETRIES", 20)
    )
    launch_delay: float = field(
        default_factory=lambda: _env_float("BROWSER_USE_LAUNCH_DELAY", 0.25)
    )
    cdp_ws_url: str | None = field(
        default_factory=lambda: _env_str("BROWSER_USE_CDP_WS_URL")
    )
    idle_timeout_minutes: float = field(
        default_factory=lambda: _env_float("BROWSER_USE_IDLE_TIMEOUT_MINUTES", 0.0)
    )
    viewport_width: int = field(
        default_factory=lambda: _env_int("BROWSER_USE_VIEWPORT_WIDTH", 1440)
    )
    viewport_height: int = field(
        default_factory=lambda: _env_int("BROWSER_USE_VIEWPORT_HEIGHT", 900)
    )
    cdp_max_message_size: int | None = field(
        default_factory=lambda: (
            None
            if _env_int("BROWSER_USE_CDP_MAX_MESSAGE_SIZE", 33554432) == 0
            else _env_int("BROWSER_USE_CDP_MAX_MESSAGE_SIZE", 33554432)
        )
    )
    browser_mode: BrowserMode = field(
        default_factory=lambda: normalize_mode(_env_str("BROWSER_USE_MODE"))
    )


# Module-level singleton — reads env vars at import time.
# Tests should instantiate OctopSettings() directly rather than mutating this object.
settings = OctopSettings()
