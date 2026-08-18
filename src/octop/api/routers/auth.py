"""Login / logout / me / change-password."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from octop.api.deps import current_user, get_server, sign_token
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.permissions import effective_permissions
from octop.infra.utils.locale import normalize_locale

router = APIRouter()


def _user_json(
    user: Any,
    *,
    locale: str | None = None,
    server: Any = None,
) -> dict[str, Any]:
    loc = normalize_locale(locale)
    avatar_url: str | None = None
    if server is not None:
        avatar_ref = server.user_manager.get_avatar_reference(user.id)
        if avatar_ref:
            avatar_url = f"/api/avatars/{avatar_ref}"
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "display_name": user.display_name,
        "locale": loc,
        "permissions": effective_permissions(user),
        "avatar_url": avatar_url,
    }


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", summary="Sign in")
async def login(body: LoginBody, server: Any = Depends(get_server)) -> dict[str, Any]:
    """Exchange username and password for a JWT access token and user profile."""
    if server.user_manager.count() == 0:
        raise OctopError(ErrorCode.SETUP_REQUIRED, "initial admin not created")
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
        "user": _user_json(user, locale=user.locale, server=server),
    }


@router.post("/logout", status_code=204, summary="Sign out")
async def logout(user: Any = Depends(current_user), server: Any = Depends(get_server)) -> Response:
    """Record an audit event for the current session. JWTs are stateless and not revoked server-side."""
    server.services.audit_repo.write(actor=user.username, action="auth.logout")
    return Response(status_code=204)


@router.get("/me", summary="Current user profile")
async def me(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the authenticated user's id, username, role, display name, and locale."""
    return _user_json(user, locale=user.locale, server=server)


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
    return _user_json(updated, locale=updated.locale, server=server)
