"""Dashboard thread list/history REST APIs."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request

from octop.api.common.agent import require_agent_row
from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import ForkThreadBody, RebindSessionBody, RenameThreadBody
from octop.api.routers.chat.serialize import (
    HISTORY_DEFAULT_LIMIT,
    _clamp_history_limit,
    _load_thread_messages,
)
from octop.infra.agents.context_breakdown import SEGMENT_KEYS, compute_context_breakdown
from octop.infra.agents.middleware.thread_artifacts import artifacts_for_response
from octop.infra.agents.thread_fork import fork_dashboard_thread
from octop.infra.agents.thread_tasks import read_thread_task_state
from octop.infra.agents.workspace_dir import agent_facing_workspace_dir_from_config
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import pending_hitl_payload
from octop.infra.gateway.threads import ThreadRegistry, thread_row_has_messages
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


def _agent_facing_workspace_dir(server: Any, agent_id: str) -> Path:
    """Agent-visible workspace_dir for artifact path joins (not host root_dir map)."""
    registry = getattr(getattr(server, "app_runtime", None), "agent_registry", None)
    if registry is not None and hasattr(registry, "get_config"):
        facing = agent_facing_workspace_dir_from_config(registry.get_config(agent_id))
        if facing:
            return Path(facing)
    return resolve_agent_workspace_dir(server, agent_id)


def _require_thread(
    server: Any, agent_id: str, thread_id: str, user: Any, as_user: int | None
) -> Any:
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    row = server.app_runtime.gateway.thread_registry.get_thread(thread_id)
    if row is None or row.agent_id != agent_id:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
    effective_uid = as_user if as_user is not None else user.id
    if row.user_id != effective_uid:
        raise OctopError(ErrorCode.FORBIDDEN, "thread not owned by user")
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
    effective_uid = as_user if as_user is not None else user.id
    rows = thread_registry.list_threads(agent_id=agent_id, user_id=effective_uid, limit=limit)
    bound = thread_registry.get_bound_thread_id(
        ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=effective_uid)
    )
    workspace_dir = _agent_facing_workspace_dir(server, agent_id)
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
            "model_ref": r.model_ref,
            "reasoning_mode": r.reasoning_mode,
            "reasoning_effort": r.reasoning_effort,
            "artifacts": artifacts_for_response(r.artifacts, workspace_dir),
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
        channel_subject_id=str(effective_uid),
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
    effective_max = registry.resolve_context_max_tokens(agent_id, fallback=max_tokens)
    breakdown = await compute_context_breakdown(
        registry,
        agent_id=agent_id,
        thread_id=thread_id,
        max_tokens=effective_max,
        input_tokens=input_tokens,
        mcp_servers=_parse_csv_query(mcp_servers),
        skills=_parse_csv_query(skills),
        usage_repo=server.services.usage_repo,
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
    """Return recent messages for a thread, including tool calls and thinking blocks.

    ``turn_active`` reports whether a turn is still streaming server-side, so a
    client that reloaded (or navigated away) can re-subscribe over the chat
    WebSocket instead of inferring liveness from the message list.
    """
    row = _require_thread(server, agent_id, thread_id, user, as_user)
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
    effective_uid = as_user if as_user is not None else user.id
    hitl_pending = pending_hitl_payload(
        server.app_runtime.gateway.processor.hitl_coordinator.store,
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=effective_uid,
    )
    workspace_dir = _agent_facing_workspace_dir(server, agent_id)
    task_state = await read_thread_task_state(
        server.app_runtime.agent_registry, agent_id, thread_id
    )
    return {
        "thread_id": thread_id,
        "messages": messages,
        "has_more": has_more,
        "limit": page_limit,
        "offset": page_offset,
        "turn_active": server.app_runtime.gateway.ws_hub.is_turn_active(thread_id),
        "hitl_pending": hitl_pending,
        "artifacts": artifacts_for_response(row.artifacts, workspace_dir),
        "task_state": task_state,
    }


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/task-state",
    summary="Current thread task plan",
)
async def get_thread_task_state(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the authoritative task projection from the thread checkpoint."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    return await read_thread_task_state(server.app_runtime.agent_registry, agent_id, thread_id)


@router.get("/agents/{agent_id}/thread-tasks", summary="List thread task plans")
async def list_thread_tasks(
    agent_id: str,
    status: Literal["active", "completed", "all"] = "all",
    limit: int = 50,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List non-empty task plans for this user's recent agent threads."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    effective_uid = as_user if as_user is not None else user.id
    rows = server.app_runtime.gateway.thread_registry.list_threads(
        agent_id=agent_id,
        user_id=effective_uid,
        limit=max(1, min(limit, 100)),
    )
    task_states = await asyncio.gather(
        *(
            read_thread_task_state(server.app_runtime.agent_registry, agent_id, row.thread_id)
            for row in rows
        )
    )
    output: list[dict[str, Any]] = []
    for row, task_state in zip(rows, task_states, strict=True):
        if task_state["status"] == "idle":
            continue
        if status != "all" and task_state["status"] != status:
            continue
        output.append(
            {
                **task_state,
                "agent_id": agent_id,
                "title": row.title,
                "last_active": row.last_active,
                "created_at": row.created_at,
                "turn_active": server.app_runtime.gateway.ws_hub.is_turn_active(row.thread_id),
                "turn_started_at": server.app_runtime.gateway.ws_hub.turn_started_at(row.thread_id),
            }
        )
    return output


@router.post(
    "/agents/{agent_id}/threads/{thread_id}/cancel",
    summary="Cancel active thread turn",
)
async def cancel_thread_turn(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Cancel the live harness stream for an owned thread, when one exists."""
    _require_thread(server, agent_id, thread_id, user, as_user)
    active = server.app_runtime.gateway.ws_hub.is_turn_active(thread_id)
    if active:
        server.app_runtime.agent_registry.cancel_stream(agent_id, thread_id)
    return {"thread_id": thread_id, "cancelled": active}


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


