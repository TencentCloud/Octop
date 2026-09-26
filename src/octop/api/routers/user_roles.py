"""Admin CRUD for role templates.

A role stores permission keys and a resource-policy array. Missing policy
names are not enabled. Applying a role copies those defaults onto a user.
Invites store only the role name and read the role when the account is created.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.api.routers.users import _assert_can_assign
from octop.infra.db.repos.user_roles import ADMIN_USER_ROLE_ID, UserRoleRepo, UserRoleRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.users.permissions import ALL_PERMISSION_KEYS, validate_permission_keys
from octop.infra.users.resource_policy import (
    POLICY_MAX_AGENTS,
    POLICY_TOKEN_QUOTA,
    POLICY_WORKSPACE_ROOT_DIR,
    max_agents_of,
    normalize_max_agents,
    normalize_token_quota,
    normalize_workspace_root_dir,
    token_quota_of,
    workspace_root_dir_of,
)

router = APIRouter()

_KNOWN_POLICIES = {
    POLICY_WORKSPACE_ROOT_DIR,
    POLICY_TOKEN_QUOTA,
    POLICY_MAX_AGENTS,
}


class PolicyItem(BaseModel):
    name: str
    value: str


class UserRoleBody(BaseModel):
    user_role_name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)
    policies: list[PolicyItem] = Field(default_factory=list)


class UserRolePatchBody(BaseModel):
    user_role_name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] | None = None
    policies: list[PolicyItem] | None = None
    avatar_icon: str | None = Field(default=None, max_length=32)


def _repo(server: Any) -> UserRoleRepo:
    return UserRoleRepo(server.services.db)


def _public(server: Any, row: UserRoleRow) -> dict[str, Any]:
    from octop.infra.users.profile_avatar import profile_avatar_url

    return public_role(
        row,
        avatar_url=profile_avatar_url(
            server.services.paths.role_avatars_dir,
            row.user_role_id,
            f"/api/users/roles/{row.user_role_id}/avatar",
        ),
    )


def _clean_name(raw: str) -> str:
    name = raw.strip()
    if not name or len(name) > 64:
        raise OctopError(ErrorCode.FORBIDDEN, "role name must be 1-64 characters", status=400)
    return name


def _clean_description(raw: str | None) -> str | None:
    if raw is None:
        return None
    return raw.strip() or None


def _policies_from_fields(
    *,
    workspace_root_dir: str | None,
    token_quota: int | None,
    max_agents: int | None,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    root = normalize_workspace_root_dir(workspace_root_dir)
    if root:
        items.append((POLICY_WORKSPACE_ROOT_DIR, root))
    quota = normalize_token_quota(token_quota)
    if quota is not None:
        items.append((POLICY_TOKEN_QUOTA, str(quota)))
    agents = normalize_max_agents(max_agents)
    if agents is not None:
        items.append((POLICY_MAX_AGENTS, str(agents)))
    return items


def _policies_from_items(items: list[PolicyItem]) -> list[tuple[str, str]]:
    unknown = sorted({item.name for item in items if item.name not in _KNOWN_POLICIES})
    if unknown:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            f"unknown policy names: {unknown}",
            status=400,
        )
    by_name = {item.name: item.value for item in items}
    return _policies_from_fields(
        workspace_root_dir=by_name.get(POLICY_WORKSPACE_ROOT_DIR),
        token_quota=token_quota_of(by_name.get(POLICY_TOKEN_QUOTA)),
        max_agents=max_agents_of(by_name.get(POLICY_MAX_AGENTS)),
    )


def _policies_for_write(body: UserRoleBody | UserRolePatchBody) -> list[tuple[str, str]] | None:
    """Persist policies only from the ``policies`` array.

    Omitted names stay disabled. A patch that leaves ``policies`` out keeps
    the stored array, so a name-only or permission-only update cannot clear
    the other policies.
    """
    if body.policies is None:
        return None
    return _policies_from_items(body.policies)


def public_role(row: UserRoleRow, *, avatar_url: str | None = None) -> dict[str, Any]:
    if row.is_admin:
        permissions = sorted(ALL_PERMISSION_KEYS)
        system_role = "admin"
        policies: list[dict[str, str]] = []
        workspace_root_dir = None
        token_quota = None
        max_agents = None
    else:
        permissions = list(row.permissions)
        system_role = "user"
        policies = [{"name": name, "value": value} for name, value in row.policies]
        workspace_root_dir = workspace_root_dir_of(row.policy_value(POLICY_WORKSPACE_ROOT_DIR))
        token_quota = token_quota_of(row.policy_value(POLICY_TOKEN_QUOTA))
        max_agents = max_agents_of(row.policy_value(POLICY_MAX_AGENTS))
    return {
        "user_role_id": row.user_role_id,
        "user_role_name": row.user_role_name,
        "description": row.description,
        "system_role": system_role,
        "permissions": permissions,
        "policies": policies,
        "deletable": row.user_role_id != ADMIN_USER_ROLE_ID,
        "immutable": row.is_admin,
        "workspace_root_dir": workspace_root_dir,
        "token_quota": token_quota,
        "max_agents": max_agents,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "avatar_icon": row.avatar_icon,
        "avatar_url": avatar_url,
    }


def _name_taken(exc: ValueError) -> None:
    if str(exc) != "name_taken":
        raise exc
    raise OctopError(ErrorCode.FORBIDDEN, "role name already exists", status=409) from exc


@router.get("", summary="List role templates")
async def list_user_roles(
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_public(server, row) for row in _repo(server).list_all()]


@router.post("", status_code=201, summary="Create a role template")
async def create_user_role(
    body: UserRoleBody,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    try:
        permissions = validate_permission_keys(body.permissions)
    except ValueError as exc:
        raise OctopError(ErrorCode.FORBIDDEN, str(exc), status=400) from exc
    _assert_can_assign(actor, permissions)
    policies = _policies_for_write(body) or []
    try:
        row = _repo(server).create(
            user_role_name=_clean_name(body.user_role_name),
            description=_clean_description(body.description),
            permissions=permissions,
            policies=policies,
        )
    except ValueError as exc:
        _name_taken(exc)
        raise
    server.services.audit_repo.write(
        actor=actor.username,
        action="user_role.create",
        target=row.user_role_name,
    )
    return _public(server, row)


@router.patch("/{user_role_id}", summary="Update a role template")
async def patch_user_role(
    user_role_id: str,
    body: UserRolePatchBody,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    current = _repo(server).get(user_role_id)
    if current is None:
        raise OctopError(ErrorCode.NOT_FOUND, "role not found")
    name = _clean_name(body.user_role_name) if body.user_role_name is not None else None
    description: str | None | object = ...
    if "description" in body.model_fields_set:
        description = _clean_description(body.description)
    avatar_icon: str | None | object = ...
    if "avatar_icon" in body.model_fields_set:
        from octop.infra.users.profile_avatar import clean_avatar_icon, delete_profile_avatar

        avatar_icon = clean_avatar_icon(body.avatar_icon)
        delete_profile_avatar(server.services.paths.role_avatars_dir, user_role_id)
    if current.is_admin:
        if name is None and description is ... and avatar_icon is ...:
            return _public(server, current)
        try:
            updated = _repo(server).update(
                user_role_id,
                user_role_name=name,
                description=description,
                avatar_icon=avatar_icon,
            )
        except ValueError as exc:
            _name_taken(exc)
            raise
        assert updated is not None
        server.services.audit_repo.write(
            actor=actor.username,
            action="user_role.update",
            target=updated.user_role_name,
        )
        return _public(server, updated)

    permissions: list[str] | None = None
    if body.permissions is not None:
        try:
            permissions = validate_permission_keys(body.permissions)
        except ValueError as exc:
            raise OctopError(ErrorCode.FORBIDDEN, str(exc), status=400) from exc
        _assert_can_assign(actor, permissions)
    try:
        updated = _repo(server).update(
            user_role_id,
            user_role_name=name,
            description=description,
            permissions=permissions,
            policies=_policies_for_write(body),
            avatar_icon=avatar_icon,
        )
    except ValueError as exc:
        _name_taken(exc)
        raise
    assert updated is not None
    server.services.audit_repo.write(
        actor=actor.username,
        action="user_role.update",
        target=updated.user_role_name,
    )
    return _public(server, updated)


@router.delete("/{user_role_id}", status_code=204, summary="Delete a role template")
async def delete_user_role(
    user_role_id: str,
    actor: User = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> None:
    current = _repo(server).get(user_role_id)
    if current is None:
        raise OctopError(ErrorCode.NOT_FOUND, "role not found")
    if current.user_role_id == ADMIN_USER_ROLE_ID:
        raise OctopError(ErrorCode.FORBIDDEN, "built-in administrator role cannot be deleted")
    _repo(server).delete(user_role_id)
    from octop.infra.users.profile_avatar import delete_profile_avatar

    delete_profile_avatar(server.services.paths.role_avatars_dir, user_role_id)
    server.services.audit_repo.write(
        actor=actor.username,
        action="user_role.delete",
        target=current.user_role_name,
    )


@router.post("/{user_role_id}/avatar", status_code=201)
async def upload_role_avatar(
    user_role_id: str,
    file: UploadFile = File(...),  # noqa: B008
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, str | None]:
    row = _repo(server).get(user_role_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "role not found")
    from octop.infra.users.profile_avatar import write_profile_avatar

    write_profile_avatar(
        server.services.paths.role_avatars_dir,
        user_role_id,
        await file.read(),
    )
    return {"avatar_url": _public(server, row)["avatar_url"]}


@router.get("/{user_role_id}/avatar")
async def get_role_avatar(
    user_role_id: str,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> Any:
    from octop.infra.users.profile_avatar import avatar_response

    if _repo(server).get(user_role_id) is None:
        raise OctopError(ErrorCode.NOT_FOUND, "role not found")
    return avatar_response(server.services.paths.role_avatars_dir, user_role_id)


@router.delete("/{user_role_id}/avatar", status_code=204)
async def delete_role_avatar(
    user_role_id: str,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> None:
    if _repo(server).get(user_role_id) is None:
        raise OctopError(ErrorCode.NOT_FOUND, "role not found")
    from octop.infra.users.profile_avatar import delete_profile_avatar

    delete_profile_avatar(server.services.paths.role_avatars_dir, user_role_id)
