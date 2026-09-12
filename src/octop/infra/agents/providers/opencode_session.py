"""OpenCode Go gateway URL detection and probe session headers.

The OpenCode Go gateway (``https://opencode.ai/zen/go``) rejects chat requests
that lack ``x-opencode-session`` with ``HTTP 400 MissingSessionID``. Chat
runtime injection is handled by harness-agent via ``ProviderConfig.session_header``
(filled with the current ``thread_id``). This module only:

- detects Go base URLs so the store can set ``session_header``
- injects a throwaway UUID for probes / model listing (those calls never
  enter ``HarnessAgent``)
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlsplit

OPENCODE_SESSION_HEADER = "x-opencode-session"
_OPENCODE_GO_HOSTS = frozenset({"opencode.ai"})


def is_opencode_go_base_url(base_url: Any) -> bool:
    """True when *base_url* points at the OpenCode Go gateway.

    Matches ``https://opencode.ai/zen/go`` and ``/zen/go/v1`` but not Zen
    (``/zen``, ``/zen/v1``), which do not require the session header.
    """
    if not base_url:
        return False
    try:
        parts = urlsplit(str(base_url))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if host not in _OPENCODE_GO_HOSTS:
        return False
    path = (parts.path or "").rstrip("/")
    return path == "/zen/go" or path.startswith("/zen/go/")


def ensure_opencode_session_header(
    base_url: Any,
    headers: dict[str, str] | None,
) -> dict[str, str]:
    """Return headers with a throwaway ``x-opencode-session`` when needed.

    Existing values (checked case-insensitively) always win. Non-Go URLs pass
    through untouched.
    """
    out = dict(headers) if headers else {}
    if any(key.lower() == OPENCODE_SESSION_HEADER for key in out):
        return out
    if not is_opencode_go_base_url(base_url):
        return out
    out[OPENCODE_SESSION_HEADER] = uuid.uuid4().hex
    return out


__all__ = [
    "OPENCODE_SESSION_HEADER",
    "ensure_opencode_session_header",
    "is_opencode_go_base_url",
]
