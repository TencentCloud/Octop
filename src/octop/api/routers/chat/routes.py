"""Dashboard chat helpers: polish prompt and HITL resume (SSE)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from octop.api.common.agent import assert_agent_access
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import HitlResumeBody, PolishBody
from octop.api.routers.chat.sse import format_sse
from octop.i18n.domains.stream import format_stream_error
from octop.infra.agents.experts.catalog import (
    default_welcome_payload,
    read_workspace_manifest_welcome,
)
from octop.infra.agents.profile import welcome_from_row
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlStreamContext,
    decision_rejection_reason,
)
from octop.infra.gateway.hitl.store import HitlPendingRecord
from octop.infra.utils.llm_text import ainvoke_text
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()
logger = logging.getLogger(__name__)

_POLISH_SYSTEM_PROMPT = (
    "You are a prompt editor, not an assistant that answers questions.\n"
    "The user message is a DRAFT PROMPT they will later send to another AI. "
    "Your only job is to rewrite that draft so another AI can understand it more "
    "clearly — improve clarity, specificity, structure, and actionable detail.\n"
    "Hard rules:\n"
    "- Do NOT answer the draft, solve the task, or provide the requested content.\n"
    "- Do NOT add explanations, greetings, or meta commentary.\n"
    "- Preserve the user's original intent and language (e.g. keep Chinese if the "
    "draft is Chinese).\n"
    "- Output ONLY the rewritten prompt text — no preamble, labels, quotes, "
    "thinking blocks, or XML tags."
)


@router.get("/agents/{agent_id}/chat/welcome", summary="Chat welcome quick cards")
async def get_chat_welcome(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Welcome copy for the empty chat screen.

    Resolution order:
    1. Agent row ``welcome_message`` (instance-owned; set at create/edit).
    2. Agent workspace ``.octop/manifest.json`` (seeded at create; quick cards + fallback copy).
    3. Default quick cards (``general-assistant`` or a small built-in set).
    """
    assert_agent_access(server, agent_id, user)
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    catalog = server.expert_catalog

    workspace = registry.workspace_for_agent(agent_id)
    payload: dict[str, Any] | None = None
    if workspace is not None:
        payload = await read_workspace_manifest_welcome(workspace)

    row = registry.get_row(agent_id)
    if payload is None:
        payload = default_welcome_payload(catalog)

    db_welcome = welcome_from_row(row) if row is not None else None
    if db_welcome is not None:
        payload = {**payload, "welcome_message": {"zh": db_welcome, "en": db_welcome}}
    return payload


async def iter_dashboard_hitl_resume_sse(
    *,
    processor: Any,
    hitl_coordinator: HitlChannelCoordinator,
    agent_id: str,
    thread_id: str,
    user_id: int,
    decisions: list[dict[str, Any]],
    pending: HitlPendingRecord | None,
    session_key: str,
    channel_type: str,
    locale: str,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """Stream dashboard HITL resume chunks and persist any nested ``hitl_required``.

    Follow-up interrupts during resume must land in the pending store so history
    reload / refresh can reinject the approval card (same as the initial turn).
    """
    rejected = any(isinstance(d, dict) and d.get("type") == "reject" for d in decisions)
    hitl_ctx = HitlStreamContext(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        session_key=session_key,
        channel_type=channel_type,
    )
    disconnected = False
    try:
        async for chunk in processor.iter_hitl_resume_chunks(
            agent_id=agent_id,
            thread_id=thread_id,
            user_id=user_id,
            decisions=decisions,
        ):
            if not disconnected:
                disconnected = await is_disconnected()
            if isinstance(chunk, dict) and chunk.get("type") == "hitl_required":
                request_payload = chunk.get("request")
                if isinstance(request_payload, dict):
                    hitl_coordinator.register_from_request(request_payload, ctx=hitl_ctx)
            if not disconnected:
                yield format_sse("chunk", chunk)
        if pending is not None:
            hitl_coordinator.store.mark_resolved(
                pending.pending_id,
                "rejected" if rejected else "approved",
            )
        if not disconnected:
            yield format_sse("chunk", {"type": "done"})
    except Exception as exc:
        yield format_sse(
            "chunk",
            {"type": "error", "message": format_stream_error(exc, locale)},
        )


def _dashboard_hitl_stream_context(
    server: Any,
    *,
    agent_id: str,
    thread_id: str,
    user_id: int,
    pending: HitlPendingRecord | None,
) -> tuple[str, str]:
    if pending is not None:
        return pending.session_key, pending.channel_type
    row = server.app_runtime.gateway.thread_registry.get_thread(thread_id)
    if row is not None:
        return row.session_key, row.channel_type or "dashboard"
    return f"{agent_id}:dashboard:{user_id}:dm", "dashboard"


@router.post("/agents/{agent_id}/chat/hitl/resume", summary="Resume HITL approval (SSE)")
async def resume_hitl(
    agent_id: str,
    body: HitlResumeBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Resume a paused human-in-the-loop tool approval and stream subsequent chunks."""
    assert_agent_access(server, agent_id, user)
    processor = server.app_runtime.gateway.processor
    hitl_coordinator = processor.hitl_coordinator
    pending = hitl_coordinator.store.resolve_pending_for_thread(
        body.thread_id,
        agent_id=agent_id,
        user_id=user.id,
    )
    session_key, channel_type = _dashboard_hitl_stream_context(
        server,
        agent_id=agent_id,
        thread_id=body.thread_id,
        user_id=user.id,
        pending=pending,
    )
    if pending is not None:
        reason = decision_rejection_reason(pending, body.decisions)
        if reason is not None:
            raise HTTPException(status_code=400, detail=reason)

    async def gen() -> AsyncIterator[str]:
        async for frame in iter_dashboard_hitl_resume_sse(
            processor=processor,
            hitl_coordinator=hitl_coordinator,
            agent_id=agent_id,
            thread_id=body.thread_id,
            user_id=user.id,
            decisions=body.decisions,
            pending=pending,
            session_key=session_key,
            channel_type=channel_type,
            locale=resolve_request_locale(request),
            is_disconnected=request.is_disconnected,
        ):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/agents/{agent_id}/chat/polish", summary="Polish prompt")
async def polish_prompt(
    agent_id: str,
    body: PolishBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """One-shot prompt refinement without touching thread history."""
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    assert_agent_access(server, agent_id, user)

    draft = body.text.strip()
    if not draft:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "text is required")

    harness = server.app_runtime.agent_registry.get_agent(agent_id)
    model_ref = (body.default_model or "").strip() or harness.config.pick_default_model_ref()
    llm = harness.model_factory.get(model_ref)
    try:
        polished = await ainvoke_text(
            llm,
            [
                SystemMessage(content=_POLISH_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        "Rewrite the following draft prompt. Do not answer it.\n\n"
                        f"---\n{draft}\n---"
                    ),
                ),
            ],
            timeout=30.0,
        )
    except TimeoutError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "polish request timed out") from None
    except Exception as exc:
        logger.exception("polish failed agent=%s model=%s", agent_id, model_ref)
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc

    if not polished:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "model returned empty polish result")
    return {"text": polished}
