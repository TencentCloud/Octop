"""Convert gateway MessageEvents to CLI stream chunks."""

from __future__ import annotations

from typing import Any

from octop_gateway.models import MessageEvent, MessageEventType, TextContent

__all__ = ["message_event_to_cli_chunks"]


def _event_text(event: MessageEvent) -> str:
    parts: list[str] = []
    for item in event.content or []:
        if isinstance(item, TextContent) and item.text:
            parts.append(item.text)
    return "\n".join(parts)


def message_event_to_cli_chunks(event: MessageEvent) -> list[dict[str, Any]]:
    """Map one IM-oriented MessageEvent onto the CLI chunk protocol."""
    if event.type == MessageEventType.ERROR:
        text = _event_text(event).strip()
        return [{"type": "error", "message": text or "error"}]
    if event.type in (
        MessageEventType.TYPING,
        MessageEventType.THINKING,
        MessageEventType.THINKING_DELTA,
        MessageEventType.FLUSH,
        MessageEventType.COMPLETED,
        MessageEventType.TOOL_END,
    ):
        return []
    if event.type == MessageEventType.TOOL_START:
        meta = event.metadata if isinstance(event.metadata, dict) else {}
        name = str(meta.get("tool_name") or meta.get("tool_key") or "").strip()
        if not name:
            return []
        return [{"type": "tool_start", "name": name}]
    text = _event_text(event)
    if not text:
        return []
    if event.type == MessageEventType.DELTA:
        return [{"type": "token", "content": text}]
    content = text if text.endswith("\n") else f"{text}\n"
    return [{"type": "token", "content": content}]
