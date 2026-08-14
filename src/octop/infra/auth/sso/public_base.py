"""Public URL helpers for OIDC callbacks (framework-free)."""

from __future__ import annotations

_OIDC_CALLBACK_PATH = "/api/auth/oidc/callback"


def build_redirect_uri(public_base: str) -> str:
    """Build Octop's OIDC callback URL from a public origin."""
    return f"{public_base.rstrip('/')}{_OIDC_CALLBACK_PATH}"
