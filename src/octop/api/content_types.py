"""Pinned ``Content-Type`` values for the web assets Octop serves.

``mimetypes.guess_type`` consults the Windows registry
(``HKEY_CLASSES_ROOT\\.js\\Content Type``). On a machine that maps ``.js`` to
``text/plain`` — not rare, file associations get rewritten by editors and
download tools — every dashboard ES module is answered with a non-JavaScript
MIME type. Browsers then refuse to execute the module scripts and both the
desktop shell and a browser tab stay stuck on the loading screen, with no way
to reach the first-run wizard.

The asset types Octop ships are known ahead of time, so pin them here instead
of asking the host. Shared by the dashboard SPA and the plugin UI routes so the
two never drift apart.
"""

from __future__ import annotations

from pathlib import Path

UI_CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def ui_content_type(name: str | Path) -> str | None:
    """Return the pinned ``Content-Type`` for a bundled asset.

    Returns ``None`` when the suffix is not one Octop ships, letting the caller
    fall back to its own default.
    """
    return UI_CONTENT_TYPES.get(Path(name).suffix.lower())
