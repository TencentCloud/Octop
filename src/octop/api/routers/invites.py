"""Admin invite CRUD and public invite validate/redeem."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission, sign_token
from octop.api.routers.auth import _user_json
from octop.infra.users.identity import User
from octop.infra.users.invites import (
    DEFAULT_EXPIRES_DAYS,
    MAX_EXPIRES_DAYS,
    MIN_EXPIRES_DAYS,
    InviteService,
    build_invite_url,
    check_invite_rate_limit,
    invite_path,
)
from octop.infra.utils.locale import resolve_request_locale

admin_router = APIRouter()
public_router = APIRouter()


def _service(server: Any) -> InviteService:
    return InviteService(server.services)


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


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


class InviteValidateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class InviteRedeemBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=128)


@admin_router.get("", summary="List user invites")
async def list_invites(
    request: Request,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    base = _public_base(request)
    return [_with_url(row, base_url=base) for row in _service(server).list_all()]


@admin_router.post("", status_code=201, summary="Create a user invite")
async def create_invite(
    body: InviteCreateBody,
    request: Request,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = _service(server).create(
        created_by=actor.id,
        actor_username=actor.username,
        note=body.note,
        expires_in_days=body.expires_in_days,
    )
    from octop.infra.db.repos.invites import invite_status_payload

    return _with_url(invite_status_payload(row), base_url=_public_base(request))


@admin_router.post("/{invite_id}/revoke", summary="Revoke an unused invite")
async def revoke_invite(
    invite_id: int,
    request: Request,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    payload = _service(server).revoke(invite_id, actor_username=actor.username)
    return _with_url(payload, base_url=_public_base(request))


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
    """Create a regular user from a one-time invite and return a login token.

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
        locale=locale,
    )
    from octop.infra.agents.default_agent import try_bootstrap_default_agent

    await try_bootstrap_default_agent(server, user_id=user.id, locale=user.locale)
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
