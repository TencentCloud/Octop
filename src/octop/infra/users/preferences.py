"""Per-user JSON preferences (models, remote-browser bookmarks, etc.)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.url import normalize_nav_url

MAX_REMOTE_BROWSER_BOOKMARKS = 12
PREFERENCES_KEY_REMOTE_BROWSER_BOOKMARKS = "remote_browser_bookmarks"
PREFERENCES_KEY_PREFERRED_MODEL = "preferred_model"
PREFERENCES_KEY_MODEL_REASONING = "model_reasoning"
PREFERENCES_KEY_AVATAR = "avatar"
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


def normalize_avatar_reference(value: Any) -> str | None:
    """Avatar references look like ``users/<id>`` or ``agents/<agent_id>``."""
    if not isinstance(value, str):
        return None
    ref = value.strip()
    if not ref or "/" not in ref:
        return None
    kind, _, key = ref.partition("/")
    if kind not in {"users", "agents"} or not key or len(ref) > 180:
        return None
    return ref


def get_avatar_reference_from_json(raw: str | None) -> str | None:
    return normalize_avatar_reference(parse_preferences_json(raw).get(PREFERENCES_KEY_AVATAR))


def merge_avatar_preferences_json(
    current_raw: str | None,
    *,
    avatar: str | None,
) -> str:
    data = parse_preferences_json(current_raw)
    if avatar is None:
        data.pop(PREFERENCES_KEY_AVATAR, None)
    else:
        ref = normalize_avatar_reference(avatar)
        if ref is None:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid avatar reference")
        data[PREFERENCES_KEY_AVATAR] = ref
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
