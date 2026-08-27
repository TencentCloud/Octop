"""Fork a conversation thread from a selected assistant reply.

Copies LangGraph checkpoint messages *through* that assistant turn into a new
thread, leaving the source transcript unchanged. The client continues in the
forked thread without prefilling the previous user question.
"""

from __future__ import annotations

import logging
from typing import Any

from octop.i18n import tr
from octop.infra.db.repos.threads import ThreadRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry

logger = logging.getLogger(__name__)

# Full-transcript read for fork; history HTTP pagination uses a much smaller cap.
_FORK_HISTORY_LIMIT = 100_000


def _fork_title(source_title: str | None, locale: str) -> str:
    """Return a sidebar title that distinguishes a fork from its source thread."""
    base = (source_title or "").strip()
    if base:
        return f"{base}{tr('threads.fork_title_suffix', locale)}"
    return tr("threads.fork_default_title", locale)


def _msg_id(msg: Any) -> str:
    raw = msg.get("id") if isinstance(msg, dict) else getattr(msg, "id", None)
    return str(raw).strip() if raw else ""


def _is_assistant_message(msg: Any) -> bool:
    if isinstance(msg, dict):
        role = str(msg.get("role") or "")
        if role:
            return role == "assistant"
        msg_type = str(msg.get("type") or "")
        return msg_type in ("ai", "assistant")
    type_name = type(msg).__name__
    if "AIMessage" in type_name:
        return True
    role = str(getattr(msg, "role", None) or getattr(msg, "type", "") or "")
    return role in ("assistant", "ai")


