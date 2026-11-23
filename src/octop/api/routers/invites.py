"""Admin invite CRUD and public invite validate/redeem."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from octop.api.common.client_ip import resolve_client_ip
from octop.api.deps import get_server, require_permission, sign_token
from octop.api.routers.auth import _user_json
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.users.invites import (
    DEFAULT_EXPIRES_DAYS,
    DEFAULT_MAX_USES,
    MAX_EXPIRES_DAYS,
    MAX_INVITE_USES,
    MIN_EXPIRES_DAYS,
    InviteService,
    build_invite_url,
    check_invite_rate_limit,
    invite_path,
)
from octop.infra.users.permissions import assert_can_assign_permissions
from octop.infra.utils.locale import resolve_request_locale

admin_router = APIRouter()
public_router = APIRouter()


def _service(server: Any) -> InviteService:
    return InviteService(server.services)


def _client_id(request: Request) -> str:
    """Trusted client address for invite rate limiting (see ``resolve_client_ip``)."""
    return resolve_client_ip(request)


def _public_base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _with_url(payload: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    code = str(payload["code"])
    return {
        **payload,
        "invite_path": invite_path(code),
        "invite_url": build_invite_url(base_url, code),
    }


class InviteCreateBody(BaseModel):
    note: str | None = Field(default=None, max_length=200)
    expires_in_days: int = Field(
        default=DEFAULT_EXPIRES_DAYS,
        ge=MIN_EXPIRES_DAYS,
        le=MAX_EXPIRES_DAYS,
    )
    max_uses: int = Field(
        default=DEFAULT_MAX_USES,
        ge=1,
        le=MAX_INVITE_USES,
        strict=True,
        description="Number of successful registrations allowed before the invite turns off.",
    )
    role: str | None = Field(
        default=None,
        description="Role-template public id stored on the invite. Applied at redeem time.",
    )


class InviteResponse(BaseModel):
    id: int
    code: str
    note: str | None
    created_by: int
    created_at: int
    expires_at: int
    used_at: int | None
    used_by_user_id: int | None
    revoked_at: int | None
    enabled: bool
    use_count: int = Field(description="Total successful registrations with this invite.")
    max_uses: int | None = Field(description="Registration limit. Null for legacy unlimited links.")
    status: Literal["active", "disabled", "expired"]
    role_name: str | None
    role: str | None
    invite_path: str
    invite_url: str


class InviteUpdateBody(BaseModel):
    enabled: bool = Field(description="Whether this invite can be used for registration.")


class InviteUser(BaseModel):
    id: int
    username: str
    display_name: str | None
    email: str | None
    created_at: int
    redeemed_at: int


class InviteUsersPage(BaseModel):
    users: list[InviteUser]
    total: int
    page: int
    page_size: int


class InviteValidateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class InviteRedeemBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=254)


@admin_router.get("", response_model=list[InviteResponse], summary="List user invites")
async def list_invites(
    request: Request,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    base = _public_base(request)
    return [_with_url(row, base_url=base) for row in _service(server).list_all()]


@admin_router.post(
    "", status_code=201, response_model=InviteResponse, summary="Create a user invite"
)
async def create_invite(
    body: InviteCreateBody,
    request: Request,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    role_name: str | None = None
    role_id: str | None = None
    if body.role is not None:
        from octop.infra.db.repos.user_roles import UserRoleRepo

        role = UserRoleRepo(server.services.db).get(body.role)
        if role is None:
            raise OctopError(ErrorCode.NOT_FOUND, "role not found")
        if role.is_admin and not actor.is_admin:
            raise OctopError(
                ErrorCode.FORBIDDEN,
                "only an administrator can invite the administrator role",
            )
        if not role.is_admin:
            assert_can_assign_permissions(actor, list(role.permissions))
        role_name = role.user_role_name
        role_id = role.user_role_id
    row = _service(server).create(
        created_by=actor.id,
        actor_username=actor.username,
        note=body.note,
        expires_in_days=body.expires_in_days,
        max_uses=body.max_uses,
        role_name=role_name,
        role=role_id,
    )
    from octop.infra.db.repos.invites import invite_status_payload

    return _with_url(invite_status_payload(row), base_url=_public_base(request))


@admin_router.post(
    "/{invite_id}/revoke", response_model=InviteResponse, summary="Disable an invite"
)
async def revoke_invite(
    invite_id: int,
    request: Request,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    payload = _service(server).set_enabled(invite_id, enabled=False, actor=actor)
    return _with_url(payload, base_url=_public_base(request))


@admin_router.patch(
    "/{invite_id}",
    response_model=InviteResponse,
    summary="Enable or disable a user invite",
    description="An invite that reached its registration limit cannot be enabled again.",
)
async def update_invite(
    invite_id: int,
    body: InviteUpdateBody,
    request: Request,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    payload = _service(server).set_enabled(invite_id, enabled=body.enabled, actor=actor)
    return _with_url(payload, base_url=_public_base(request))


@admin_router.get(
    "/{invite_id}/users",
    response_model=InviteUsersPage,
    summary="List users registered with an invite",
)
async def list_invite_users(
    invite_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, object]:
    return _service(server).list_users(invite_id, page=page, page_size=page_size)


@public_router.post("/validate", summary="Validate an invite code")
async def validate_invite(
    body: InviteValidateBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    check_invite_rate_limit(_client_id(request))
    return _service(server).validate(body.code)


@public_router.post("/redeem", summary="Redeem an invite and create a user")
async def redeem_invite(
    body: InviteRedeemBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a user from an enabled invite and return a login token.

    Also bootstraps the same default ``general-assistant`` expert as the setup
    wizard (auto-allocated agent id; setup pins ``main`` for the first admin).
    """
    check_invite_rate_limit(_client_id(request))
    locale = resolve_request_locale(request)
    user = await server.user_manager.create_from_invite(
        code=body.code,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        email=body.email,
        locale=locale,
    )
    from octop.infra.agents.experts.default_agent import try_bootstrap_default_agent

    await try_bootstrap_default_agent(server, user_id=user.id, locale=user.locale)
    server.services.user_repo.touch_last_login(user.id)
    from octop.infra.auth.tokens import PURPOSE_ACCESS

    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    row = server.services.user_repo.get(user.id)
    mfa_version = int(row.mfa_version) if row is not None else 0
    password_version = int(row.password_version) if row is not None else 0
    token = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_ACCESS,
        ttl_seconds=ttl,
        mfa_version=mfa_version,
        password_version=password_version,
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ttl,
        "user": _user_json(user, locale=user.locale),
    }
