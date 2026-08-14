"""``tools.*`` — built-in agent tool display names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.i18n.loader import _load_all, lookup
from octop.infra.utils.locale import Locale, normalize_locale

# Built-in tools that must stay available without HITL — hidden from the approval picker.
HITL_TOOL_EXCLUDE: frozenset[str] = frozenset(
    {
        # Meta / agent internals
        "unknown",
        "current_time",
        "write_todos",
        # Memory
        "memory_search",
        "memory_get",
        # Knowledge base
        "search_knowledge",
        # Cron
        "cronjob_list",
        "cronjob_get",
        "cronjob_create",
        "cronjob_update",
        "cronjob_delete",
        "cronjob_run_now",
        # Sub-agent / multi-agent orchestration
        "task",
        "agent_list",
        "ask_agent",
        "call_agent",
        "acp_runner",
    }
)

__all__ = [
    "HITL_TOOL_EXCLUDE",
    "HitlToolCatalogEntry",
    "all_tool_labels",
    "hitl_tool_catalog",
    "tool_display_name",
]


@dataclass(frozen=True)
class HitlToolCatalogEntry:
    name: str
    label_zh: str
    label_en: str


def tool_display_name(name: str | None, locale: str | Locale = "en") -> str:
    if not name:
        return lookup("tools.unknown", locale) or "unknown"
    text = lookup(f"tools.{name}", locale)
    return text if text is not None else name


def all_tool_labels(locale: str | Locale = "en") -> dict[str, str]:
    loc = normalize_locale(str(locale))
    tables = _load_all()
    node: Any = tables.get(loc, {}).get("tools")
    if not isinstance(node, dict):
        node = tables.get("en", {}).get("tools")
    if not isinstance(node, dict):
        return {}
    return {str(k): str(v) for k, v in node.items() if isinstance(v, str)}


def hitl_tool_catalog() -> list[HitlToolCatalogEntry]:
    """Built-in tools eligible for human-in-the-loop approval (excludes must-use internals)."""
    labels_zh = all_tool_labels("zh")
    labels_en = all_tool_labels("en")
    names = sorted((set(labels_zh) | set(labels_en)) - HITL_TOOL_EXCLUDE)
    return [
        HitlToolCatalogEntry(
            name=name,
            label_zh=labels_zh.get(name, name),
            label_en=labels_en.get(name, name),
        )
        for name in names
    ]
