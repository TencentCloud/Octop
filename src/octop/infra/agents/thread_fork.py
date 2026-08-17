"""Fork a conversation thread from a selected user message.

Copies LangGraph checkpoint messages *strictly before* that user turn into a
new thread, leaving the source transcript unchanged. The selected question is
intentionally omitted so the dashboard can prefill the composer and send a
different follow-up — the non-destructive counterpart of "edit message".
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


def _is_user_message(msg: Any) -> bool:
    if isinstance(msg, dict):
        role = str(msg.get("role") or "")
        if role:
            return role == "user"
        msg_type = str(msg.get("type") or "")
        return msg_type in ("human", "user")
    type_name = type(msg).__name__
    if "HumanMessage" in type_name:
        return True
    role = str(getattr(msg, "role", None) or getattr(msg, "type", "") or "")
    return role in ("user", "human")


def _user_text(msg: Any) -> str:
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


def find_user_fork_index(
    messages: list[Any],
    *,
    message_id: str,
    content: str | None = None,
    user_turns_from_end: int | None = None,
) -> int:
    """Return the index of the selected user message in *messages*.

    Prefers a suffix count of user turns (stable across client-generated UI
    ids), then checkpoint ``id``, then exact text content.
    """
    humans = [i for i, msg in enumerate(messages) if _is_user_message(msg)]
    if not humans:
        raise OctopError(ErrorCode.NOT_FOUND, "no user message to fork from")

    wanted_id = (message_id or "").strip()
    wanted_text = (content or "").strip()

    if (
        user_turns_from_end is not None
        and user_turns_from_end >= 1
        and user_turns_from_end <= len(humans)
    ):
        idx = humans[-user_turns_from_end]
        if not wanted_text or _user_text(messages[idx]) == wanted_text:
            return idx
        if wanted_id and _msg_id(messages[idx]) == wanted_id:
            return idx

    if wanted_id:
        for idx in humans:
            if _msg_id(messages[idx]) == wanted_id:
                return idx

    if wanted_text:
        matches = [idx for idx in humans if _user_text(messages[idx]) == wanted_text]
        if matches:
            return matches[-1]

    raise OctopError(ErrorCode.NOT_FOUND, "user message not found in thread")


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
    message_id: str,
    content: str | None = None,
    user_turns_from_end: int | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Create a dashboard thread seeded with the source prefix before *message_id*."""
    wanted_id = (message_id or "").strip()
    if not wanted_id:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "message_id is required")

    messages = await load_checkpoint_messages(harness, source.thread_id)
    idx = find_user_fork_index(
        messages,
        message_id=wanted_id,
        content=content,
        user_turns_from_end=user_turns_from_end,
    )
    prefix = messages[:idx]

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
