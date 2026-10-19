"""Login / logout / me / change-password."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from pydantic import BaseModel, Field

from octop.api.common.client_ip import resolve_client_ip
from octop.api.deps import current_user, get_server, sign_token
from octop.infra.auth.captcha import current_env, ensure_captcha, load_effective, public_config
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.email import normalize_email
from octop.infra.users.permissions import effective_permissions
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_json(user: Any, *, locale: str | None = None) -> dict[str, Any]:
    loc = normalize_locale(locale)
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
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
    from octop.infra.users.profile_avatar import profile_avatar_url

    payload["avatar_icon"] = row.avatar_icon
    payload["avatar_url"] = profile_avatar_url(
        server.services.paths.user_avatars_dir,
        str(user.id),
        f"/api/users/{user.id}/avatar",
    )
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
    """Trusted client address for throttling and captcha verification.

    A spoofable value here would let a caller reset the directory bind throttle
    by varying one header, so this delegates to the shared resolver.
    """
    return resolve_client_ip(request)


def _local_row(server: Any, identifier: str) -> Any:
    """The local account for a username-or-email identifier, when one exists."""
    text = (identifier or "").strip()
    if not text:
        return None
    repo = server.services.user_repo
    row = repo.get_by_username(text)
    if row is None:
        email = normalize_email(text)
        if email is not None:
            row = repo.get_by_email(email)
    return row


def _directory_may_own(row: Any) -> bool:
    """Whether an unresolved local login may legitimately belong to the directory.

    ``False`` as soon as the identifier has a local password of its own: the
    submitted secret then belongs to *this* system, and forwarding it would hand a
    local credential to another server and spend one attempt against the
    directory's own lockout policy. Such an account still signs in — the local
    check runs first and succeeds on the right password — it just never falls
    through on a wrong one.

    Only identifiers with no local password, or none at all, may fall through.
    """
    if row is None:
        return True
    return not row.password_hash


async def _authenticate_ldap(server: Any, username: str, password: str, client_ip: str) -> Any:
    """Bind against the directory, throttled before the attempt reaches it."""
    service = server.ldap_service
    if not service.is_enabled():
        return None
    throttle = server.ldap_bind_throttle
    _raise_if_throttled(throttle.retry_after(username, client_ip))
    # An OctopError raised here (LDAP_UNAVAILABLE, LDAP_GROUP_NOT_ALLOWED, …) is a
    # real answer and propagates unchanged. Outages are not credential failures,
    # so they never count towards the brute-force budget.
    identity = await asyncio.get_running_loop().run_in_executor(
        None, service.directory_authenticate, username, password
    )
    if identity is None:
        retry_after = throttle.record_failure(username, client_ip)
        server.services.audit_repo.write(actor=username, action="auth.ldap_failed", target=username)
        _raise_if_throttled(retry_after)
        return None
    throttle.clear(username, client_ip)
    return await service.resolve_user(identity)


def _raise_if_throttled(retry_after: int) -> None:
    if retry_after <= 0:
        return
    minutes = max(1, (retry_after + 59) // 60)
    raise OctopError(
        ErrorCode.LOGIN_LOCKED,
        "too many directory login attempts",
        details={"retry_after_seconds": retry_after, "minutes": minutes},
    )


@router.post("/login", summary="Sign in")
async def login(
    body: LoginBody, request: Request, server: Any = Depends(get_server)
) -> dict[str, Any]:
    """Exchange username (or email) and password for a JWT access token and user profile.

    When no local password matches, the credentials are retried against the
    configured LDAP directory — but only for identifiers the directory could
    legitimately own. Any account holding its own password stops at the local
    check, so a mistyped local password is never forwarded to the directory nor
    counted against the directory's lockout policy.
    """
    if server.user_manager.count() == 0:
        raise OctopError(ErrorCode.SETUP_REQUIRED, "initial admin not created")
    server.user_manager.raise_if_login_locked(body.username)
    effective = load_effective(
        server.services.settings_repo,
        server.services.secret_repo,
        current_env(),
    )
    client_ip = _client_ip(request)
    await ensure_captcha(effective, body.captcha_token, client_ip)
    user = await server.user_manager.authenticate(body.username, body.password)
    if user is None:
        local_row = _local_row(server, body.username)
        if _directory_may_own(local_row):
            user = await _authenticate_ldap(server, body.username, body.password, client_ip)
    if user is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid credentials")
    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    token = sign_token(secret, sub=user.id, uname=user.username, role=user.role, ttl_seconds=ttl)
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
    avatar_icon: str | None = Field(default=None, max_length=32)


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
    if "avatar_icon" in provided:
        from octop.infra.users.profile_avatar import clean_avatar_icon, delete_profile_avatar

        server.services.user_repo.set_avatar_icon(user.id, clean_avatar_icon(body.avatar_icon))
        delete_profile_avatar(server.services.paths.user_avatars_dir, str(user.id))
    updated = server.user_manager.get(user.username)
    assert updated is not None
    return me_payload(updated, server)


@router.post("/me/avatar", status_code=201, summary="Upload the current user's portrait")
async def upload_my_avatar(
    file: UploadFile = File(...),  # noqa: B008
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str | None]:
    from octop.infra.users.profile_avatar import profile_avatar_url, write_profile_avatar

    write_profile_avatar(
        server.services.paths.user_avatars_dir,
        str(user.id),
        await file.read(),
    )
    return {
        "avatar_url": profile_avatar_url(
            server.services.paths.user_avatars_dir,
            str(user.id),
            f"/api/users/{user.id}/avatar",
        )
    }


@router.delete("/me/avatar", status_code=204, summary="Remove the current user's portrait")
async def delete_my_avatar(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    from octop.infra.users.profile_avatar import delete_profile_avatar

    delete_profile_avatar(server.services.paths.user_avatars_dir, str(user.id))
    return Response(status_code=204)
