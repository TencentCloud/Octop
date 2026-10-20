"""octop-browser: AI-friendly browser automation via CDP."""

from octop_browser.install import (
    InstallEvent,
    chromium_executable,
    ensure_chromium,
    install_chromium_stream,
)
from octop_browser.mode import BrowserMode
from octop_browser.models import ActionMetrics, TabInfo, ToolResult
from octop_browser.session import BrowserSession
from octop_browser.settings import OctopSettings, settings
from octop_browser.tool_interface import browser_tool

__all__ = [
    "BrowserSession",
    "browser_tool",
    "BrowserMode",
    "OctopSettings",
    "settings",
    "ToolResult",
    "ActionMetrics",
    "TabInfo",
    "InstallEvent",
    "chromium_executable",
    "ensure_chromium",
    "install_chromium_stream",
]
