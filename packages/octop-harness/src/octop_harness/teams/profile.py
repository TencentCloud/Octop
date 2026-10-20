"""Peer profile fields shared by the roster prompt and ``agent_list``."""

from __future__ import annotations

from typing import Any, Literal

Language = Literal["en", "zh"]

MAX_PEER_CARDS = 8


def localized_text(value: object, language: Language) -> str:
    """Pick a string from a plain value or ``{zh, en}`` map."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in (language, "zh", "en"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def peer_description(metadata: dict[str, Any], language: Language) -> str:
    return localized_text(metadata.get("description"), language)


def peer_guidance_cards(
    metadata: dict[str, Any],
    language: Language,
    *,
    limit: int = MAX_PEER_CARDS,
) -> list[dict[str, str]]:
    """Compact title + short description cards (no ``prompt`` text)."""
    raw = metadata.get("quick_prompts")
    if not isinstance(raw, list) or not raw:
        return []
    cards: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = localized_text(item.get("title"), language)
        if not title:
            continue
        card: dict[str, str] = {"title": title}
        detail = localized_text(item.get("description"), language)
        if detail:
            card["description"] = detail
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards
