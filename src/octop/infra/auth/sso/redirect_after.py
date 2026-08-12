"""Safe post-login redirect path handling."""

from __future__ import annotations

_DEFAULT_REDIRECT_AFTER = "/chat"


def sanitize_redirect_after(path: str | None) -> str:
    """Return a safe internal redirect path, or the default chat route."""
    if not path or not path.startswith("/"):
        return _DEFAULT_REDIRECT_AFTER
    if path.startswith("//") or "\\" in path or "://" in path or path.startswith("http:"):
        return _DEFAULT_REDIRECT_AFTER
    return path
