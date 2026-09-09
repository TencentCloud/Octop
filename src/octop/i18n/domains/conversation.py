"""``conversation.*`` — Ask / Plan / Craft mode system hints (#616)."""

from __future__ import annotations

from octop.i18n.loader import tr
from octop.infra.agents.conversation_mode import ConversationMode
from octop.infra.utils.locale import Locale

__all__ = [
    "conversation_mode_plan_brief_block",
    "conversation_mode_system_hint",
    "conversation_mode_tool_blocked",
]


def conversation_mode_system_hint(
    mode: ConversationMode,
    locale: str | Locale = "en",
) -> str:
    """Localized system hint for the turn's conversation mode."""
    return tr(f"conversation.mode.{mode}_system_hint", locale)


def conversation_mode_plan_brief_block(
    brief: str,
    locale: str | Locale = "en",
) -> str:
    """Wrap an approved plan brief for system-prompt injection (Craft handoff)."""
    cleaned = brief.strip()
    if not cleaned:
        return ""
    prefix = tr("conversation.mode.plan_brief_prefix", locale)
    return f"{prefix}\n\n{cleaned}"


def conversation_mode_tool_blocked(
    tool_name: str,
    mode: ConversationMode,
    locale: str | Locale = "en",
) -> str:
    """Error text when a denylisted tool is invoked under Ask/Plan."""
    return tr(
        "conversation.mode.tool_blocked",
        locale,
        tool_name=tool_name,
        mode=mode,
    )
