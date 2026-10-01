"""Pluggable OAuth SSO HTTP routes (Feishu and future providers)."""

from __future__ import annotations

import asyncio
import secrets
from functools import partial
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from octop.api.common.public_base import resolve_public_base
from octop.api.common.sso_cookie import (
    cookie_state,
    delete_sso_state_cookie,
    set_sso_state_cookie,
)
from octop.api.deps import current_user, get_server, require_permission
from octop.api.routers.auth_oidc import exchange_login_code_response
from octop.infra.auth.sso.service import SsoService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User

router = APIRouter()

SsoKind = Literal["oidc", "feishu", "dingtalk", "wecom"]


class OauthStartBody(BaseModel):
    kind: SsoKind
    redirect_after: str | None = None


class OauthExchangeBody(BaseModel):
    code: str = Field(min_length=1)


class OauthProviderPutBody(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None
    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: str | None = None
    dashboard_origin: str | None = None
    extra: dict[str, Any] | None = None


def _service(server: Any) -> SsoService:
    return cast(SsoService, server.sso_service)


def _public_base(request: Request) -> str:
    return resolve_public_base(request)


def _bad_request(exc: ValueError) -> OctopError:
    return OctopError.localized(ErrorCode.OIDC_BAD_REQUEST, detail=str(exc))


def _login_error_redirect(server: Any, public_base: str) -> str:
    return _service(server).login_error_frontend(public_base)


@router.get("/oauth/status", summary="SSO login button status")
async def oauth_status(server: Any = Depends(get_server)) -> dict[str, Any]:
    """Return enabled dashboard SSO providers for the login page."""
    return _service(server).providers_status()


@router.post("/oauth/start", summary="Begin OAuth login")
async def oauth_start(
    body: OauthStartBody,
    request: Request,
    server: Any = Depends(get_server),
) -> JSONResponse:
    """Create login state and return the identity provider authorization URL."""
    service = _service(server)
    try:
        started = await asyncio.get_running_loop().run_in_executor(
            None,
            partial(
                service.start_login_for_kind,
                body.kind,
                redirect_after=body.redirect_after,
                public_base=_public_base(request),
            ),
        )
        state = started.get("state")
        if not isinstance(state, str) or not state:
            raise ValueError("OAuth authorization state is missing")
    except ValueError as exc:
        raise _bad_request(exc) from exc
    response = JSONResponse(started)
    set_sso_state_cookie(response, request, state)
    return response


@router.get("/oauth/callback", summary="OAuth identity provider callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    authCode: str | None = None,
    state: str | None = None,
    error: str | None = None,
    server: Any = Depends(get_server),
) -> RedirectResponse:
    """Complete an OAuth authorization-code callback and redirect to the dashboard."""
    public_base = _public_base(request)
    stored = cookie_state(request)
    auth_code = code or authCode
    if not state or not stored or not secrets.compare_digest(stored, state):
        frontend = _login_error_redirect(server, public_base)
        response = RedirectResponse(f"{frontend}/login?oidc_error=state", status_code=302)
    else:
        result = await _service(server).handle_callback(
            code=auth_code,
            state=state,
            error=error,
            public_base=public_base,
        )
        response = RedirectResponse(result.url, status_code=302)
    delete_sso_state_cookie(response, request)
    return response


@router.post("/oauth/exchange", summary="Exchange OAuth login code")
async def oauth_exchange(
    body: OauthExchangeBody, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Exchange a short-lived browser login code for the standard JWT login response."""
    return await exchange_login_code_response(body.code, server)


@router.post("/oauth/bind/start", summary="Begin OAuth account linking")
async def oauth_bind_start(
    body: OauthStartBody,
    request: Request,
    user: User = Depends(current_user),
    server: Any = Depends(get_server),
) -> JSONResponse:
    """Start an OAuth flow that binds the identity to the current user."""
    service = _service(server)
    try:
        started = await asyncio.get_running_loop().run_in_executor(
            None,
            partial(
                service.start_login_for_kind,
                body.kind,
                redirect_after=body.redirect_after,
                public_base=_public_base(request),
                bind_user_id=user.id,
            ),
        )
        state = started.get("state")
        if not isinstance(state, str) or not state:
            raise ValueError("OAuth authorization state is missing")
    except ValueError as exc:
        raise _bad_request(exc) from exc
    response = JSONResponse(started)
    set_sso_state_cookie(response, request, state)
    return response


class OauthUnbindBody(BaseModel):
    kind: SsoKind


@router.post("/oauth/unbind", summary="Unlink SSO identity")
async def oauth_unbind(
    body: OauthUnbindBody,
    user: User = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Unlink one SSO identity. Requires a local password when it is the last login method."""
    from octop.api.routers.auth import me_payload

    updated = await server.user_manager.unbind_sso_identity(user_id=user.id, kind=body.kind)
    return me_payload(updated, server)


@router.get("/oauth/providers/{kind}", summary="Get OAuth provider configuration")
async def get_oauth_provider(
    kind: SsoKind,
    request: Request,
    _: Any = Depends(require_permission("sso")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return admin-safe provider configuration; the client secret is omitted."""
    if kind == "oidc":
        return _service(server).get_config_for_admin(public_base=_public_base(request))
    return _service(server).get_config_for_kind(kind, public_base=_public_base(request))


@router.put("/oauth/providers/{kind}", summary="Upsert OAuth provider configuration")
async def put_oauth_provider(
    kind: SsoKind,
    body: OauthProviderPutBody,
    request: Request,
    _: Any = Depends(require_permission("sso")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create or update provider settings; the client secret is write-only."""
    dumped = body.model_dump(exclude_unset=True)
    try:
        result = _service(server).put_config_for_kind(
            kind,
            dumped,
            public_base=_public_base(request),
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if kind == "oidc":
        result.pop("kind", None)
        result.pop("extra", None)
    return result


@router.post("/oauth/providers/{kind}/test", summary="Test OAuth provider connection")
async def test_oauth_provider(
    kind: SsoKind,
    _: Any = Depends(require_permission("sso")),
    server: Any = Depends(get_server),
) -> dict[str, bool | str]:
    """Verify provider credentials without changing configuration."""
    try:
        return await asyncio.get_running_loop().run_in_executor(
            None, partial(_service(server).test_connection_for_kind, kind)
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
