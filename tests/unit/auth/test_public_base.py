"""Tests for public OIDC callback URL helpers."""

from __future__ import annotations

from starlette.requests import Request

from octop.api.common.public_base import resolve_public_base
from octop.infra.auth.sso.public_base import build_redirect_uri


def _request(*, scheme: str = "http", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": scheme,
            "server": ("internal.example", 8080),
            "path": "/",
            "headers": headers or [(b"host", b"internal.example:8080")],
        }
    )


def test_resolve_public_base_uses_the_server_resolved_scheme() -> None:
    """Behind a trusted proxy the ASGI server has already set ``scope['scheme']``.

    ``X-Forwarded-Proto`` is not read here: uvicorn applies it, and only for
    peers in ``forwarded_allow_ips``.
    """
    request = _request(scheme="https", headers=[(b"host", b"octop.example")])

    assert resolve_public_base(request) == "https://octop.example"


def test_resolve_public_base_ignores_forwarded_headers_from_any_peer() -> None:
    """A client cannot talk Octop into building someone else's OIDC origin."""
    request = _request(
        headers=[
            (b"host", b"internal.example:8080"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"octop.example"),
        ]
    )

    assert resolve_public_base(request) == "http://internal.example:8080"


def test_resolve_public_base_uses_request_url_without_proxy_headers() -> None:
    request = _request(scheme="https", headers=[(b"host", b"octop.example")])

    assert resolve_public_base(request) == "https://octop.example"


def test_build_redirect_uri_uses_oidc_callback_path() -> None:
    assert (
        build_redirect_uri("https://octop.example/")
        == "https://octop.example/api/auth/oidc/callback"
    )


def test_build_redirect_uri_accepts_oauth_callback_path() -> None:
    assert (
        build_redirect_uri("https://octop.example", "/api/auth/oauth/callback")
        == "https://octop.example/api/auth/oauth/callback"
    )
