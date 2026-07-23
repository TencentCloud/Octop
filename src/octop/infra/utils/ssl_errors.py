"""Detect TLS/SSL failures in exception / stderr text for actionable UX hints."""

from __future__ import annotations

_SSL_MARKERS = (
    "ssl",
    "certificate verify",
    "record_layer",
    "handshake",
)


def looks_like_ssl_error(text: object) -> bool:
    """Return True when *text* looks like a TLS/SSL stack failure."""
    lower = str(text or "").lower()
    if not lower:
        return False
    return any(marker in lower for marker in _SSL_MARKERS)
