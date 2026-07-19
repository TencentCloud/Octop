"""Shared helpers for one-shot LangChain LLM calls.

Used by chat polish, proactive care (memory), and SkillHub expert
manifest generation so text extraction and invoke timing stay consistent.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

_THINKING_RE = re.compile(
    r"<think>[\s\S]*?</think>\s*",
    re.IGNORECASE,
)


def strip_thinking(text: str) -> str:
    """Remove ``<think>...</think>`` blocks from model output."""
    return _THINKING_RE.sub("", text).strip()


def llm_text_content(result: Any) -> str:
    """Extract plain text from a LangChain ``ainvoke`` result.

    Skips thinking/reasoning content blocks and strips ``<think>`` tags
    so callers get the user-visible response only.
    """
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return strip_thinking(content)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_type = str(block.get("type") or "").lower()
                if block_type in ("thinking", "reasoning"):
                    continue
                if block_type == "text":
                    parts.append(str(block.get("text") or ""))
                else:
                    text = block.get("text") or block.get("content")
                    if text:
                        parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
        return strip_thinking("".join(parts))
    return strip_thinking(str(content or ""))


async def ainvoke_text(
    llm: Any,
    messages: list[Any],
    *,
    timeout: float | None = 30.0,
) -> str:
    """Invoke *llm* with *messages* and return stripped plain text.

    When *timeout* is set, wraps ``ainvoke`` in ``asyncio.wait_for``
    (same pattern as chat polish). Pass ``timeout=None`` to wait unbound.
    """
    coro = llm.ainvoke(messages)
    if timeout is None:
        result = await coro
    else:
        result = await asyncio.wait_for(coro, timeout=timeout)
    return llm_text_content(result)
