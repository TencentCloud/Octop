"""Safe post-login redirect path handling."""

from __future__ import annotations

_DEFAULT_REDIRECT_AFTER = "/chat"


def sanitize_redirect_after(path: str | None, *, default: str = _DEFAULT_REDIRECT_AFTER) -> str:
    """Return a safe internal redirect path, or the caller's fallback route."""
    if not path or not path.startswith("/"):
        return default
    # Browsers strip ASCII tabs/newlines before parsing URLs (e.g. /\n/evil.test).
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return default
    if path.startswith("//") or "\\" in path or "://" in path or path.startswith("http:"):
        return default
    return path
