"""Shared helpers for single-turn LLM invoke via :class:`ModelAccess`."""

from __future__ import annotations

import re
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_THINKING_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)


def build_text_messages(
    prompt: str,
    *,
    system: str | None = None,
) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    return messages


def bind_call_options(
    model: object,
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_format: Literal["text", "json"] = "text",
    timeout_s: float | None = None,
    extra_body: dict[str, Any] | None = None,
) -> Any:
    kwargs: dict[str, object] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    if timeout_s is not None and timeout_s > 0:
        # OpenAI / Anthropic adapters accept ``timeout``. Do not bind
        # ``max_retries=0`` — some providers reject it before the request.
        kwargs["timeout"] = timeout_s
    # ``response_format={"type": "json_object"}`` is OpenAI-specific;
    # Anthropic's adapter rejects ``json_object`` before sending.
    if response_format == "json" and _is_langchain_openai_model(model):
        kwargs["response_format"] = {"type": "json_object"}
    # Vendor extensions (thinking controls, ``reasoning_effort``) ride
    # ChatOpenAI's ``extra_body``. Copy so a later mutate cannot change the
    # bound request. Other adapters reject the key, so skip them.
    if extra_body and _is_langchain_openai_model(model):
        kwargs["extra_body"] = dict(extra_body)
    if not kwargs:
        return model
    bind = getattr(model, "bind", None)
    if bind is None:
        return model
    try:
        return bind(**kwargs)
    except (TypeError, ValueError, AttributeError):
        return model


def stringify_content(content: object) -> str:
    if isinstance(content, list):
        joined = "".join(_stringify_block(block) for block in content)
        return _THINKING_RE.sub("", joined).strip()
    text = content if isinstance(content, str) else str(content)
    return _THINKING_RE.sub("", text).strip()


def _stringify_block(block: object) -> str:
    if not isinstance(block, dict):
        return str(block)
    block_type = str(block.get("type") or "").lower()
    if block_type in ("thinking", "reasoning"):
        return ""
    text = block.get("text")
    return text if isinstance(text, str) else ""


def _is_langchain_openai_model(model: object) -> bool:
    for cls in type(model).mro():
        module = getattr(cls, "__module__", "")
        if module.startswith("langchain_openai"):
            return True
    return False


# Backwards-compatible alias (pre-1360 name).
_supports_openai_response_format = _is_langchain_openai_model


__all__ = [
    "bind_call_options",
    "build_text_messages",
    "stringify_content",
]
