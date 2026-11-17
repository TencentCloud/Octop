"""Keep the ACP tool title when a later update omits it.

Cursor sends ``tool_call`` with a title, then ``tool_call_update`` with only a
status. The harness fills a missing title with ``unknown``, and the chat
catalog translates that to "未知工具". Remember the first real title for each
call so the update keeps the original name.
"""

from __future__ import annotations

from typing import Any

_INSTALLED = False
_TITLES = "_octop_tool_titles"
_PLACEHOLDER = "unknown"


def _raw_tool_name(update: Any) -> str:
    title = getattr(update, "title", None)
    if isinstance(title, str):
        text = title.strip()
        if text and text.lower() != _PLACEHOLDER:
            return text
    raw = getattr(update, "raw_input", None)
    if isinstance(raw, dict):
        for key in ("name", "toolName", "tool_name", "tool"):
            value = raw.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text and text.lower() != _PLACEHOLDER:
                    return text
    return ""


def install_acp_tool_titles() -> None:
    """Reuse the first real ACP tool title when a later update has none."""
    global _INSTALLED
    if _INSTALLED:
        return
    from octop_harness.acp.client import ACPHostedClient

    original_event = ACPHostedClient._tool_event_from_state
    original_start = ACPHostedClient.start_prompt

    def start_prompt(self: Any, on_message: Any) -> None:
        setattr(self, _TITLES, {})
        original_start(self, on_message)

    def _tool_event_from_state(self: Any, update: Any) -> dict[str, Any] | None:
        event = original_event(self, update)
        if not isinstance(event, dict):
            return event
        call_id = str(event.get("call_id") or "")
        remembered = getattr(self, _TITLES, None)
        if not isinstance(remembered, dict):
            remembered = {}
            setattr(self, _TITLES, remembered)
        raw = _raw_tool_name(update)
        current = str(event.get("name") or "")
        if raw:
            chosen = raw
        elif current and current.lower() != _PLACEHOLDER:
            chosen = current
        elif call_id and isinstance(remembered.get(call_id), str):
            chosen = str(remembered[call_id])
        else:
            chosen = current
        if call_id and chosen and chosen.lower() != _PLACEHOLDER:
            remembered[call_id] = chosen
            event["name"] = chosen
            event["title"] = chosen
            event["detail"] = chosen
        return event

    ACPHostedClient.start_prompt = start_prompt  # type: ignore[method-assign]
    ACPHostedClient._tool_event_from_state = _tool_event_from_state  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = ["install_acp_tool_titles"]
