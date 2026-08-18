"""Dashboard chat helpers: polish prompt and HITL resume (SSE)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from octop.api.common.agent import assert_agent_access
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import HitlResumeBody, PolishBody, UserQuestionAnswerBody
from octop.api.routers.chat.sse import format_sse
from octop.i18n import tr
from octop.i18n.domains.stream import format_stream_error
from octop.infra.agents.experts.catalog import (
    default_welcome_payload,
    read_workspace_manifest_welcome,
    welcome_payload_from_expert,
    welcome_payload_has_content,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator, HitlStreamContext
from octop.infra.gateway.hitl.store import HitlPendingRecord
from octop.infra.gateway.questions.coordinator import (
    UserQuestionCoordinator,
    is_user_question_request,
    validate_answers,
)
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
    1. Agent workspace ``manifest.json`` (seeded at create; instance-owned).
    2. Bundled expert catalog entry for ``template_name`` (legacy agents).
    3. Default quick cards (``general-assistant`` or a small built-in set).
    """
    assert_agent_access(server, agent_id, user)
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    catalog = server.expert_catalog

    workspace = registry.workspace_for_agent(agent_id)
    if workspace is not None:
        payload = await read_workspace_manifest_welcome(workspace)
        if payload is not None:
            return payload

    row = registry.get_row(agent_id)
    template = (row.template_name if row else None) or ""
    if catalog is not None and template:
        expert = catalog.get(template)
        if expert is not None:
            payload = welcome_payload_from_expert(expert)
            if welcome_payload_has_content(payload):
                return payload

    return default_welcome_payload(catalog)


async def iter_dashboard_hitl_resume_sse(
    *,
    agent_registry: Any,
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
    question_coordinator: UserQuestionCoordinator | None = None,
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
    try:
        async for chunk in agent_registry.resume_hitl(agent_id, thread_id, decisions):
            if await is_disconnected():
                break
            if isinstance(chunk, dict) and chunk.get("type") == "hitl_required":
                request_payload = chunk.get("request")
                if isinstance(request_payload, dict):
                    if (
                        is_user_question_request(request_payload)
                        and question_coordinator is not None
                    ):
                        record = question_coordinator.register_from_request(
                            request_payload,
                            thread_id=thread_id,
                            agent_id=agent_id,
                            user_id=user_id,
                            session_key=session_key,
                            channel_type=channel_type,
                        )
                        chunk = {
                            **chunk,
                            "request": {**request_payload, "pending_id": record.pending_id},
                        }
                    else:
                        hitl_coordinator.register_from_request(request_payload, ctx=hitl_ctx)
            yield format_sse("chunk", chunk)
        if pending is not None:
            hitl_coordinator.store.mark_resolved(
                pending.pending_id,
                "rejected" if rejected else "approved",
            )
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
    agent_registry = server.app_runtime.agent_registry
    hitl_coordinator = server.app_runtime.gateway.processor.hitl_coordinator
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

    async def gen() -> AsyncIterator[str]:
        async for frame in iter_dashboard_hitl_resume_sse(
            agent_registry=agent_registry,
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
            question_coordinator=server.app_runtime.gateway.question_coordinator,
        ):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post(
    "/agents/{agent_id}/chat/questions/{pending_id}/answer",
    summary="Answer a pending agent question (SSE)",
)
async def answer_user_question(
    agent_id: str,
    pending_id: str,
    body: UserQuestionAnswerBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Resume a durable ``ask_user_question`` interrupt and stream the result."""
    assert_agent_access(server, agent_id, user)
    coordinator = server.app_runtime.gateway.question_coordinator
    row = coordinator.repo.get(pending_id)
    if (
        row is None
        or row.status != "pending"
        or row.agent_id != agent_id
        or row.user_id != user.id
        or row.thread_id != body.thread_id
    ):
        raise OctopError(ErrorCode.FORBIDDEN, "pending question is unavailable")
    try:
        answers = validate_answers(row, body.answers)
    except ValueError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc

    async def gen() -> AsyncIterator[str]:
        if not coordinator.repo.claim(pending_id, agent_id=agent_id, user_id=user.id):
            yield format_sse(
                "chunk",
                {
                    "type": "error",
                    "message": tr("slash.questions.none_pending", resolve_request_locale(request)),
                },
            )
            return
        completed = False
        try:
            hitl = server.app_runtime.gateway.processor.hitl_coordinator
            hitl_ctx = HitlStreamContext(
                thread_id=row.thread_id,
                agent_id=row.agent_id,
                user_id=row.user_id,
                session_key=row.session_key,
                channel_type=row.channel_type,
            )
            async for chunk in server.app_runtime.agent_registry.resume_hitl(
                agent_id,
                row.thread_id,
                [{"type": "answer", "answers": answers}],
            ):
                if await request.is_disconnected():
                    return
                if isinstance(chunk, dict) and chunk.get("type") == "hitl_required":
                    nested = chunk.get("request")
                    if isinstance(nested, dict):
                        if is_user_question_request(nested):
                            nested_row = coordinator.register_from_request(
                                nested,
                                thread_id=row.thread_id,
                                agent_id=row.agent_id,
                                user_id=row.user_id,
                                session_key=row.session_key,
                                channel_type=row.channel_type,
                            )
                            chunk = {
                                **chunk,
                                "request": {**nested, "pending_id": nested_row.pending_id},
                            }
                        else:
                            hitl.register_from_request(nested, ctx=hitl_ctx)
                yield format_sse("chunk", chunk)
            coordinator.repo.mark_answered(pending_id, answers)
            completed = True
            yield format_sse("chunk", {"type": "done"})
        except Exception as exc:
            yield format_sse(
                "chunk",
                {
                    "type": "error",
                    "message": format_stream_error(exc, resolve_request_locale(request)),
                },
            )
        finally:
            if not completed:
                coordinator.repo.release(pending_id)

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
