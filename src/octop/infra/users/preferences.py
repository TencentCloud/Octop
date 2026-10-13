"""Per-user JSON preferences (models, remote-browser bookmarks, etc.)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.url import normalize_nav_url

MAX_REMOTE_BROWSER_BOOKMARKS = 12
PREFERENCES_KEY_REMOTE_BROWSER_BOOKMARKS = "remote_browser_bookmarks"
PREFERENCES_KEY_PREFERRED_MODEL = "preferred_model"
PREFERENCES_KEY_MODEL_REASONING = "model_reasoning"
PREFERENCES_KEY_TIMEZONE = "timezone"
PREFERENCES_KEY_SIDEBAR_NAV = "sidebar_nav"

# Keep in sync with dashboard/src/layouts/sidebarNav.tsx SIDEBAR_NAV_KEYS.
SIDEBAR_NAV_KEYS = frozenset(
    {
        "chat",
        "experts",
        "tasks",
        "token-usage",
        "personalization",
        "channels",
        "connectors",
        "skill-packages",
        "knowledge-bases",
        "bridge",
        "workbench",
        "remote-desktop",
        "acp",
        "admin-users",
        "models",
        "admin-storage",
        "admin-plugins",
        "admin-security",
        "admin-advanced",
    }
)
_BUILTIN_SIDEBAR_GROUP_IDS = frozenset({"settings", "control", "admin"})
_CUSTOM_SIDEBAR_GROUP_ID = re.compile(r"^c_[a-z0-9]{8,32}$")
_MAX_SIDEBAR_GROUPS = 24
_MAX_SIDEBAR_GROUP_NAME = 40
MAX_BOOKMARK_TITLE_LEN = 80

REASONING_MODES = frozenset({"auto", "enabled", "disabled"})


@dataclass(frozen=True)
class ModelReasoningPreference:
    mode: str = "auto"
    effort: str | None = None


@dataclass(frozen=True)
class RemoteBrowserBookmark:
    url: str
    title: str


@dataclass(frozen=True)
class SidebarNavGroup:
    id: str
    name: str | None = None


@dataclass(frozen=True)
class SidebarNavItem:
    key: str
    group: str | None = None
    hidden: bool = False


def parse_preferences_json(raw: str | None) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def validate_remote_browser_bookmarks(items: list[Any]) -> list[RemoteBrowserBookmark]:
    out: list[RemoteBrowserBookmark] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = normalize_nav_url(str(item.get("url") or ""))
        if not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        title_raw = str(item.get("title") or "").strip()
        if not title_raw:
            title_raw = urlparse(url).hostname or url
        out.append(RemoteBrowserBookmark(url=url, title=title_raw[:MAX_BOOKMARK_TITLE_LEN]))
    if len(out) > MAX_REMOTE_BROWSER_BOOKMARKS:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"remote_browser_bookmarks limit is {MAX_REMOTE_BROWSER_BOOKMARKS}",
        )
    return out


def get_remote_browser_bookmarks_from_json(raw: str | None) -> list[RemoteBrowserBookmark]:
    data = parse_preferences_json(raw)
    items = data.get(PREFERENCES_KEY_REMOTE_BROWSER_BOOKMARKS, [])
    if not isinstance(items, list):
        return []
    return validate_remote_browser_bookmarks(items)


def normalize_model_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    ref = value.strip()
    if not ref or ref.lower() == "auto" or "/" not in ref:
        return None
    provider, _, model = ref.partition("/")
    return ref if provider and model else None


def get_preferred_model_from_json(raw: str | None) -> str | None:
    return normalize_model_ref(parse_preferences_json(raw).get(PREFERENCES_KEY_PREFERRED_MODEL))


def normalize_reasoning_preference(value: Any) -> ModelReasoningPreference:
    if not isinstance(value, dict):
        return ModelReasoningPreference()
    raw_mode = value.get("mode")
    mode = str(raw_mode).strip().lower() if raw_mode is not None else "auto"
    if mode not in REASONING_MODES:
        mode = "auto"
    raw_effort = value.get("effort")
    effort = str(raw_effort).strip().lower() if isinstance(raw_effort, str) else None
    return ModelReasoningPreference(mode=mode, effort=effort or None)


def get_model_reasoning_from_json(raw: str | None) -> dict[str, ModelReasoningPreference]:
    data = parse_preferences_json(raw).get(PREFERENCES_KEY_MODEL_REASONING)
    if not isinstance(data, dict):
        return {}
    out: dict[str, ModelReasoningPreference] = {}
    for raw_ref, value in data.items():
        ref = normalize_model_ref(raw_ref)
        if ref:
            out[ref] = normalize_reasoning_preference(value)
    return out


def get_timezone_from_preferences_json(raw: str | None) -> str | None:
    """Return the preferred timezone from preferences JSON if present and non-empty."""
    value = parse_preferences_json(raw).get(PREFERENCES_KEY_TIMEZONE)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def merge_preferences_json(
    current_raw: str | None,
    bookmarks: list[RemoteBrowserBookmark],
) -> str:
    data = parse_preferences_json(current_raw)
    data[PREFERENCES_KEY_REMOTE_BROWSER_BOOKMARKS] = [
        {"url": b.url, "title": b.title} for b in bookmarks
    ]
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def merge_model_preferences_json(
    current_raw: str | None,
    *,
    preferred_model: str | None | object = ...,
    model_reasoning: dict[str, ModelReasoningPreference] | None = None,
) -> str:
    data = parse_preferences_json(current_raw)
    if preferred_model is not ...:
        if preferred_model is None:
            data.pop(PREFERENCES_KEY_PREFERRED_MODEL, None)
        else:
            ref = normalize_model_ref(preferred_model)
            if ref is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid preferred_model")
            data[PREFERENCES_KEY_PREFERRED_MODEL] = ref
    if model_reasoning is not None:
        data[PREFERENCES_KEY_MODEL_REASONING] = {
            ref: {"mode": pref.mode, "effort": pref.effort} for ref, pref in model_reasoning.items()
        }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _sidebar_group_name(value: Any, *, builtin: bool) -> str | None:
    if value is None:
        if builtin:
            return None
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "sidebar nav group name is required")
    if not isinstance(value, str):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav group name")
    name = value.strip()
    if not name:
        if builtin:
            return None
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "sidebar nav group name is required")
    if len(name) > _MAX_SIDEBAR_GROUP_NAME or any(ch in name for ch in "\n\r\t"):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav group name")
    return name


def validate_sidebar_nav(value: Any) -> tuple[list[SidebarNavGroup], list[SidebarNavItem]]:
    """Normalize a sidebar layout. Unknown keys and dangling groups are rejected."""
    if not isinstance(value, dict):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav layout")
    raw_groups = value.get("groups", [])
    raw_items = value.get("items", [])
    if not isinstance(raw_groups, list) or not isinstance(raw_items, list):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav layout")
    if len(raw_groups) > _MAX_SIDEBAR_GROUPS:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"sidebar nav groups limit is {_MAX_SIDEBAR_GROUPS}",
        )
    groups: list[SidebarNavGroup] = []
    seen_groups: set[str] = set()
    for raw in raw_groups:
        if not isinstance(raw, dict):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav group")
        group_id = str(raw.get("id") or "").strip()
        builtin = group_id in _BUILTIN_SIDEBAR_GROUP_IDS
        if not builtin and _CUSTOM_SIDEBAR_GROUP_ID.fullmatch(group_id) is None:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav group id")
        if group_id in seen_groups:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "duplicate sidebar nav group")
        seen_groups.add(group_id)
        groups.append(
            SidebarNavGroup(
                id=group_id,
                name=_sidebar_group_name(raw.get("name"), builtin=builtin),
            )
        )
    items: list[SidebarNavItem] = []
    seen_keys: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid sidebar nav item")
        key = str(raw.get("key") or "").strip()
        if key not in SIDEBAR_NAV_KEYS:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "unknown sidebar nav item")
        if key in seen_keys:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "duplicate sidebar nav item")
        seen_keys.add(key)
        hidden = bool(raw.get("hidden"))
        raw_group = raw.get("group")
        item_group: str | None = (
            str(raw_group).strip() if isinstance(raw_group, str) and raw_group.strip() else None
        )
        if hidden:
            item_group = None
        elif item_group is not None and item_group not in seen_groups:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "sidebar nav item group does not exist")
        items.append(SidebarNavItem(key=key, group=item_group, hidden=hidden))
    return groups, items


def sidebar_nav_to_dict(
    groups: list[SidebarNavGroup],
    items: list[SidebarNavItem],
) -> dict[str, Any]:
    payload_items: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {"key": item.key}
        if item.group:
            row["group"] = item.group
        if item.hidden:
            row["hidden"] = True
        payload_items.append(row)
    payload_groups: list[dict[str, Any]] = []
    for group in groups:
        row = {"id": group.id}
        if group.name:
            row["name"] = group.name
        payload_groups.append(row)
    return {"groups": payload_groups, "items": payload_items}


def get_sidebar_nav_from_json(raw: str | None) -> dict[str, Any] | None:
    value = parse_preferences_json(raw).get(PREFERENCES_KEY_SIDEBAR_NAV)
    if value is None:
        return None
    try:
        groups, items = validate_sidebar_nav(value)
    except OctopError:
        return None
    return sidebar_nav_to_dict(groups, items)


def merge_sidebar_nav_json(current_raw: str | None, layout: Any | None) -> str:
    data = parse_preferences_json(current_raw)
    if layout is None:
        data.pop(PREFERENCES_KEY_SIDEBAR_NAV, None)
    else:
        groups, items = validate_sidebar_nav(layout)
        data[PREFERENCES_KEY_SIDEBAR_NAV] = sidebar_nav_to_dict(groups, items)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
