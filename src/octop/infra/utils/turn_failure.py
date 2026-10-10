"""One-line server logs for swallowed model / tool failures."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

logger = logging.getLogger(__name__)

_DETAIL_MAX = 500
_TURN_MODEL: ContextVar[str] = ContextVar("octop_turn_model", default="")


def _truncate(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _DETAIL_MAX:
        return compact
    return compact[: _DETAIL_MAX - 3] + "..."


def _field(key: str, value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    return f"{key}={text}"


@contextmanager
def turn_model_scope(model: str) -> Iterator[None]:
    """Bind the model label for :func:`_model_retry_on_failure` during one turn."""
    token: Token[str] = _TURN_MODEL.set((model or "").strip())
    try:
        yield
    finally:
        _TURN_MODEL.reset(token)


def current_turn_model() -> str:
    return _TURN_MODEL.get()


def log_turn_failure(
    kind: str,
    *,
    detail: str,
    agent_id: str = "",
    thread_id: str = "",
    model: str = "",
    tool: str = "",
    exc: BaseException | None = None,
    level: int = logging.WARNING,
) -> None:
    """Emit ``turn failure kind=… agent=…`` so model/tool misses still grep."""
    parts = [f"turn failure kind={kind}"]
    for key, value in (
        ("agent", agent_id),
        ("thread", thread_id),
        ("model", model),
        ("tool", tool),
    ):
        piece = _field(key, value)
        if piece:
            parts.append(piece)
    line = f"{' '.join(parts)} : {_truncate(detail) or 'unknown error'}"
    logger.log(level, line, exc_info=exc)


def _attr(msg: Any, key: str) -> Any:
    if isinstance(msg, dict):
        return msg.get(key)
    return getattr(msg, key, None)


def _tool_name(msg: Any, fallback: str) -> str:
    name = _attr(msg, "name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return fallback


def _tool_detail(msg: Any) -> str:
    content = _attr(msg, "content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _tool_call_id(msg: Any) -> str:
    for key in ("tool_call_id", "id"):
        value = _attr(msg, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _dedupe_key(tool: str, detail: str, call_id: str) -> str:
    if call_id:
        return f"id:{call_id}"
    return f"txt:{tool}:{_truncate(detail)[:120]}"


def iter_failed_tool_results(chunk: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return ``(tool_name, detail, dedupe_key)`` for ``status=error`` only."""
    if chunk.get("type") != "tool_result":
        return []
    raw_name = chunk.get("name")
    fallback = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else "tool"
    messages = chunk.get("messages")
    found: list[tuple[str, str, str]] = []
    if isinstance(messages, list):
        for msg in messages:
            if str(_attr(msg, "status") or "") != "error":
                continue
            tool = _tool_name(msg, fallback)
            detail = _tool_detail(msg) or "tool error"
            found.append((tool, detail, _dedupe_key(tool, detail, _tool_call_id(msg))))
        if found:
            return found
    if str(chunk.get("status") or "") == "error":
        detail = str(chunk.get("content") or chunk.get("error") or "tool error")
        call_id = chunk.get("id")
        key = _dedupe_key(
            fallback,
            detail,
            call_id.strip() if isinstance(call_id, str) else "",
        )
        return [(fallback, detail, key)]
    return []


def log_failed_tool_results(
    chunk: dict[str, Any],
    *,
    agent_id: str,
    thread_id: str = "",
    seen: set[str] | None = None,
    live: bool = True,
) -> None:
    """Log live ``status=error`` tool results. Skip history replay and duplicates."""
    if not live:
        return
    for tool, detail, key in iter_failed_tool_results(chunk):
        if seen is not None:
            if key in seen:
                continue
            seen.add(key)
        log_turn_failure(
            "tool",
            detail=detail,
            agent_id=agent_id,
            thread_id=thread_id,
            tool=tool,
        )
