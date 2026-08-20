"""Agent profile fields stored on ``agents`` rather than in ``config_json``.

``config_json`` keeps harness-agent interaction keys (backend, plugins, memory,
skills, heartbeat, runtime knobs). Display / catalog metadata lives on columns.
"""

from __future__ import annotations

import json
from typing import Any

PROFILE_CONFIG_KEYS = frozenset(
    {
        "expert_id",
        "icon_name",
        "icon_url",
        "color",
        "skill_package_ids",
        "published_expert_id",
        "welcome_message",
    }
)


def parse_config_json(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def strip_profile_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return harness-only config, dropping Octop profile keys."""
    return {key: value for key, value in cfg.items() if key not in PROFILE_CONFIG_KEYS}


def dumps_config(cfg: dict[str, Any]) -> str:
    return json.dumps(strip_profile_config(cfg), ensure_ascii=False)


def parse_skill_package_ids_json(raw: str | None) -> list[str] | None:
    """Parse the ``skill_package_ids`` column. ``None`` means the column is unset."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, list):
        return None
    return [str(item) for item in parsed if str(item).strip()]


def dump_skill_package_ids(ids: list[str]) -> str:
    return json.dumps(list(ids), ensure_ascii=False)


def _nonempty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _localized_text(value: Any) -> str | None:
    """Pick a single string from a legacy bilingual dict or a plain string."""
    if isinstance(value, dict):
        zh = str(value.get("zh") or "").strip()
        en = str(value.get("en") or "").strip()
        text = zh or en
        return text or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def extract_profile_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Lift legacy profile keys out of a config dict into column-oriented updates."""
    out: dict[str, Any] = {}
    icon_name = _nonempty_str(cfg.get("icon_name"))
    if icon_name is not None:
        out["icon_name"] = icon_name
    icon_url = _nonempty_str(cfg.get("icon_url"))
    if icon_url is not None:
        out["icon_url"] = icon_url
    color = _nonempty_str(cfg.get("color"))
    if color is not None:
        out["color"] = color
    published = _nonempty_str(cfg.get("published_expert_id"))
    if published is not None:
        out["published_expert_id"] = published
    expert_id = _nonempty_str(cfg.get("expert_id"))
    if expert_id is not None:
        out["template_name"] = expert_id
    packages = cfg.get("skill_package_ids")
    if isinstance(packages, list):
        out["skill_package_ids"] = dump_skill_package_ids(
            [str(item) for item in packages if str(item).strip()]
        )
    welcome = _localized_text(cfg.get("welcome_message"))
    if welcome is not None:
        out["welcome_message"] = welcome
    return out


def welcome_from_row(row: Any) -> str | None:
    text = str(getattr(row, "welcome_message", None) or "").strip()
    return text or None


def overlay_skill_package_ids(cfg: dict[str, Any], row: Any) -> dict[str, Any]:
    """Prefer the column when set; otherwise keep a legacy ``config_json`` list."""
    from_col = parse_skill_package_ids_json(getattr(row, "skill_package_ids", None))
    if from_col is None:
        return cfg
    merged = dict(cfg)
    merged["skill_package_ids"] = from_col
    return merged


__all__ = [
    "PROFILE_CONFIG_KEYS",
    "dump_skill_package_ids",
    "dumps_config",
    "extract_profile_from_config",
    "overlay_skill_package_ids",
    "parse_config_json",
    "parse_skill_package_ids_json",
    "strip_profile_config",
    "welcome_from_row",
]
