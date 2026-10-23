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
CONNECTOR_FEATURE_KEY = "feature"
RESOURCE_MODEL = "model"
RESOURCE_STORAGE_BACKEND = "storage_backend"
STORAGE_FEATURE_KEY = "feature"  # legacy feature-wide key; prefer backend name
RESOURCE_PLUGIN = "plugin"
RESOURCE_BRIDGE = "bridge"
RESOURCE_EXPERT = "expert"

RESOURCE_TYPES = frozenset(
    {
        RESOURCE_SKILL_PACKAGE,
        RESOURCE_KNOWLEDGE_BASE,
        RESOURCE_CONNECTOR,
        RESOURCE_MODEL,
        RESOURCE_STORAGE_BACKEND,
        RESOURCE_PLUGIN,
        RESOURCE_BRIDGE,
        RESOURCE_EXPERT,
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
        " JOIN user_group ug ON ug.user_group_id = g.user_group_id AND ug.enabled = 1"
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
        active = granted & self._enabled_group_ids()
        if not active:
            return False
        return bool(active & self._members.group_ids_for_user(user_id))

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
        enabled = self._enabled_group_ids()
        member_groups = self._members.group_ids_for_user(user_id)
        kept: list[T] = []
        for row in rows:
            if is_owner(row):
                kept.append(row)
                continue
            granted = granted_by_key.get(key_of(row))
            if not granted:
                kept.append(row)
                continue
            active = granted & enabled
            if active and member_groups & active:
                kept.append(row)
        return kept

    def _enabled_group_ids(self) -> set[str]:
        return {row.user_group_id for row in self._groups.list_all() if row.enabled}

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

    def validate_visibility(
        self,
        visibility: str,
        group_ids: Sequence[str] | None,
    ) -> list[str]:
        """Validate visibility args before any ``shared`` write.

        Returns cleaned group ids (empty for ``all`` / ``owner``). Call this
        before persisting ``shared=True`` so a failed ``groups`` choice cannot
        leave a resource open to everyone with no grants.
        """
        if visibility in {VISIBILITY_ALL, VISIBILITY_OWNER}:
            return []
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
        return cleaned

    def set_visibility(
        self,
        resource_type: str,
        resource_key: str,
        visibility: str,
        group_ids: Sequence[str] | None,
    ) -> None:
        if resource_type not in RESOURCE_TYPES:
            raise OctopError(ErrorCode.FORBIDDEN, "unknown resource type", status=400)
        cleaned = self.validate_visibility(visibility, group_ids)
        if visibility in {VISIBILITY_ALL, VISIBILITY_OWNER}:
            self._grants.delete_resource(resource_type, resource_key)
            return
        self._grants.replace(resource_type, resource_key, cleaned)

    def clear(self, resource_type: str, resource_key: str) -> None:
        self._grants.delete_resource(resource_type, resource_key)


def expert_visible_to(
    repos: Any,
    row: Any,
    *,
    user_id: int,
    is_admin: bool,
) -> bool:
    """Owner and admin always pass. Others need ``is_shared`` plus the group layer."""
    if is_admin:
        return True
    owner_id = getattr(row, "user_id", None)
    if owner_id is not None and int(owner_id) == int(user_id):
        return True
    if int(getattr(row, "is_shared", 0) or 0) != 1:
        return False
    return GroupAccess(repos).allows(
        user_id=user_id,
        is_admin=False,
        resource_type=RESOURCE_EXPERT,
        resource_key=str(getattr(row, "agent_id", "")),
        is_owner=False,
    )


def empty_group_access() -> dict[str, Any]:
    return {
        "connectors": [],
        "storage": [],
        "models": [],
        "plugins": [],
        "skill_packages": [],
        "knowledge_bases": [],
        "bridges": [],
        "experts": [],
    }


def _access_item(key: str, label: str, *, audience: str, missing: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "missing": missing, "audience": audience}


def _model_catalog(repos: Any) -> tuple[dict[str, str], set[str]]:
    """Return ``(labels, usable keys)``. Disabled providers and models are not usable."""
    labels: dict[str, str] = {}
    usable: set[str] = set()
    for provider in repos.provider_repo.list_all():
        provider_on = bool(provider.enabled)
        for model in provider.get_models():
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            name = str(model.get("name") or model_id).strip() or model_id
            key = model_resource_key(provider.name, model_id)
            labels[key] = f"{name} · {provider.name}"
            if provider_on and model.get("enabled") is not False:
                usable.add(key)
    return labels, usable


_AUDIENCE_ORDER = {"groups": 0, "all": 1, "creator": 2, "owner": 3}


def _resource_items(
    *,
    catalog: dict[str, str],
    private: dict[str, str],
    private_audience: str,
    known: set[str],
    grants: dict[str, set[str]],
    group_id: str,
) -> list[dict[str, Any]]:
    """Resources this group can see in the access list.

    ``catalog`` is already shared or otherwise open to the group layer.
    ``private`` stays with the creator or owner; groups cannot open those, but
    they are still listed so the category is not blank.
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, label in catalog.items():
        granted = grants.get(key, set())
        if not granted:
            audience = "all"
        elif group_id in granted:
            audience = "groups"
        else:
            continue
        seen.add(key)
        items.append(_access_item(key, label, audience=audience))
    for key, label in private.items():
        if key in seen:
            continue
        seen.add(key)
        items.append(_access_item(key, label, audience=private_audience))
    for key, granted in grants.items():
        if key in seen or key in known or group_id not in granted:
            continue
        items.append(_access_item(key, key, audience="groups", missing=True))
    items.sort(
        key=lambda item: (
            _AUDIENCE_ORDER.get(str(item["audience"]), 9),
            str(item["label"]).lower(),
        )
    )
    return items


def group_access_by_group(repos: Any) -> dict[str, dict[str, Any]]:
    """What each group can use.

    No grant means the resource stays open to everyone, and that is listed too.
    A grant narrows the resource to those groups. Private skill packages and
    unshared knowledge bases are listed as creator-only or owner-only.
    """
    model_labels, usable_models = _model_catalog(repos)
    package_rows = repos.skill_package_repo.list_all()
    base_rows = repos.knowledge_repo.list_all()
    packages = {row.id: row.name for row in package_rows if row.shared}
    private_packages = {row.id: row.name for row in package_rows if not row.shared}
    bases = {row.id: row.name for row in base_rows if row.shared}
    private_bases = {row.id: row.name for row in base_rows if not row.shared}
    grants: dict[tuple[str, str], set[str]] = {}
    for group_id, resource_type, resource_key in repos.resource_group_grant_repo.list_all():
        grants.setdefault((resource_type, resource_key), set()).add(group_id)

    def keys(resource_type: str) -> dict[str, set[str]]:
        return {
            key: group_ids for (kind, key), group_ids in grants.items() if kind == resource_type
        }

    model_grants = keys(RESOURCE_MODEL)
    package_grants = keys(RESOURCE_SKILL_PACKAGE)
    base_grants = keys(RESOURCE_KNOWLEDGE_BASE)
    connector_grants = keys(RESOURCE_CONNECTOR)
    storage_grants = keys(RESOURCE_STORAGE_BACKEND)
    plugin_grants = keys(RESOURCE_PLUGIN)
    bridge_grants = keys(RESOURCE_BRIDGE)
    expert_grants = keys(RESOURCE_EXPERT)
    agent_rows = list(repos.agent_repo.list_all())
    shared_experts = {
        row.agent_id: row.name for row in agent_rows if int(getattr(row, "is_shared", 0) or 0) == 1
    }
    private_experts = {
        row.agent_id: row.name for row in agent_rows if int(getattr(row, "is_shared", 0) or 0) != 1
    }
    bridge_rows = list(repos.bridge_connection_repo.list_all())
    shared_bridges = {row.connection_id: row.display_name for row in bridge_rows if row.shared}
    private_bridges = {row.connection_id: row.display_name for row in bridge_rows if not row.shared}
    connector_rows = [
        row
        for row in repos.connector_repo.list_all()
        if str(getattr(row, "kind", "") or "") != "custom-mcp"
    ]
    shared_connectors = {row.instance_id: row.display_name for row in connector_rows if row.shared}
    private_connectors = {
        row.instance_id: row.display_name for row in connector_rows if not row.shared
    }
    # Ignore the legacy feature-wide key in per-instance summaries.
    connector_grants.pop(CONNECTOR_FEATURE_KEY, None)
    storage_grants.pop(STORAGE_FEATURE_KEY, None)
    storage_rows = list(repos.storage_backend_repo.list_all())
    storage_catalog = {row.name: row.name for row in storage_rows}
    # Plugins live on disk; surface grant keys (labels = plugin id) until loaded.
    plugin_catalog = {key: key for key in plugin_grants}
    out: dict[str, dict[str, Any]] = {}
    for group in repos.user_group_repo.list_all():
        group_id = group.user_group_id
        summary = empty_group_access()
        summary["connectors"] = _resource_items(
            catalog=shared_connectors,
            private=private_connectors,
            private_audience="owner",
            known={row.instance_id for row in connector_rows},
            grants=connector_grants,
            group_id=group_id,
        )
        summary["storage"] = _resource_items(
            catalog=storage_catalog,
            private={},
            private_audience="owner",
            known=set(storage_catalog),
            grants=storage_grants,
            group_id=group_id,
        )
        summary["models"] = _resource_items(
            catalog={key: model_labels[key] for key in usable_models},
            private={},
            private_audience="owner",
            known=set(model_labels),
            grants=model_grants,
            group_id=group_id,
        )
        summary["plugins"] = _resource_items(
            catalog=plugin_catalog,
            private={},
            private_audience="owner",
            known=set(plugin_catalog),
            grants=plugin_grants,
            group_id=group_id,
        )
        summary["skill_packages"] = _resource_items(
            catalog=packages,
            private=private_packages,
            private_audience="creator",
            known={row.id for row in package_rows},
            grants=package_grants,
            group_id=group_id,
        )
        summary["knowledge_bases"] = _resource_items(
            catalog=bases,
            private=private_bases,
            private_audience="owner",
            known={row.id for row in base_rows},
            grants=base_grants,
            group_id=group_id,
        )
        summary["bridges"] = _resource_items(
            catalog=shared_bridges,
            private=private_bridges,
            private_audience="owner",
            known={row.connection_id for row in bridge_rows},
            grants=bridge_grants,
            group_id=group_id,
        )
        summary["experts"] = _resource_items(
            catalog=shared_experts,
            private=private_experts,
            private_audience="owner",
            known={row.agent_id for row in agent_rows},
            grants=expert_grants,
            group_id=group_id,
        )
        out[group_id] = summary
    return out
