"""Admin CRUD for users."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User
from octop.infra.users.permissions import PERMISSIONS
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


class UserCreateBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    role: str = "user"
    display_name: str | None = None
    email: str | None = Field(default=None, max_length=254)
    permissions: list[str] = Field(default_factory=list)


class UserPatchBody(BaseModel):
    role: str | None = None
    display_name: str | None = None
    email: str | None = Field(default=None, max_length=254)
    disabled: bool | None = None
    permissions: list[str] | None = None


class ResetPasswordBody(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)


def _row_to_dict(r: Any) -> dict[str, Any]:
    now = int(time.time())
    locked_until = int(getattr(r, "login_locked_until", 0) or 0)
    locked = locked_until > now and not bool(r.disabled)
    retry_after = max(0, locked_until - now) if locked else 0
    return {
        "id": r.id,
        "username": r.username,
        "role": r.role,
        "display_name": r.display_name,
        "email": r.email,
        "has_password": r.password_hash is not None,
        "sso_linked": r.sso_provider_id is not None and r.sso_subject is not None,
        "disabled": bool(r.disabled),
        "login_failed_count": int(getattr(r, "login_failed_count", 0) or 0),
        "login_locked": locked,
        "login_locked_until": locked_until if locked else 0,
        "login_retry_after_seconds": retry_after,
        "created_at": int(r.created_at),
        "permissions": list(getattr(r, "permissions", None) or []),
    }


def _assert_can_assign(actor: User, permissions: list[str]) -> None:
    """Non-admin actors may only grant permissions they themselves hold."""
    if actor.is_admin:
        return
    missing = sorted(set(permissions) - set(actor.permissions or []))
    if missing:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "cannot grant permissions you do not hold",
            details={"missing": missing},
        )


def _can_manage_users(row: Any) -> bool:
    if str(getattr(row, "role", "")) == "admin":
        return True
    return "users" in (getattr(row, "permissions", None) or [])


def _assert_not_last_user_manager(
    server: Any,
    *,
    actor: User,
    target_user_id: int,
    new_permissions: list[str],
) -> None:
    """Refuse stripping ``users`` if no one else could manage users afterward."""
    if target_user_id != actor.id:
        return
    if "users" in new_permissions:
        return
    managers = [
        u
        for u in server.user_manager.list_all(include_disabled=False)
        if _can_manage_users(u) and int(u.id) != target_user_id
    ]
    if not managers:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "cannot remove own user management permission",
        )


@router.get("/permissions", summary="List assignable permission catalog")
async def list_permission_catalog(
    request: Request,
    _: User = Depends(current_user),
) -> list[dict[str, str]]:
    """Return all permissions, localized by Accept-Language, for the UI picker."""
    locale = resolve_request_locale(request)
    items: list[dict[str, str]] = []
    zh = locale.startswith("zh")
    for key, p in PERMISSIONS.items():
        labels = [(p.label_zh, p.label_en), *p.extra_tabs]
        for label_zh, label_en in labels:
            items.append(
                {
                    "key": key,
                    "category": p.category,
                    "label": label_zh if zh else label_en,
                    "page": p.page,
                    "page_label": (p.page_zh if zh else p.page_en) if p.page else "",
                }
            )
    return items


@router.get("")
async def list_users(
    _: Any = Depends(require_permission("users")), server: Any = Depends(get_server)
) -> list[dict[str, Any]]:
    rows = server.user_manager.list_all(include_disabled=True)
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
async def create_user(
    body: UserCreateBody,
    actor: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _assert_can_assign(actor, body.permissions)
    role = Role(body.role)
    user = await server.user_manager.create(
        username=body.username,
        password=body.password,
        role=role,
        display_name=body.display_name,
        email=body.email,
        permissions=body.permissions,
    )
    row = server.user_manager.get_row(user.id)
    assert row is not None
    return _row_to_dict(row)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    return _row_to_dict(row)


@router.patch("/{user_id}")
async def patch_user(
    user_id: int,
    body: UserPatchBody,
    actor: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    if body.permissions is not None:
        _assert_can_assign(actor, body.permissions)
        _assert_not_last_user_manager(
            server,
            actor=actor,
            target_user_id=user_id,
            new_permissions=body.permissions,
        )
    if body.role is not None:
        if user_id == actor.id and Role(body.role) is not Role.ADMIN:
            raise OctopError(ErrorCode.FORBIDDEN, "cannot demote yourself")
        await server.user_manager.set_role(row.username, Role(body.role))
    if body.display_name is not None:
        await server.user_manager.set_display_name(row.username, body.display_name)
    if "email" in body.model_fields_set:
        await server.user_manager.set_email(row.username, body.email)
    if body.disabled is True:
        await server.user_manager.disable(row.username)
    elif body.disabled is False:
        await server.user_manager.enable(row.username)
    if body.permissions is not None:
        await server.user_manager.set_permissions(row.username, body.permissions)
    updated = server.user_manager.get_row(user_id)
    assert updated is not None
    return _row_to_dict(updated)


@router.post("/{user_id}/unlock-login", status_code=204, summary="Clear login lockout")
async def unlock_user_login(
    user_id: int,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> None:
    """Clear failed-login counter and temporary lock for a user."""
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    await server.user_manager.unlock_login(row.username)


@router.post("/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: int,
    body: ResetPasswordBody,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> None:
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    await server.user_manager.reset_password(row.username, body.new_password)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    actor: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> None:
    if user_id == actor.id:
        raise OctopError(ErrorCode.FORBIDDEN, "cannot delete yourself")
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    await server.user_manager.remove(row.username)
