"""Shared SSO state cookie for OIDC and OAuth login callbacks."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from octop.api.common.public_base import resolve_public_base

SSO_STATE_COOKIE = "octop_sso_state"
SSO_COOKIE_PATH = "/api/auth"
SSO_STATE_TTL_SECONDS = 600


def request_is_https(request: Request) -> bool:
    """Whether the browser-facing origin is HTTPS.

    Same order as ``resolve_public_base``: a forwarded proto wins, otherwise
    ``public_base_url``, otherwise the socket scheme. A TLS-terminating proxy
    that omits ``X-Forwarded-Proto`` still gets a ``Secure`` SSO cookie when
    the configured origin is ``https``.
    """
    return resolve_public_base(request).split(":", 1)[0].lower() == "https"


def set_sso_state_cookie(response: JSONResponse, request: Request, state: str) -> None:
    response.set_cookie(
        SSO_STATE_COOKIE,
        state,
        max_age=SSO_STATE_TTL_SECONDS,
        path=SSO_COOKIE_PATH,
        httponly=True,
        secure=request_is_https(request),
        samesite="lax",
    )


def delete_sso_state_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SSO_STATE_COOKIE, path=SSO_COOKIE_PATH, secure=request_is_https(request))


def cookie_state(request: Request) -> str | None:
    return request.cookies.get(SSO_STATE_COOKIE)
