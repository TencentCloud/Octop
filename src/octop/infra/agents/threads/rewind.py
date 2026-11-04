"""Rewind the current thread's conversation to before a user turn.

The LangGraph checkpoint is what the model reads next. This module rewrites
that checkpoint with the published harness graph API, then marks the same
tail in dashboard history so the bubbles stay on screen in gray. Files and
stored memories are left as they are. A slash command, including ``/undo``
itself, is not a conversation turn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_USER_ROLES = frozenset({"human", "user"})
_REMOVE_ALL = "__remove_all__"
_REWIND_CODES = {
    "empty": ErrorCode.UNDO_EMPTY,
    "not_found": ErrorCode.UNDO_NOT_FOUND,
    "bad_args": ErrorCode.SLASH_BAD_ARGS,
    "conflict": ErrorCode.UNDO_CONFLICT,
    "unavailable": ErrorCode.AGENT_NOT_RUNNING,
    "failed": ErrorCode.UNDO_FAILED,
    "busy": ErrorCode.UNDO_BUSY,
}


class RewindError(Exception):
    """Recoverable rewind failure. ``code`` is empty, not_found, bad_args, conflict, or failed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RewindOutcome:
    turns_undone: int
    prefill_text: str
    cut_message_id: str
    removed_count: int


def rewind_error(exc: RewindError) -> OctopError:
    code = _REWIND_CODES.get(exc.code, ErrorCode.UNDO_FAILED)
    return OctopError(code, exc.code)


def _role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("type") or message.get("role") or "").lower()
    type_name = type(message).__name__
    if type_name == "HumanMessage":
        return "human"
    if type_name == "AIMessage":
        return "ai"
    if type_name == "ToolMessage":
        return "tool"
    return str(getattr(message, "type", None) or getattr(message, "role", "") or "").lower()


def _message_id(message: Any) -> str:
    raw = message.get("id") if isinstance(message, dict) else getattr(message, "id", None)
    return str(raw).strip() if raw else ""


