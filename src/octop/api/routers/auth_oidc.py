"""OpenID Connect SSO HTTP routes."""

from __future__ import annotations

import asyncio
import secrets
from functools import partial
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from octop.api.common.public_base import resolve_public_base
from octop.api.deps import current_admin, get_server, sign_token
from octop.api.routers.auth import _user_json
from octop.infra.auth.sso.service import SsoService
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()
_OIDC_STATE_COOKIE = "octop_oidc_state"
_OIDC_COOKIE_PATH = "/api/auth/oidc"
_OIDC_STATE_TTL_SECONDS = 600


class OidcStartBody(BaseModel):
    redirect_after: str | None = None


class OidcExchangeBody(BaseModel):
    code: str = Field(min_length=1)


class OidcConfigBody(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None
    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: str | None = None
    dashboard_origin: str | None = None


def _service(server: Any) -> SsoService:
    return cast(SsoService, server.sso_service)


def _public_base(request: Request) -> str:
    return resolve_public_base(request)


def _request_is_https(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _bad_request(exc: ValueError) -> OctopError:
    return OctopError.localized(ErrorCode.OIDC_BAD_REQUEST, detail=str(exc))


def _login_error_redirect(server: Any, public_base: str) -> str:
    """Prefer configured dashboard_origin for OIDC error pages."""
    return _service(server).login_error_frontend(public_base)


@router.get("/oidc/status", summary="OIDC login button status")
async def oidc_status(server: Any = Depends(get_server)) -> dict[str, bool | str]:
    """Return whether OIDC login is available and the configured provider label."""
    return _service(server).status()


@router.post("/oidc/start", summary="Begin OIDC login")
async def oidc_start(
    body: OidcStartBody,
    request: Request,
    server: Any = Depends(get_server),
) -> JSONResponse:
    """Create OIDC state and return the identity provider authorization URL."""
    service = _service(server)
    try:
        started = await asyncio.get_running_loop().run_in_executor(
            None,
            partial(
                service.start_login,
                redirect_after=body.redirect_after,
                public_base=_public_base(request),
            ),
        )
        state = started.get("state")
        if not isinstance(state, str) or not state:
            raise ValueError("OIDC authorization state is missing")
    except ValueError as exc:
        raise _bad_request(exc) from exc
    response = JSONResponse(started)
    response.set_cookie(
        _OIDC_STATE_COOKIE,
        state,
        max_age=_OIDC_STATE_TTL_SECONDS,
        path=_OIDC_COOKIE_PATH,
        httponly=True,
        secure=_request_is_https(request),
        samesite="lax",
    )
    return response


@router.get("/oidc/callback", summary="OIDC identity provider callback")
async def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    server: Any = Depends(get_server),
) -> RedirectResponse:
    """Complete an OIDC authorization-code callback and redirect to the dashboard."""
    public_base = _public_base(request)
    cookie_state = request.cookies.get(_OIDC_STATE_COOKIE)
    if not state or not cookie_state or not secrets.compare_digest(cookie_state, state):
        frontend = _login_error_redirect(server, public_base)
        response = RedirectResponse(f"{frontend}/login?oidc_error=state", status_code=302)
    else:
        result = await _service(server).handle_callback(
            code=code,
            state=state,
            error=error,
            public_base=public_base,
        )
        response = RedirectResponse(result.url, status_code=302)
    response.delete_cookie(
        _OIDC_STATE_COOKIE, path=_OIDC_COOKIE_PATH, secure=_request_is_https(request)
    )
    return response


@router.post("/oidc/exchange", summary="Exchange OIDC login code")
async def oidc_exchange(
    body: OidcExchangeBody, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Exchange a short-lived browser login code for the standard JWT login response."""
    try:
        user = await _service(server).exchange_login_code(body.code)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    return {
        "access_token": sign_token(
            secret, sub=user.id, uname=user.username, role=user.role.value, ttl_seconds=ttl
        ),
        "token_type": "Bearer",
        "expires_in": ttl,
        "user": _user_json(user, locale=user.locale),
    }


@router.get("/oidc/config", summary="Get OIDC provider configuration")
async def oidc_config(
    request: Request,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the admin-safe OIDC provider configuration, excluding its client secret."""
    return _service(server).get_config_for_admin(public_base=_public_base(request))


@router.put("/oidc/config", summary="Upsert OIDC provider configuration")
async def put_oidc_config(
    body: OidcConfigBody,
    request: Request,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create or update OIDC provider settings; the client secret is write-only."""
    return _service(server).put_config(
        body.model_dump(exclude_unset=True),
        public_base=_public_base(request),
    )


@router.post("/oidc/config/test", summary="Test OIDC discovery")
async def test_oidc_config(
    _: Any = Depends(current_admin), server: Any = Depends(get_server)
) -> dict[str, bool | str]:
    """Fetch OIDC discovery metadata and JWKS without changing configuration."""
    try:
        return await asyncio.get_running_loop().run_in_executor(
            None, _service(server).test_connection
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
