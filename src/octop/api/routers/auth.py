"""Login / logout / me / change-password."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, sign_token
from octop.infra.auth.captcha import current_env, ensure_captcha, load_effective, public_config
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.permissions import effective_permissions
from octop.infra.utils.locale import normalize_locale

router = APIRouter()


def _user_json(user: Any, *, locale: str | None = None) -> dict[str, Any]:
    loc = normalize_locale(locale)
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "display_name": user.display_name,
        "locale": loc,
        "permissions": effective_permissions(user),
    }


def me_payload(user: Any, server: Any) -> dict[str, Any]:
    """Profile JSON for ``/auth/me`` and OAuth bind/unbind responses."""
    payload = _user_json(user, locale=user.locale)
    row = server.user_manager.get_row(user.id)
    if row is None:
        payload["sso_linked"] = False
        payload["sso_kind"] = None
        payload["sso_identities"] = []
        payload["has_password"] = True
        return payload
    identities = [{"kind": item.kind} for item in server.user_manager.list_sso_identities(user.id)]
    payload["sso_identities"] = identities
    payload["sso_linked"] = bool(identities)
    payload["sso_kind"] = identities[0]["kind"] if identities else None
    payload["has_password"] = row.password_hash is not None
    return payload


class LoginBody(BaseModel):
    username: str
    password: str
    captcha_token: str | None = Field(default=None, max_length=4096)


class CaptchaPublicResponse(BaseModel):
    provider: str
    site_key: str | None = None


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.get(
    "/captcha",
    summary="Public login captcha config",
    response_model=CaptchaPublicResponse,
    response_model_exclude_none=True,
)
async def get_captcha(server: Any = Depends(get_server)) -> CaptchaPublicResponse:
    """Return the active login captcha provider and public site key. No secret."""
    if server.user_manager.count() == 0:
        raise OctopError(ErrorCode.SETUP_REQUIRED, "initial admin not created")
    effective = load_effective(
        server.services.settings_repo,
        server.services.secret_repo,
        current_env(),
    )
    return CaptchaPublicResponse.model_validate(public_config(effective))


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/login", summary="Sign in")
async def login(
    body: LoginBody, request: Request, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Exchange username (or email) and password for a JWT access token and user profile."""
    if server.user_manager.count() == 0:
        raise OctopError(ErrorCode.SETUP_REQUIRED, "initial admin not created")
    server.user_manager.raise_if_login_locked(body.username)
    effective = load_effective(
        server.services.settings_repo,
        server.services.secret_repo,
        current_env(),
    )
    await ensure_captcha(effective, body.captcha_token, _client_ip(request))
    user = await server.user_manager.authenticate(body.username, body.password)
    if user is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid credentials")
    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    token = sign_token(
        secret, sub=user.id, uname=user.username, role=user.role.value, ttl_seconds=ttl
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ttl,
        "user": _user_json(user, locale=user.locale),
    }


@router.post("/logout", status_code=204, summary="Sign out")
async def logout(user: Any = Depends(current_user), server: Any = Depends(get_server)) -> Response:
    """Record an audit event for the current session. JWTs are stateless and not revoked server-side."""
    server.services.audit_repo.write(actor=user.username, action="auth.logout")
    return Response(status_code=204)


@router.get("/me", summary="Current user profile")
async def me(
    user: Any = Depends(current_user), server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Return the authenticated user's id, username, role, display name, and locale."""
    return me_payload(user, server)


@router.post("/change-password", status_code=204, summary="Change password")
async def change_password(
    body: ChangePasswordBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    """Verify the old password and set a new one for the current user."""
    await server.user_manager.change_password(user.username, body.old_password, body.new_password)
    return Response(status_code=204)


class UpdateMeBody(BaseModel):
    display_name: str | None = None
    locale: str | None = None


@router.patch("/me", summary="Update profile")
async def update_me(
    body: UpdateMeBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Update the current user's display name and/or locale.

    Use ``model_dump(exclude_unset=True)`` so an explicitly-provided ``null``
    (e.g. ``{"display_name": null}``) clears the field, while an omitted field
    leaves the current value untouched.
    """
    provided = body.model_dump(exclude_unset=True)
    if "display_name" in provided:
        await server.user_manager.set_display_name(user.username, body.display_name)
    if "locale" in provided:
        await server.user_manager.set_locale(user.username, body.locale)
    updated = server.user_manager.get(user.username)
    assert updated is not None
    return _user_json(updated, locale=updated.locale)
