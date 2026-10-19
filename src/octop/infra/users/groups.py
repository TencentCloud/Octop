"""User-group visibility layered on top of the existing per-user rules.

A resource with no grant rows keeps today's audience. Grant rows narrow that
audience to members of those groups. Owners, creators, and admins are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from octop.infra.errors import ErrorCode, OctopError

RESOURCE_SKILL_PACKAGE = "skill_package"
RESOURCE_KNOWLEDGE_BASE = "knowledge_base"
RESOURCE_CONNECTOR = "connector"
RESOURCE_MODEL = "model"
RESOURCE_STORAGE_BACKEND = "storage_backend"

RESOURCE_TYPES = frozenset(
    {
        RESOURCE_SKILL_PACKAGE,
        RESOURCE_KNOWLEDGE_BASE,
        RESOURCE_CONNECTOR,
        RESOURCE_MODEL,
        RESOURCE_STORAGE_BACKEND,
    }
)

VISIBILITY_ALL = "all"
VISIBILITY_GROUPS = "groups"
VISIBILITY_OWNER = "owner"

T = TypeVar("T")


def model_resource_key(provider_name: str, model_id: str) -> str:
    return f"{provider_name}/{model_id}"


def model_ref_allowed(
    repos: Any,
    *,
    user_id: int,
    is_admin: bool,
    model_ref: str | None,
) -> bool:
    """Whether *model_ref* (``provider/model``) passes the group layer.

    Blank refs, ``auto``, and refs without a provider prefix are not model grants.
    """
    ref = (model_ref or "").strip()
    if not ref or ref.lower() == "auto" or "/" not in ref:
        return True
    return GroupAccess(repos).allows(
        user_id=user_id,
        is_admin=is_admin,
        resource_type=RESOURCE_MODEL,
        resource_key=ref,
        is_owner=False,
    )


def group_visibility_sql(resource_type: str, key_expr: str) -> str:
    """SQL fragment: no grants, or the bound user belongs to a granted group.

    ``resource_type`` and ``key_expr`` are fixed by the caller, not request data.
    The user id placeholder is ``?``.
    """
    if resource_type not in RESOURCE_TYPES:
        raise ValueError(f"unknown resource type {resource_type!r}")
    return (
        "NOT EXISTS ("
        " SELECT 1 FROM resource_group_grant g"
        f" WHERE g.resource_type = '{resource_type}' AND g.resource_key = {key_expr}"
        ") OR EXISTS ("
        " SELECT 1 FROM resource_group_grant g"
        " JOIN user_group_member m ON m.user_group_id = g.user_group_id"
        f" WHERE g.resource_type = '{resource_type}' AND g.resource_key = {key_expr}"
        " AND m.user_id = ?"
        ")"
    )


class GroupAccess:
    """Read and write the group layer. Callers still apply ownership themselves."""

    def __init__(self, repos: Any) -> None:
        self._groups = repos.user_group_repo
        self._members = repos.user_group_member_repo
        self._grants = repos.resource_group_grant_repo

    def allows(
        self,
        *,
        user_id: int,
        is_admin: bool,
        resource_type: str,
        resource_key: str,
        is_owner: bool,
    ) -> bool:
        if is_admin or is_owner:
            return True
        granted = self._grants.group_ids(resource_type, resource_key)
        if not granted:
            return True
        return bool(granted & self._members.group_ids_for_user(user_id))

    def assert_allowed(
        self,
        *,
        user_id: int,
        is_admin: bool,
        resource_type: str,
        resource_key: str,
        is_owner: bool,
    ) -> None:
        if self.allows(
            user_id=user_id,
            is_admin=is_admin,
            resource_type=resource_type,
            resource_key=resource_key,
            is_owner=is_owner,
        ):
            return
        raise OctopError(ErrorCode.RESOURCE_NOT_ALLOWED, "resource is not visible to this user")

    def filter_rows(
        self,
        rows: Sequence[T],
        *,
        user_id: int,
        is_admin: bool,
        resource_type: str,
        key_of: Callable[[T], str],
        is_owner: Callable[[T], bool],
    ) -> list[T]:
        if is_admin:
            return list(rows)
        granted_by_key = self._grants.group_ids_by_resource(resource_type)
        if not granted_by_key:
            return list(rows)
        member_groups = self._members.group_ids_for_user(user_id)
        kept: list[T] = []
        for row in rows:
            if is_owner(row):
                kept.append(row)
                continue
            granted = granted_by_key.get(key_of(row))
            if not granted or member_groups & granted:
                kept.append(row)
        return kept

    def visibility(
        self, resource_type: str, resource_key: str, *, shared: bool | None
    ) -> dict[str, Any]:
        """Public visibility for one resource.

        ``shared is False`` is the existing private state of a knowledge base or
        connector. Other resources pass ``shared=None`` and are ``all`` or ``groups``.
        """
        if shared is False:
            return {"visibility": VISIBILITY_OWNER, "group_ids": []}
        group_ids = sorted(self._grants.group_ids(resource_type, resource_key))
        if not group_ids:
            return {"visibility": VISIBILITY_ALL, "group_ids": []}
        return {"visibility": VISIBILITY_GROUPS, "group_ids": group_ids}

    def set_visibility(
        self,
        resource_type: str,
        resource_key: str,
        visibility: str,
        group_ids: Sequence[str] | None,
    ) -> None:
        if resource_type not in RESOURCE_TYPES:
            raise OctopError(ErrorCode.FORBIDDEN, "unknown resource type", status=400)
        if visibility in {VISIBILITY_ALL, VISIBILITY_OWNER}:
            self._grants.delete_resource(resource_type, resource_key)
            return
        if visibility != VISIBILITY_GROUPS:
            raise OctopError(ErrorCode.FORBIDDEN, "unknown visibility", status=400)
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in group_ids or []:
            group_id = str(raw).strip()
            if not group_id or group_id in seen:
                continue
            seen.add(group_id)
            cleaned.append(group_id)
        if not cleaned:
            raise OctopError(
                ErrorCode.FORBIDDEN,
                "choose at least one user group",
                status=400,
            )
        missing = [group_id for group_id in cleaned if self._groups.get(group_id) is None]
        if missing:
            raise OctopError(ErrorCode.NOT_FOUND, "user group not found")
        self._grants.replace(resource_type, resource_key, cleaned)

    def clear(self, resource_type: str, resource_key: str) -> None:
        self._grants.delete_resource(resource_type, resource_key)
