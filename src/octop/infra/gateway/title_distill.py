"""Async LLM title distillation for new conversation threads."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from octop.infra.db.repos.thread_messages import ThreadMessageInput
from octop.infra.db.repos.threads import clip_thread_title
from octop.infra.gateway.process.history_projection import TurnHistoryTracker
from octop.infra.utils.llm_text import ainvoke_text

logger = logging.getLogger(__name__)

DistillWork = Callable[[], Awaitable[None]]

_USER_ROLES = frozenset({"human", "user"})
_AI_ROLES = frozenset({"ai", "assistant"})

_TITLE_DISTILL_SYSTEM = (
    "You write short sidebar titles for chat conversations. "
    "Given the user's first message and the assistant's first reply, "
    "output ONLY a concise title (at most 40 characters). "
    "No quotes, markdown, punctuation wrapping, or explanation. "
    "Use the same language as the user when it is obvious."
)


def extract_message_plain_text(message_json: str) -> str:
    """Best-effort plain text from a serialized LangChain/history message."""
    try:
        wire = json.loads(message_json)
    except (TypeError, ValueError):
        return ""
    if not isinstance(wire, dict):
        return str(wire).strip()

    text_val = wire.get("text")
    if isinstance(text_val, str):
        return text_val.strip()

    data = wire.get("data")
    content = data.get("content") if isinstance(data, dict) else wire.get("content")

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_type = str(block.get("type") or "").lower()
                if block_type in ("text", "input_text", "output_text"):
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
                elif "content" in block:
                    parts.append(str(block["content"]))
        return " ".join(part.strip() for part in parts if part.strip())
    return ""


def turn_snippet_for_title(inputs: list[ThreadMessageInput]) -> tuple[str, str] | None:
    """Return (user_text, assistant_text) when the turn has both sides."""
    user_text = ""
    assistant_text = ""
    for item in inputs:
        text = extract_message_plain_text(item.message_json)
        if not text:
            continue
        role = str(item.role or "").lower()
        if role in _USER_ROLES:
            user_text = text
        elif role in _AI_ROLES:
            assistant_text = text
    if user_text and assistant_text:
        return user_text, assistant_text
    return None


def first_turn_snippet_for_title(inputs: list[ThreadMessageInput]) -> tuple[str, str] | None:
    """Return the first user+assistant pair in transcript order."""
    user_text = ""
    for item in inputs:
        text = extract_message_plain_text(item.message_json)
        if not text:
            continue
        role = str(item.role or "").lower()
        if role in _USER_ROLES and not user_text:
            user_text = text
            continue
        if role in _AI_ROLES and user_text:
            return user_text, text
    return None


async def distill_thread_title(
    llm: Any,
    *,
    user_text: str,
    assistant_text: str,
    timeout: float = 45.0,
) -> str | None:
    """Ask the configured model for a short sidebar title."""
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    user_excerpt = user_text.strip()
    assistant_excerpt = assistant_text.strip()
    if len(user_excerpt) > 1200:
        user_excerpt = user_excerpt[:1200].rstrip() + "…"
    if len(assistant_excerpt) > 1200:
        assistant_excerpt = assistant_excerpt[:1200].rstrip() + "…"

    raw = await ainvoke_text(
        llm,
        [
            SystemMessage(content=_TITLE_DISTILL_SYSTEM),
            HumanMessage(
                content=(
                    "User message:\n"
                    f"{user_excerpt}\n\n"
                    "Assistant reply:\n"
                    f"{assistant_excerpt}\n\n"
                    "Title:"
                ),
            ),
        ],
        timeout=timeout,
    )
    line = (raw.splitlines()[0] if raw else "").strip().strip("\"'“”‘’")
    title = clip_thread_title(line)
    return title or None


class TitleDistillQueue:
    """Deduplicate per-thread distill jobs and run them off the hot path."""

    def __init__(self, *, max_pending: int = 100) -> None:
        self._max_pending = max_pending
        self._queue: asyncio.Queue[tuple[str, DistillWork]] = asyncio.Queue(maxsize=max_pending)
        self._known: set[str] = set()
        self._worker: asyncio.Task[None] | None = None

    def enqueue(self, thread_id: str, work: DistillWork) -> bool:
        if thread_id in self._known:
            return True
        if self._queue.full():
            return False
        self._known.add(thread_id)
        self._queue.put_nowait((thread_id, work))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="title-distill")
        return True

    async def _run(self) -> None:
        while True:
            thread_id, work = await self._queue.get()
            try:
                await work()
            except Exception:
                logger.exception("thread title distill failed: %s", thread_id)
            finally:
                self._known.discard(thread_id)
                self._queue.task_done()

    async def close(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker


def snippet_from_tracker(tracker: TurnHistoryTracker) -> tuple[str, str] | None:
    return turn_snippet_for_title(tracker.inputs)
