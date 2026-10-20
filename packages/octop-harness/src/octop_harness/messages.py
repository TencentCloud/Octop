"""Message parsing helpers for call results and OpenAI-style dict messages."""

from __future__ import annotations

from typing import Any

# Epoch-ms wall-clock stamp attached in ``additional_kwargs`` by
# :class:`~octop_harness.middleware.checkpoint_ts.CheckpointTsMiddleware`
# when a message is first appended. ``HarnessAgent.aget_history`` returns
# whatever is already stored — it does not backfill missing stamps.
CHECKPOINT_TS_KEY = "checkpoint_ts"

# Prefix on the AIMessage that ModelRetryMiddleware emits when retries are
# exhausted and ``on_failure`` returns a model-visible prompt instead of raising.
# Inbox jobs treat this as a failed peer task so the source agent sees the error.
MODEL_RETRY_FAILURE_MARK = "[model_call_failed]"


def message_role(msg: Any) -> str:  # noqa: PLR0911
    if isinstance(msg, dict):
        role = msg.get("role")
        if role:
            return str(role)
        msg_type = str(msg.get("type") or "")
        if msg_type in ("human", "user"):
            return "user"
        if msg_type in ("ai", "assistant"):
            return "assistant"
        return msg_type
    t = type(msg).__name__
    if "AIMessage" in t:
        return "assistant"
    if "HumanMessage" in t:
        return "user"
    return str(getattr(msg, "type", ""))


def message_content(msg: Any) -> str:
    content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content else ""


def extract_call_response(result: dict[str, Any]) -> str:
    """Extract the last assistant text from a langgraph ``call`` result."""
    messages = result.get("messages")
    if not isinstance(messages, list):
        return ""
    for msg in reversed(messages):
        if message_role(msg) not in ("assistant", "ai"):
            continue
        text = message_content(msg).strip()
        if text:
            return text
    return ""


def is_model_retry_failure_text(text: str | None) -> bool:
    """True when assistant text is a model-retry exhaustion prompt, not a real answer."""
    return text is not None and MODEL_RETRY_FAILURE_MARK in text


__all__ = [
    "CHECKPOINT_TS_KEY",
    "MODEL_RETRY_FAILURE_MARK",
    "extract_call_response",
    "is_model_retry_failure_text",
    "message_content",
    "message_role",
]