def _text(message: Any) -> str:
    content = (
        message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
    )
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str) and block.strip():
                parts.append(block.strip())
            elif isinstance(block, dict) and str(block.get("type") or "") == "text":
                text = str(block.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _is_slash_command(message: Any) -> bool:
    return _text(message).lstrip().startswith("/")


def _checkpoint_id(state: Any) -> str:
    config = getattr(state, "config", None) or {}
    configurable = config.get("configurable") if isinstance(config, dict) else None
    if not isinstance(configurable, dict):
        return ""
    return str(configurable.get("checkpoint_id") or "")


def _summary_past_cut(event: Any, cut_index: int) -> bool:
    if not isinstance(event, dict) or cut_index <= 0:
        return event is not None and cut_index <= 0
    cutoff = event.get("cutoff_index")
    return isinstance(cutoff, int) and cutoff > cut_index


def _pick_user_index(
    user_indexes: list[int],
    messages: list[Any],
    *,
    from_message_id: str | None,
    content: str | None,
    turns: int | None,
) -> int | None:
    wanted = (from_message_id or "").strip()
    if wanted:
        by_id = [index for index in user_indexes if _message_id(messages[index]) == wanted]
        if by_id:
            return by_id[0]
    text = (content or "").strip()
    if text:
        by_text = [index for index in user_indexes if _text(messages[index]) == text]
        if len(by_text) == 1:
            return by_text[0]
        if len(by_text) > 1 and turns is not None and turns >= 1:
            candidate = user_indexes[-min(turns, len(user_indexes))]
            if candidate in by_text:
                return candidate
        if by_text:
            return by_text[-1]
        if wanted:
            return None
    return None


def plan_user_rewind(
    messages: list[Any],
    *,
    turns: int | None = None,
    from_message_id: str | None = None,
    content: str | None = None,
) -> tuple[int, int, str, str]:
    """Return ``(cut_index, turns_undone, prefill_text, cut_message_id)``."""
    user_indexes = [
        index
        for index, message in enumerate(messages)
        if _role(message) in _USER_ROLES and not _is_slash_command(message)
    ]
    if not user_indexes:
        raise RewindError("empty")
    picked = _pick_user_index(
        user_indexes,
        messages,
        from_message_id=from_message_id,
        content=content,
        turns=turns,
    )
    if (from_message_id or "").strip() or (content or "").strip():
        if picked is None:
            raise RewindError("not_found")
        cut = picked
    else:
        count = 1 if turns is None else turns
        if count < 1:
            raise RewindError("bad_args")
        count = min(count, len(user_indexes))
        cut = user_indexes[-count]
    undone = sum(1 for index in user_indexes if index >= cut)
    target = messages[cut]
    return cut, undone, _text(target), _message_id(target)


async def apply_user_rewind(
    graph: Any,
    thread_id: str,
    *,
    turns: int | None = None,
    from_message_id: str | None = None,
    content: str | None = None,
) -> RewindOutcome:
    """Replace the live transcript with the prefix before the chosen user turn."""
    from langchain_core.messages import RemoveMessage

    tid = thread_id.strip()
    if not tid:
        raise RewindError("failed")
    config: dict[str, Any] = {"configurable": {"thread_id": tid}}
    try:
        state = await graph.aget_state(config)
    except Exception as exc:
        raise RewindError("failed") from exc
    values = getattr(state, "values", None) or {}
    messages = list(values.get("messages") or [])
    pinned = _checkpoint_id(state)
    cut, undone, prefill, cut_id = plan_user_rewind(
        messages, turns=turns, from_message_id=from_message_id, content=content
    )
    try:
        again = await graph.aget_state(config)
    except Exception as exc:
        raise RewindError("failed") from exc
    if _checkpoint_id(again) != pinned:
        raise RewindError("conflict")
    kept = messages[:cut]
    updates: dict[str, Any] = {"messages": [RemoveMessage(id=_REMOVE_ALL), *kept]}
    if _summary_past_cut(values.get("_summarization_event"), cut):
        updates["_summarization_event"] = None
    try:
        await graph.aupdate_state(config, updates)
    except Exception as exc:
        raise RewindError("failed") from exc
    return RewindOutcome(
        turns_undone=undone,
        prefill_text=prefill,
        cut_message_id=cut_id,
        removed_count=len(messages) - cut,
    )


def _clear_context_usage(harness: Any, thread_id: str) -> None:
    middleware = getattr(harness, "_context_usage_mw", None)
    clear = getattr(middleware, "clear_snapshot", None)
    if callable(clear):
        clear(thread_id)


async def rewind_thread(
    *,
    harness: Any,
    thread_id: str,
    turns: int | None = None,
    from_message_id: str | None = None,
    content: str | None = None,
    thread_message_repo: Any | None = None,
    history_archive: Any | None = None,
    hitl: Any | None = None,
    agent_id: str = "",
    user_id: int | None = None,
) -> RewindOutcome:
    """Rewind *thread_id* and gray the same tail in dashboard history."""
    graph = getattr(harness, "graph", None)
    checkpointer = getattr(harness, "checkpointer", None)
    if graph is None or not checkpointer:
        raise rewind_error(RewindError("unavailable"))
    try:
        outcome = await apply_user_rewind(
            graph,
            thread_id,
            turns=turns,
            from_message_id=from_message_id,
            content=content,
        )
    except RewindError as exc:
        if (
            exc.code == "not_found"
            and turns is not None
            and (from_message_id or "").strip()
            and not (content or "").strip()
        ):
            try:
                outcome = await apply_user_rewind(graph, thread_id, turns=turns)
            except RewindError as retry:
                raise rewind_error(retry) from retry
        else:
            raise rewind_error(exc) from exc
    _clear_context_usage(harness, thread_id.strip())
    _mark_projection(thread_message_repo, history_archive, thread_id, outcome.cut_message_id)
    if hitl is not None and agent_id:
        hitl.expire_pending_for_thread(thread_id, agent_id=agent_id, user_id=user_id)
    return outcome


def _mark_projection(
    thread_message_repo: Any | None,
    history_archive: Any | None,
    thread_id: str,
    message_id: str,
) -> None:
    if not message_id:
        logger.warning("rewind left history projection unmarked; cut message has no id")
        return
    if thread_message_repo is not None:
        try:
            thread_message_repo.mark_reverted_from_message_id(thread_id, message_id)
        except Exception:
            logger.warning(
                "failed to mark thread_messages after rewind thread=%s",
                thread_id,
                exc_info=True,
            )
    store = getattr(history_archive, "store", None)
    if store is None:
        return
    try:
        store.mark_reverted_from(thread_id, message_id)
    except Exception:
        logger.warning(
            "failed to mark history archive after rewind thread=%s",
            thread_id,
            exc_info=True,
        )
