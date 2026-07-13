"""Browser environment helpers (install/uninstall, profile prep)."""

from __future__ import annotations

from octop.infra.browser.setup import (
    chrome_source_for_path,
    playwright_chromium_installed,
    prepare_harness_profile_for_launch,
    resolve_browser_display,
    uninstall_browser_stream,
)

__all__ = [
    "chrome_source_for_path",
    "playwright_chromium_installed",
    "prepare_harness_profile_for_launch",
    "resolve_browser_display",
    "uninstall_browser_stream",
]
