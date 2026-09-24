"""Admin CRUD for users."""

from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User
from octop.infra.users.permissions import PERMISSIONS
from octop.infra.users.resource_policy import (
    normalize_max_agents,
    normalize_token_quota,
    normalize_workspace_root_dir,
    public_policy_fields,
)
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()

UserBatchAction = Literal["enable", "disable", "delete", "set_token_quota", "set_max_agents"]


class UserCreateBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    role: str = "user"
    display_name: str | None = None
    email: str | None = Field(default=None, max_length=254)
    permissions: list[str] = Field(default_factory=list)
    workspace_root_dir: str | None = None
    token_quota: int | None = Field(default=None, ge=0)
    max_agents: int | None = Field(default=None, ge=0)


class UserPatchBody(BaseModel):
    role: str | None = None
    display_name: str | None = None
    email: str | None = Field(default=None, max_length=254)
    disabled: bool | None = None
    permissions: list[str] | None = None
    workspace_root_dir: str | None = None
    token_quota: int | None = Field(default=None, ge=0)
    max_agents: int | None = Field(default=None, ge=0)


class ResetPasswordBody(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)


class UserBatchBody(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=500)
    action: UserBatchAction
    token_quota: int | None = Field(
        default=None,
        ge=0,
        description="Used by set_token_quota. null clears the limit (unlimited).",
    )
    max_agents: int | None = Field(
        default=None,
        ge=0,
        description="Used by set_max_agents. null clears the limit (unlimited).",
    )


class UserBatchItemResult(BaseModel):
    user_id: int
    ok: bool
    error: str | None = None
    code: str | None = None


class UserBatchResponse(BaseModel):
    action: UserBatchAction
    results: list[UserBatchItemResult]
    succeeded: int
    failed: int


def _row_to_dict(r: Any, policy: Any | None = None) -> dict[str, Any]:
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
        **public_policy_fields(policy),
    }


def _policy_kwargs_from_body(body: UserCreateBody | UserPatchBody) -> dict[str, Any]:
    policy_kwargs: dict[str, Any] = {}
    if "workspace_root_dir" in body.model_fields_set:
        policy_kwargs["workspace_root_dir"] = body.workspace_root_dir
    if "token_quota" in body.model_fields_set:
        policy_kwargs["token_quota"] = body.token_quota
    if "max_agents" in body.model_fields_set:
        policy_kwargs["max_agents"] = body.max_agents
    return policy_kwargs


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
    policy_map = server.services.user_policy_repo.list_by_user_ids([r.id for r in rows])
    return [_row_to_dict(r, policy_map.get(r.id)) for r in rows]


@router.post("", status_code=201)
async def create_user(
    body: UserCreateBody,
    actor: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _assert_can_assign(actor, body.permissions)
    policy_kwargs = _policy_kwargs_from_body(body)
    if "workspace_root_dir" in policy_kwargs:
        normalize_workspace_root_dir(policy_kwargs["workspace_root_dir"])
    if "token_quota" in policy_kwargs:
        normalize_token_quota(policy_kwargs["token_quota"])
    if "max_agents" in policy_kwargs:
        normalize_max_agents(policy_kwargs["max_agents"])
    role = Role(body.role)
    user = await server.user_manager.create(
        username=body.username,
        password=body.password,
        role=role,
        display_name=body.display_name,
        email=body.email,
        permissions=body.permissions,
    )
    if policy_kwargs:
        await server.user_manager.set_resource_policy(user.username, **policy_kwargs)
    row = server.user_manager.get_row(user.id)
    assert row is not None
    return _row_to_dict(row, server.services.user_policy_repo.list_for_user(row.id))


def _batch_fail(user_id: int, *, code: str, error: str) -> UserBatchItemResult:
    return UserBatchItemResult(user_id=user_id, ok=False, code=code, error=error)


async def _batch_apply_one(
    *,
    server: Any,
    actor: User,
    user_id: int,
    action: UserBatchAction,
    token_quota: int | None,
    max_agents: int | None,
) -> UserBatchItemResult:
    if action in ("disable", "delete") and user_id == actor.id:
        return _batch_fail(
            user_id,
            code=ErrorCode.FORBIDDEN.value,
            error="cannot apply this action to yourself",
        )
    row = server.user_manager.get_row(user_id)
    if row is None:
        return _batch_fail(
            user_id,
            code=ErrorCode.NOT_FOUND.value,
            error="user not found",
        )
    try:
        if action == "enable":
            await server.user_manager.enable(row.username)
        elif action == "disable":
            await server.user_manager.disable(row.username)
        elif action == "delete":
            await server.user_manager.remove(row.username)
        elif action == "set_token_quota":
            await server.user_manager.set_resource_policy(
                row.username,
                token_quota=token_quota,
            )
        elif action == "set_max_agents":
            await server.user_manager.set_resource_policy(
                row.username,
                max_agents=max_agents,
            )
        else:
            return _batch_fail(
                user_id,
                code=ErrorCode.SLASH_BAD_ARGS.value,
                error=f"unknown action: {action}",
            )
    except OctopError as exc:
        return _batch_fail(
            user_id,
            code=exc.code.value,
            error=exc.message,
        )
    return UserBatchItemResult(user_id=user_id, ok=True)


@router.post(
    "/batch",
    summary="Batch enable, disable, delete, or set resource policies",
    description=(
        "Apply one action to many users. Per-user failures do not abort the batch. "
        "Disable and delete skip the current actor. For set_token_quota / set_max_agents, "
        "a null value clears the limit."
    ),
    response_model=UserBatchResponse,
)
async def batch_users(
    body: UserBatchBody,
    actor: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> UserBatchResponse:
    if body.action == "set_token_quota":
        normalize_token_quota(body.token_quota)
    if body.action == "set_max_agents":
        normalize_max_agents(body.max_agents)

    # Preserve order while dropping duplicates.
    seen: set[int] = set()
    user_ids: list[int] = []
    for uid in body.user_ids:
        if uid in seen:
            continue
        seen.add(uid)
        user_ids.append(uid)

    results: list[UserBatchItemResult] = []
    for user_id in user_ids:
        results.append(
            await _batch_apply_one(
                server=server,
                actor=actor,
                user_id=user_id,
                action=body.action,
                token_quota=body.token_quota,
                max_agents=body.max_agents,
            )
        )
    succeeded = sum(1 for item in results if item.ok)
    return UserBatchResponse(
        action=body.action,
        results=results,
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    _: Any = Depends(require_permission("users")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = server.user_manager.get_row(user_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    return _row_to_dict(row, server.services.user_policy_repo.list_for_user(row.id))


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
    policy_kwargs = _policy_kwargs_from_body(body)
    if policy_kwargs:
        await server.user_manager.set_resource_policy(row.username, **policy_kwargs)
    updated = server.user_manager.get_row(user_id)
    assert updated is not None
    return _row_to_dict(
        updated,
        server.services.user_policy_repo.list_for_user(updated.id),
    )


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