def _message_text(msg: Any) -> str:
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                if block.strip():
                    parts.append(block.strip())
            elif isinstance(block, dict) and str(block.get("type") or "") == "text":
                text = str(block.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _has_tool_calls(msg: Any) -> bool:
    if isinstance(msg, dict):
        calls = msg.get("tool_calls") or msg.get("tool_call_chunks")
        return bool(calls)
    calls = getattr(msg, "tool_calls", None)
    return bool(calls)


def _assistant_answer_indices(messages: list[Any]) -> list[int]:
    """Indices of final assistant answers (skip tool-calling shells).

    Aligns with the dashboard: one answer bubble per turn, not intermediate
    AIMessages that only request tools (even if they also carry short text).
    """
    indices: list[int] = []
    for i, msg in enumerate(messages):
        if not _is_assistant_message(msg):
            continue
        if _has_tool_calls(msg):
            continue
        indices.append(i)
    return indices


def find_assistant_fork_index(
    messages: list[Any],
    *,
    message_id: str | None = None,
    content: str | None = None,
    assistant_turns_from_end: int | None = None,
) -> int:
    """Return the index of the selected assistant answer in *messages*.

    Prefers a suffix count of answer turns (stable across client-generated UI
    ids). When that locator is present it is authoritative — content/id are
    only used as fallbacks when the suffix count is absent or out of range.
    """
    answers = _assistant_answer_indices(messages)
    if not answers:
        raise OctopError(ErrorCode.NOT_FOUND, "no assistant message to fork from")

    wanted_id = (message_id or "").strip()
    wanted_text = (content or "").strip()

    if (
        assistant_turns_from_end is not None
        and assistant_turns_from_end >= 1
        and assistant_turns_from_end <= len(answers)
    ):
        return answers[-assistant_turns_from_end]

    if wanted_id:
        for idx in answers:
            if _msg_id(messages[idx]) == wanted_id:
                return idx
        # Client id may point at a non-answer AIMessage; still allow exact id match.
        for i, msg in enumerate(messages):
            if _is_assistant_message(msg) and _msg_id(msg) == wanted_id:
                return i

    if wanted_text:
        matches = [idx for idx in answers if _message_text(messages[idx]) == wanted_text]
        if matches:
            return matches[-1]

    raise OctopError(ErrorCode.NOT_FOUND, "assistant message not found in thread")


async def load_checkpoint_messages(harness: Any, thread_id: str) -> list[Any]:
    """Return the full checkpoint transcript (oldest first)."""
    graph = getattr(harness, "graph", None)
    if graph is not None and hasattr(graph, "aget_state"):
        try:
            state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            raw = list((state.values or {}).get("messages") or []) if state is not None else []
            if raw:
                return raw
        except Exception:
            logger.warning(
                "fork: graph.aget_state failed for thread=%s",
                thread_id,
                exc_info=True,
            )
    aget_history = getattr(harness, "aget_history", None)
    if aget_history is not None:
        return list(await aget_history(thread_id, limit=_FORK_HISTORY_LIMIT))
    return []


async def write_checkpoint_messages(
    harness: Any,
    *,
    thread_id: str,
    messages: list[Any],
) -> None:
    """Seed *thread_id* with *messages* (no-op when the list is empty)."""
    if not messages:
        return
    graph = getattr(harness, "graph", None)
    aupdate = getattr(graph, "aupdate_state", None) if graph is not None else None
    if aupdate is None:
        raise OctopError(
            ErrorCode.AGENT_NOT_RUNNING,
            "agent checkpointer cannot copy thread state",
        )
    await aupdate(
        {"configurable": {"thread_id": thread_id}},
        {"messages": messages},
    )


async def fork_dashboard_thread(
    *,
    thread_registry: ThreadRegistry,
    harness: Any,
    source: ThreadRow,
    user_id: int,
    message_id: str | None = None,
    content: str | None = None,
    assistant_turns_from_end: int | None = None,
    locale: str = "en",
    thread_message_repo: Any | None = None,
) -> dict[str, Any]:
    """Create a dashboard thread seeded through the selected assistant reply."""
    messages = await load_checkpoint_messages(harness, source.thread_id)
    idx = find_assistant_fork_index(
        messages,
        message_id=message_id,
        content=content,
        assistant_turns_from_end=assistant_turns_from_end,
    )
    # Include the selected assistant message (and any tool traffic before it).
    prefix = messages[: idx + 1]
    prefix_projection_inputs: list[Any] | None = None
    if thread_message_repo is not None:
        from octop.infra.gateway.process.history_projection import (  # noqa: PLC0415
            message_inputs,
        )

        projection_inputs = message_inputs(messages)
        prefix_projection_inputs = message_inputs(prefix)
        # A fork already paid the explicit full-history read cost. Reuse it to
        # heal an empty read model instead of decoding the source again later.
        thread_message_repo.append_if_ready(source.thread_id, projection_inputs)

    session_key = ThreadRegistry.dashboard_key(agent_id=source.agent_id, user_id=user_id)
    dest_id = thread_registry.create_thread(
        agent_id=source.agent_id,
        user_id=user_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        title=None,
        last_active=0,
    )
    try:
        await write_checkpoint_messages(harness, thread_id=dest_id, messages=prefix)
        if thread_message_repo is not None:
            assert prefix_projection_inputs is not None
            thread_message_repo.append_if_ready(dest_id, prefix_projection_inputs)
    except Exception:
        thread_registry.delete_thread(dest_id)
        raise

    copied = len(prefix)
    if copied > 0:
        thread_registry.update_title(dest_id, _fork_title(source.title, locale))
    thread_registry.update_composer(
        dest_id,
        model_ref=source.model_ref,
        reasoning_mode=source.reasoning_mode,
        reasoning_effort=source.reasoning_effort,
    )
    await thread_registry.rebind(
        session_key=session_key,
        thread_id=dest_id,
        agent_id=source.agent_id,
    )
    row = thread_registry.get_thread(dest_id)
    return {
        "thread_id": dest_id,
        "session_key": session_key,
        "source_thread_id": source.thread_id,
        "copied_messages": copied,
        "title": row.title if row is not None else None,
        "last_active": row.last_active if row is not None else 0,
        "created_at": row.created_at if row is not None else 0,
    }
