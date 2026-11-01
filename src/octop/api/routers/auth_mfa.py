"""MFA / passkey HTTP routes under ``/api/auth``."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from octop.api.common.client_ip import resolve_client_ip
from octop.api.deps import current_user, get_server
from octop.api.routers.auth import _user_json, me_payload
from octop.infra.auth.mfa import MfaService
from octop.infra.auth.mfa import reauth as reauth_mod
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


def _mfa(server: Any) -> MfaService:
    return MfaService(server.services)


def _origin(request: Request) -> str:
    origin = request.headers.get("origin") or ""
    if not origin:
        raise OctopError(ErrorCode.WEBAUTHN_CONFIG_INVALID, "Origin header required")
    return origin


def _reauth_token(
    *,
    header: str | None,
    body_token: str | None,
) -> str:
    token = (header or body_token or "").strip()
    if not token:
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required")
    return token


class ReauthBody(BaseModel):
    password: str = Field(min_length=1)


class MfaVerifyBody(BaseModel):
    mfa_token: str = Field(min_length=1)
    method: Literal["totp", "webauthn", "recovery"]
    code: str | None = None
    credential: dict[str, Any] | None = None


class MfaPasskeyOptionsBody(BaseModel):
    mfa_token: str = Field(min_length=1)


class PasskeyLoginVerifyBody(BaseModel):
    credential: dict[str, Any]


class TotpConfirmBody(BaseModel):
    code: str = Field(min_length=6, max_length=16)
    reauth_token: str | None = None


class PasskeyRegisterVerifyBody(BaseModel):
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=64)
    reauth_token: str | None = None


class ReauthTokenBody(BaseModel):
    reauth_token: str | None = None


@router.post("/mfa/reauth", summary="Prove password for MFA management")
async def mfa_reauth(
    body: ReauthBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    await reauth_mod.prove_password(
        server.services,
        user_id=user.id,
        password=body.password,
        ldap_service=getattr(server, "ldap_service", None),
        ldap_bind_throttle=getattr(server, "ldap_bind_throttle", None),
        client_ip=resolve_client_ip(request),
    )
    token = reauth_mod.issue_reauth_token(
        server.services,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )
    return {"reauth_token": token, "expires_in": 300}


@router.post("/mfa/verify", summary="Complete MFA challenge after password login")
async def mfa_verify(
    body: MfaVerifyBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    origin = request.headers.get("origin")
    result = _mfa(server).verify_mfa(
        mfa_token=body.mfa_token,
        method=body.method,
        code=body.code,
        credential=body.credential,
        origin=origin,
        user_manager=server.user_manager,
    )
    user = server.user_manager.get_by_id(int(result["user"]["id"]))
    if user is not None:
        result["user"] = _user_json(user, locale=user.locale)
    return result


@router.post("/mfa/passkey/options", summary="Passkey assertion options for MFA")
async def mfa_passkey_options(
    body: MfaPasskeyOptionsBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return _mfa(server).mfa_passkey_options(
        mfa_token=body.mfa_token,
        origin=_origin(request),
    )


@router.post("/passkey/login/options", summary="Passwordless passkey options")
async def passkey_login_options(
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return _mfa(server).passkey_login_options(origin=_origin(request))


@router.post("/passkey/login/verify", summary="Passwordless passkey verify")
async def passkey_login_verify(
    body: PasskeyLoginVerifyBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    result = _mfa(server).passkey_login_verify(
        credential=body.credential,
        origin=_origin(request),
        user_manager=server.user_manager,
    )
    user = server.user_manager.get_by_id(int(result["user"]["id"]))
    if user is not None:
        result["user"] = _user_json(user, locale=user.locale)
    return result


@router.get("/mfa/status", summary="Current user's MFA enrollment status")
async def mfa_status(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    return _mfa(server).status(user.id)


@router.post("/mfa/totp/begin", summary="Begin TOTP enrollment")
async def totp_begin(
    body: ReauthTokenBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    return _mfa(server).totp_begin(user, reauth_token=token)


@router.post("/mfa/totp/confirm", summary="Confirm TOTP enrollment")
async def totp_confirm(
    body: TotpConfirmBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    result = _mfa(server).totp_confirm(user, reauth_token=token, code=body.code)
    result["user"] = me_payload(user, server)
    return result


@router.delete("/mfa/totp", summary="Disable TOTP")
async def totp_disable(
    body: ReauthTokenBody | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    body = body or ReauthTokenBody()
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    result = _mfa(server).totp_disable(user, reauth_token=token)
    result["user"] = me_payload(user, server)
    return result


@router.post("/mfa/passkey/register/options", summary="Passkey registration options")
async def passkey_register_options(
    body: ReauthTokenBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    return _mfa(server).passkey_register_options(user, reauth_token=token, origin=_origin(request))


@router.post("/mfa/passkey/register/verify", summary="Verify passkey registration")
async def passkey_register_verify(
    body: PasskeyRegisterVerifyBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    result = _mfa(server).passkey_register_verify(
        user,
        reauth_token=token,
        credential=body.credential,
        origin=_origin(request),
        name=body.name,
    )
    result["user"] = me_payload(user, server)
    return result


@router.delete(
    "/mfa/passkey/{credential_id}",
    summary="Remove a passkey",
)
async def passkey_delete(
    credential_id: str,
    body: ReauthTokenBody | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    body = body or ReauthTokenBody()
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    result = _mfa(server).passkey_delete(user, reauth_token=token, credential_id=credential_id)
    result["user"] = me_payload(user, server)
    return result


@router.post("/mfa/recovery/regenerate", summary="Regenerate recovery codes")
async def recovery_regenerate(
    body: ReauthTokenBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    x_octop_reauth: str | None = Header(None, alias="X-Octop-Reauth"),
) -> dict[str, Any]:
    token = _reauth_token(header=x_octop_reauth, body_token=body.reauth_token)
    result = _mfa(server).recovery_regenerate(user, reauth_token=token)
    result["user"] = me_payload(user, server)
    return result