@router.post(
    "/agents/{agent_id}/threads/{thread_id}/fork",
    status_code=201,
    summary="Fork thread from an assistant message",
)
async def fork_thread(
    agent_id: str,
    thread_id: str,
    body: ForkThreadBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a new dashboard thread with history through *message_id*.

    The original thread is left unchanged. History includes the selected
    assistant reply so the user can continue from that point.
    """
    if not (body.message_id or "").strip() and body.assistant_turns_from_end is None:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "message_id or assistant_turns_from_end is required",
        )
    row = _require_thread(server, agent_id, thread_id, user, as_user)
    effective_uid = as_user if as_user is not None else user.id
    harness = server.app_runtime.agent_registry.get_agent(agent_id)
    return await fork_dashboard_thread(
        thread_registry=server.app_runtime.gateway.thread_registry,
        harness=harness,
        source=row,
        user_id=effective_uid,
        message_id=body.message_id,
        content=body.content,
        assistant_turns_from_end=body.assistant_turns_from_end,
        locale=resolve_request_locale(request),
    )


@router.patch("/agents/{agent_id}/session", summary="Rebind dashboard session")
async def rebind_session(
    agent_id: str,
    body: RebindSessionBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Point the user's dashboard session at an existing thread."""
    _require_thread(server, agent_id, body.thread_id, user, as_user=None)
    sk = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user.id)
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
    """Update sidebar metadata or sticky composer settings for a thread."""
    row = _require_thread(server, agent_id, thread_id, user, as_user)
    composer_fields = {"model_ref", "reasoning_mode", "reasoning_effort"}
    if (
        body.title is None
        and body.pinned is None
        and not body.model_fields_set.intersection(composer_fields)
    ):
        return {
            "thread_id": thread_id,
            "title": row.title,
            "pinned": row.pinned,
            "model_ref": row.model_ref,
            "reasoning_mode": row.reasoning_mode,
            "reasoning_effort": row.reasoning_effort,
        }
    registry = server.app_runtime.gateway.thread_registry
    if body.title is not None:
        registry.update_title(thread_id, body.title)
    if body.pinned is not None:
        registry.set_pinned(thread_id, body.pinned)
    model_ref: str | None | object = ...
    reasoning_mode: str | None | object = ...
    reasoning_effort: str | None | object = ...
    if "model_ref" in body.model_fields_set:
        model_ref = (body.model_ref or "").strip() or None
        if (
            model_ref is not None
            and not server.app_runtime.agent_registry.providers.is_model_ref_usable(model_ref)
        ):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "model_ref must reference an enabled model",
            )
    if "reasoning_mode" in body.model_fields_set:
        reasoning_mode = body.reasoning_mode
    if "reasoning_effort" in body.model_fields_set:
        reasoning_effort = (body.reasoning_effort or "").strip().lower() or None
    registry.update_composer(
        thread_id,
        model_ref=model_ref,
        reasoning_mode=reasoning_mode,
        reasoning_effort=reasoning_effort,
    )
    updated = registry.get_thread(thread_id)
    assert updated is not None
    return {
        "thread_id": thread_id,
        "title": updated.title,
        "pinned": updated.pinned,
        "model_ref": updated.model_ref,
        "reasoning_mode": updated.reasoning_mode,
        "reasoning_effort": updated.reasoning_effort,
    }


@router.delete("/agents/{agent_id}/threads/{thread_id}", status_code=204, summary="Delete thread")
async def delete_thread(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Remove a conversation thread, its actual checkpoint data, and its metadata.

    Checkpoint deletion runs first: if it fails (as opposed to simply
    finding nothing to delete — agent not running / no checkpointer),
    the row is intentionally left in place so the thread stays visible
    and the caller can retry, instead of orphaning undeleted data with
    no remaining handle to it.
    """
    _require_thread(server, agent_id, thread_id, user, as_user)
    await server.app_runtime.agent_registry.delete_thread_checkpoint(agent_id, thread_id)
    server.app_runtime.gateway.thread_registry.delete_thread(thread_id)
