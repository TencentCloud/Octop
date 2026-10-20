"""User groups.

Membership changes require the users permission. Listing group names is also
open to people who can edit a resource that has a visibility picker.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.groups import empty_group_access, group_access_by_group
from octop.infra.users.identity import User
from octop.infra.users.permissions import user_has_permission
from octop.infra.users.profile_avatar import (
    avatar_response,
    clean_avatar_icon,
    delete_profile_avatar,
    profile_avatar_url,
    write_profile_avatar,
)

router = APIRouter()

_CATALOG_KEYS = (
    "users",
    "skill_packages",
    "knowledge_bases",
    "connectors",
    "providers",
    "storage_backends",
)


class UserGroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    avatar_icon: str | None = Field(default=None, max_length=32)


class UserGroupPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    avatar_icon: str | None = Field(default=None, max_length=32)


class ReplaceMembersBody(BaseModel):
    user_ids: list[int] = Field(default_factory=list)


def _clean_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise OctopError(ErrorCode.FORBIDDEN, "user group name is required", status=400)
    return name


def _clean_description(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    return text or None


def _unique_name(exc: BaseException) -> bool:
    try:
        from psycopg import errors as pg_errors
    except ImportError:
        pg_errors = None  # type: ignore[assignment]
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


async def catalog_reader(user: User = Depends(current_user)) -> User:
    if user.is_admin or any(user_has_permission(user, key) for key in _CATALOG_KEYS):
        return user
    raise OctopError(ErrorCode.FORBIDDEN, "user group catalog requires a management permission")


def _avatar_url(server: Any, user_group_id: str) -> str | None:
    return profile_avatar_url(
        server.services.paths.group_avatars_dir,
        user_group_id,
        f"/api/user-groups/{user_group_id}/avatar",
    )


def _public(
    server: Any,
    row: Any,
    *,
    member_count: int,
    member_ids: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "user_group_id": row.user_group_id,
        "name": row.name,
        "description": row.description,
        "enabled": bool(row.enabled),
        "avatar_icon": row.avatar_icon,
        "avatar_url": _avatar_url(server, row.user_group_id),
        "member_count": member_count,
        "member_ids": member_ids or [],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _require_group(server: Any, user_group_id: str) -> Any:
    row = server.services.repos.user_group_repo.get(user_group_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user group not found")
    return row


@router.get("", summary="List user groups")
async def list_user_groups(
    server: Any = Depends(get_server),
    _: User = Depends(catalog_reader),
) -> list[dict[str, Any]]:
    members = server.services.repos.user_group_member_repo.user_ids_by_group()
    access = group_access_by_group(server.services.repos)
    payloads = []
    for row in server.services.repos.user_group_repo.list_all():
        payload = _public(
            server,
            row,
            member_count=len(members.get(row.user_group_id, [])),
            member_ids=members.get(row.user_group_id, []),
        )
        payload["access"] = access.get(row.user_group_id, empty_group_access())
        payloads.append(payload)
    return payloads


@router.post("", status_code=201, summary="Create a user group")
async def create_user_group(
    body: UserGroupBody,
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> dict[str, Any]:
    try:
        row = server.services.repos.user_group_repo.create(
            name=_clean_name(body.name),
            description=_clean_description(body.description),
            enabled=body.enabled,
            avatar_icon=clean_avatar_icon(body.avatar_icon),
        )
    except Exception as exc:
        if _unique_name(exc):
            raise OctopError(
                ErrorCode.FORBIDDEN, "user group name is already in use", status=409
            ) from exc
        raise
    return _public(server, row, member_count=0)


@router.patch("/{user_group_id}", summary="Rename a user group")
async def update_user_group(
    user_group_id: str,
    body: UserGroupPatchBody,
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> dict[str, Any]:
    _require_group(server, user_group_id)
    fields = body.model_fields_set
    name = _clean_name(body.name) if body.name is not None else None
    description = _clean_description(body.description) if "description" in fields else None
    try:
        server.services.repos.user_group_repo.update(
            user_group_id,
            name=name,
            description=description,
            update_description="description" in fields,
            enabled=body.enabled if "enabled" in fields else None,
            avatar_icon=clean_avatar_icon(body.avatar_icon) if "avatar_icon" in fields else None,
            update_avatar_icon="avatar_icon" in fields,
        )
    except Exception as exc:
        if _unique_name(exc):
            raise OctopError(
                ErrorCode.FORBIDDEN, "user group name is already in use", status=409
            ) from exc
        raise
    row = _require_group(server, user_group_id)
    member_ids = server.services.repos.user_group_member_repo.user_ids_for_group(user_group_id)
    return _public(server, row, member_count=len(member_ids), member_ids=member_ids)


@router.delete("/{user_group_id}", status_code=204, summary="Delete a user group")
async def delete_user_group(
    user_group_id: str,
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> None:
    if not server.services.repos.user_group_repo.delete(user_group_id):
        raise OctopError(ErrorCode.NOT_FOUND, "user group not found")
    delete_profile_avatar(server.services.paths.group_avatars_dir, user_group_id)


@router.get("/{user_group_id}/members", summary="List members of a user group")
async def list_members(
    user_group_id: str,
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> dict[str, list[int]]:
    _require_group(server, user_group_id)
    return {
        "user_ids": server.services.repos.user_group_member_repo.user_ids_for_group(user_group_id)
    }


@router.put("/{user_group_id}/members", summary="Replace members of a user group")
async def replace_members(
    user_group_id: str,
    body: ReplaceMembersBody,
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> dict[str, list[int]]:
    _require_group(server, user_group_id)
    user_ids: list[int] = []
    seen: set[int] = set()
    for user_id in body.user_ids:
        if user_id in seen:
            continue
        if server.services.user_repo.get(user_id) is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"user {user_id} not found")
        seen.add(user_id)
        user_ids.append(user_id)
    server.services.repos.user_group_member_repo.replace(user_group_id, user_ids)
    return {"user_ids": user_ids}


@router.post("/{user_group_id}/avatar", status_code=201, summary="Upload a user group portrait")
async def upload_group_avatar(
    user_group_id: str,
    file: UploadFile = File(...),  # noqa: B008
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> dict[str, str | None]:
    _require_group(server, user_group_id)
    write_profile_avatar(
        server.services.paths.group_avatars_dir,
        user_group_id,
        await file.read(),
    )
    return {"avatar_url": _avatar_url(server, user_group_id)}


@router.get("/{user_group_id}/avatar", summary="Read a user group portrait")
async def get_group_avatar(
    user_group_id: str,
    server: Any = Depends(get_server),
    _: User = Depends(catalog_reader),
) -> Any:
    _require_group(server, user_group_id)
    return avatar_response(server.services.paths.group_avatars_dir, user_group_id)


@router.delete(
    "/{user_group_id}/avatar",
    status_code=204,
    summary="Remove a user group portrait",
)
async def delete_group_avatar(
    user_group_id: str,
    server: Any = Depends(get_server),
    _: User = Depends(require_permission("users")),
) -> None:
    _require_group(server, user_group_id)
    delete_profile_avatar(server.services.paths.group_avatars_dir, user_group_id)
