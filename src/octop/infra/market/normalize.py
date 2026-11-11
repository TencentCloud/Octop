"""Turn untrusted catalog JSON into bounded strings and lists."""

from __future__ import annotations

import re
from typing import Any

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")


def pick_localized(value: Any, language: str) -> str:
    """Pick zh or en. A plain string is used for both languages."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        zh = str(value.get("zh") or "").strip()
        en = str(value.get("en") or "").strip()
        if language.lower().startswith("zh"):
            return zh or en
        return en or zh
    return ""


def valid_id(value: str) -> bool:
    return _ID_RE.fullmatch(value) is not None


def order_slugs(present: Any, order: tuple[str, ...]) -> list[str]:
    values = {str(item).strip() for item in present if str(item).strip()}
    known = set(order)
    extras = sorted(item for item in values if item not in known)
    return [item for item in order if item in values] + extras


def sort_recent(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[str, str]:
        stamp = str(item.get("updated_at") or "")
        name = str(item.get("slug") or item.get("id") or "")
        return (stamp, name)

    return sorted(items, key=key, reverse=True)
