"""Dashboard thread list/history REST APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from octop.api.common.agent import require_agent_row
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import RebindSessionBody, RenameThreadBody
from octop.api.routers.chat.serialize import (
    HISTORY_DEFAULT_LIMIT,
    _clamp_history_limit,
    _load_thread_messages,
)
from octop.infra.agents.context_breakdown import SEGMENT_KEYS, compute_context_breakdown
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry, thread_row_has_messages

router = APIRouter()


def _require_thread(
    server: Any, agent_id: str, thread_id: str, user: Any, as_user: int | None
) -> Any:
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    row = server.app_runtime.gateway.thread_registry.get_thread(thread_id)
    if row is None or row.agent_id != agent_id:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
    return row


@router.get("/agents/{agent_id}/threads", summary="List threads")
async def list_threads(
    agent_id: str,
    limit: int = 50,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List conversation threads for an agent, including which thread is active for this user."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    thread_registry = server.app_runtime.gateway.thread_registry
    rows = thread_registry.list_threads(agent_id=agent_id, limit=limit)
    effective_uid = as_user if as_user is not None else user.id
    bound = thread_registry.get_bound_thread_id(
        ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=effective_uid)
    )
    return [
        {
            "thread_id": r.thread_id,
            "title": r.title,
            "channel_type": r.channel_type,
            "session_key": r.session_key,
            "last_active": r.last_active,
            "created_at": r.created_at,
            "is_active": r.thread_id == bound,
            "has_messages": thread_row_has_messages(r),
            "pinned": r.pinned,
        }
        for r in rows
    ]


@router.post("/agents/{agent_id}/threads", status_code=201, summary="New thread")
async def create_thread(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Start a new conversation (/new equivalent for dashboard)."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    effective_uid = as_user if as_user is not None else user.id
    sk = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=effective_uid)
    tid = await server.app_runtime.gateway.thread_registry.reset(
        agent_id=agent_id,
        user_id=effective_uid,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        channel_subject_id=str(user.id),
    )
    return {"thread_id": tid, "session_key": sk}


def _parse_csv_query(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/context-usage",
    summary="Context window usage breakdown",
)
async def get_thread_context_usage(
    agent_id: str,
    thread_id: str,
    max_tokens: int = 128_000,
    input_tokens: int | None = None,
    mcp_servers: str | None = None,
    skills: str | None = None,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return persisted context-window usage for a thread (harness-agent snapshot)."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    registry = server.app_runtime.agent_registry
    breakdown = await compute_context_breakdown(
        registry,
        agent_id=agent_id,
        thread_id=thread_id,
        max_tokens=max_tokens,
        input_tokens=input_tokens,
        mcp_servers=_parse_csv_query(mcp_servers),
        skills=_parse_csv_query(skills),
    )
    return {
        "max_tokens": breakdown.max_tokens,
        "used_tokens": breakdown.used_tokens,
        "segments": [
            {"key": key, "tokens": breakdown.segments.get(key, 0)}
            for key in SEGMENT_KEYS
            if breakdown.segments.get(key, 0) > 0
        ],
    }


@router.get("/agents/{agent_id}/threads/{thread_id}/history", summary="Thread history")
async def get_thread_history(
    agent_id: str,
    thread_id: str,
    limit: int = HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return recent messages for a thread, including tool calls and thinking blocks."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    page_limit = _clamp_history_limit(limit)
    page_offset = max(0, offset)
    messages, has_more = await _load_thread_messages(
        server,
        agent_id,
        thread_id,
        page_limit,
        offset=page_offset,
        user=user,
    )
    return {
        "thread_id": thread_id,
        "messages": messages,
        "has_more": has_more,
        "limit": page_limit,
        "offset": page_offset,
    }


@router.post(
    "/agents/{agent_id}/threads/{thread_id}/read",
    status_code=204,
    summary="Mark thread read",
)
async def mark_thread_read(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Clear unread message count for a thread (e.g. when the user opens it in the dashboard)."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    server.app_runtime.gateway.thread_registry.mark_thread_read(thread_id)


@router.patch("/agents/{agent_id}/session", summary="Rebind dashboard session")
async def rebind_session(
    agent_id: str,
    body: RebindSessionBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Point the user's dashboard session at an existing thread."""
    require_agent_row(agent_id, user=user, as_user=None, server=server)
    sk = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user.id)
    row = server.app_runtime.gateway.thread_registry.get_thread(body.thread_id)
    if row is None or row.agent_id != agent_id:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {body.thread_id!r} not found")
    await server.app_runtime.gateway.thread_registry.rebind(
        session_key=sk, thread_id=body.thread_id, agent_id=agent_id
    )
    return {"session_key": sk, "thread_id": body.thread_id}


@router.patch("/agents/{agent_id}/threads/{thread_id}", summary="Update thread")
async def patch_thread(
    agent_id: str,
    thread_id: str,
    body: RenameThreadBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Rename a thread or toggle its pinned state in the sidebar."""
    row = _require_thread(server, agent_id, thread_id, user, as_user)
    if body.title is None and body.pinned is None:
        return {
            "thread_id": thread_id,
            "title": row.title,
            "pinned": row.pinned,
        }
    registry = server.app_runtime.gateway.thread_registry
    if body.title is not None:
        registry.update_title(thread_id, body.title)
    if body.pinned is not None:
        registry.set_pinned(thread_id, body.pinned)
    updated = registry.get_thread(thread_id)
    assert updated is not None
    return {
        "thread_id": thread_id,
        "title": updated.title,
        "pinned": updated.pinned,
    }


@router.delete("/agents/{agent_id}/threads/{thread_id}", status_code=204, summary="Delete thread")
async def delete_thread(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Remove a conversation thread and its metadata."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    server.app_runtime.gateway.thread_registry.delete_thread(thread_id)
