"""Admin CRUD for users."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_admin, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role

router = APIRouter()


class UserCreateBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    role: str = "user"
    display_name: str | None = None


class UserPatchBody(BaseModel):
    role: str | None = None
    display_name: str | None = None
    disabled: bool | None = None


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
    }


@router.get("")
async def list_users(
    _: Any = Depends(current_admin), server: Any = Depends(get_server)
) -> list[dict[str, Any]]:
    rows = server.user_manager.list_all(include_disabled=True)
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
async def create_user(
    body: UserCreateBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    role = Role(body.role)
    user = await server.user_manager.create(
        username=body.username,
        password=body.password,
        role=role,
        display_name=body.display_name,
    )
    row = server.user_manager.get_row(user.id)
    assert row is not None
    return _row_to_dict(row)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    _: Any = Depends(current_admin),
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
    admin: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    if body.role is not None:
        if user_id == admin.id and Role(body.role) is not Role.ADMIN:
            raise OctopError(ErrorCode.FORBIDDEN, "cannot demote yourself")
        await server.user_manager.set_role(row.username, Role(body.role))
    if body.display_name is not None:
        await server.user_manager.set_display_name(row.username, body.display_name)
    if body.disabled is True:
        await server.user_manager.disable(row.username)
    elif body.disabled is False:
        await server.user_manager.enable(row.username)
    updated = server.user_manager.get_row(user_id)
    assert updated is not None
    return _row_to_dict(updated)


@router.post("/{user_id}/unlock-login", status_code=204, summary="Clear login lockout")
async def unlock_user_login(
    user_id: int,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    """Clear failed-login counter and temporary lock for a user (admin)."""
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    await server.user_manager.unlock_login(row.username)


@router.post("/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: int,
    body: ResetPasswordBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    await server.user_manager.reset_password(row.username, body.new_password)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    admin: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    if user_id == admin.id:
        raise OctopError(ErrorCode.FORBIDDEN, "cannot delete yourself")
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    await server.user_manager.remove(row.username)
