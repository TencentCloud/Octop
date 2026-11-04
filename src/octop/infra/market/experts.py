"""Expert records from the octop.cloud market portal."""

from __future__ import annotations

from typing import Any

from octop.infra.market.normalize import order_slugs, pick_localized, valid_id
from octop.infra.market.source import cached

_SCENE_ORDER = (
    "ecommerce",
    "finance",
    "content-creation",
    "lifestyle",
    "marketing",
    "mysticism",
    "academic",
    "legal",
    "tech",
    "education",
    "healthcare",
    "hr",
    "media",
    "design",
)


def list_market_experts(
    query: str = "",
    scene: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return expert cards and the scene tabs present in the full catalog."""
    items = cached("experts")
    scenes = order_slugs((str(item.get("scene") or "") for item in items), _SCENE_ORDER)
    scene_key = scene.strip().lower()
    needle = query.strip().lower()
    filtered = [
        item
        for item in items
        if (not scene_key or str(item.get("scene") or "") == scene_key)
        and (not needle or needle in _haystack(item))
    ]
    return filtered, scenes


def get_market_expert(slug: str) -> dict[str, Any] | None:
    if not valid_id(slug):
        return None
    for item in cached("experts"):
        if item.get("slug") == slug:
            return item
    return None


def _haystack(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("slug") or ""),
        pick_localized(item.get("label"), "zh"),
        pick_localized(item.get("label"), "en"),
        pick_localized(item.get("description"), "zh"),
        pick_localized(item.get("description"), "en"),
        str(item.get("scene") or ""),
        str(item.get("sub_scene") or ""),
    ]
    return " ".join(parts).lower()
