"""Public URL helpers for SSO callbacks (framework-free)."""

from __future__ import annotations

from urllib.parse import urlparse

_OIDC_CALLBACK_PATH = "/api/auth/oidc/callback"
_OAUTH_CALLBACK_PATH = "/api/auth/oauth/callback"


def build_redirect_uri(public_base: str, callback_path: str = _OIDC_CALLBACK_PATH) -> str:
    """Build Octop's SSO callback URL from a public origin.

    ``callback_path`` defaults to the OIDC callback so existing one-argument
    callers and IdP registrations stay on ``/api/auth/oidc/callback``.
    """
    path = callback_path if callback_path.startswith("/") else f"/{callback_path}"
    return f"{public_base.rstrip('/')}{path}"


def oauth_callback_path() -> str:
    return _OAUTH_CALLBACK_PATH


def oidc_callback_path() -> str:
    return _OIDC_CALLBACK_PATH


def parse_strict_origin(value: str | None) -> str | None:
    """Return scheme+host origin or raise ValueError if the URL is not an origin."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("dashboard_origin must be an origin (scheme + host)")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("dashboard_origin must be an origin (scheme + host)")
    return f"{parsed.scheme}://{parsed.netloc}"
