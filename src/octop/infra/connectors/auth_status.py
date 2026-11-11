"""Whether a custom MCP server using OAuth can be used now or needs the user to authorize again.

``ok``        a token is stored and either still valid or refreshable;
``required``  OAuth is needed and no token is stored;
``expired``   a stored token stopped working (expired without a refresh
              token, refresh failed, or the MCP server rejected it).

Servers that do not use OAuth have no status (``None``).
"""

from __future__ import annotations

import time
from typing import Any, Literal

from octop.infra.connectors.custom_mcp import (
    oauth_configured,
    oauth_required,
    oauth_tokens_from_spec,
)

AuthStatus = Literal["ok", "required", "expired"]

AUTH_OK: AuthStatus = "ok"
AUTH_REQUIRED: AuthStatus = "required"
AUTH_EXPIRED: AuthStatus = "expired"
NEEDS_AUTH: frozenset[str] = frozenset({AUTH_REQUIRED, AUTH_EXPIRED})


def _expired_without_refresh(tokens: dict[str, Any], now: int) -> bool:
    raw = tokens.get("expires_at")
    try:
        expires_at = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        expires_at = None
    refresh = str(tokens.get("refresh_token") or "").strip()
    return expires_at is not None and expires_at <= now and not refresh


def custom_auth_status(spec: dict[str, Any], *, now: int | None = None) -> AuthStatus | None:
    """Status of a custom MCP server; ``None`` when it does not use OAuth."""
    if oauth_required(spec):
        return AUTH_EXPIRED if oauth_tokens_from_spec(spec).get("expired") else AUTH_REQUIRED
    if not oauth_configured(spec):
        return None
    tokens = oauth_tokens_from_spec(spec)
    if _expired_without_refresh(tokens, int(time.time()) if now is None else now):
        return AUTH_EXPIRED
    return AUTH_OK
