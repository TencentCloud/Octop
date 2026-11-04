"""Opt-in for a browser that was baked into the image.

The binary can be present without Browser AI being turned on. Confirmation
writes a marker under the Octop home (the data volume in Docker). Hosts
without the image marker keep the previous behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.utils.paths import PathLayout

MARKER = Path("/etc/octop/bundled-components.json")
FLAG_NAME = "browser.enabled"


def bundled_browser(marker: Path = MARKER) -> bool:
    """True when this install shipped Chromium and still requires a confirm."""
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return bool(isinstance(payload, dict) and payload.get("browser") is True)


def _flag_path(root: Path | None) -> Path:
    home = root if root is not None else PathLayout.from_env().root
    return home / FLAG_NAME


def browser_enabled(*, marker: Path = MARKER, root: Path | None = None) -> bool:
    """False only for a bundled browser the user has not confirmed."""
    if not bundled_browser(marker):
        return True
    return _flag_path(root).is_file()


def confirm_browser_enabled(root: Path | None = None, *, marker: Path = MARKER) -> None:
    """Record that the user enabled the bundled browser."""
    if not bundled_browser(marker):
        return
    path = _flag_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n", encoding="utf-8")
