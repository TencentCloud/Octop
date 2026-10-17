"""Dashboard chat helpers: polish prompt and HITL resume (SSE)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from octop.api.common.agent import (
    agent_is_shared,
    assert_agent_access,
    require_agent_owner_row,
    user_owns_agent,
)
from octop.api.common.workspace import require_running_workspace
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import HitlResumeBody, PolishBody, SecretFileSubmitBody
from octop.api.routers.chat.sse import format_sse
from octop.i18n.domains.secret import secret_cancelled_message, secret_filled_message
from octop.i18n.domains.stream import format_stream_error
from octop.infra.agents.experts.catalog import (
    default_welcome_payload,
    display_task_examples_for_agent,
    parse_task_examples,
    read_workspace_manifest_data,
    welcome_payload_from_manifest_data,
    welcome_payload_has_content,
)
from octop.infra.agents.secret_file import (
    is_secret_action_requests,
    maybe_annotate_secret_payload,
    secret_request_args,
    submit_secret_content,
)
from octop.infra.agents.settings.profile import welcome_from_row
from octop.infra.agents.teams import is_team_agent
from octop.infra.agents.teams.welcome import team_host_welcome_payload
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlStreamContext,
    decision_rejection_reason,
)
from octop.infra.gateway.hitl.format import normalize_hitl_request
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

    Team hosts keep the team intro and show members' own quick cards — the host
    is not turned into cards.
    """
    assert_agent_access(server, agent_id, user)
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    catalog = server.expert_catalog
    row = registry.get_row(agent_id)
    if is_team_agent(row):
        team_payload = await team_host_welcome_payload(row, registry, catalog)
        return {**team_payload, "task_examples": None}

    workspace = registry.workspace_for_agent(agent_id)
    payload: dict[str, Any] | None = None
    parsed_examples = None
    if workspace is not None:
        manifest = await read_workspace_manifest_data(workspace)
        if manifest is not None:
            welcome = welcome_payload_from_manifest_data(manifest)
            if welcome_payload_has_content(welcome):
                payload = welcome
            parsed_examples = parse_task_examples(manifest)

    if payload is None:
        payload = default_welcome_payload(catalog)

    db_welcome = welcome_from_row(row) if row is not None else None
    if db_welcome is not None:
        payload = {**payload, "welcome_message": {"zh": db_welcome, "en": db_welcome}}
    task_examples = display_task_examples_for_agent(
        parsed=parsed_examples,
        catalog=catalog,
        row=row,
    )
    return {**payload, "task_examples": task_examples}


async def iter_dashboard_hitl_resume_sse(
    *,
    server: Any,
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
    secret_workspace: Any | None = None,
) -> AsyncIterator[str]:
    """Stream dashboard HITL resume chunks and persist any nested ``hitl_required``.

    Follow-up interrupts during resume must land in the pending store so history
    reload / refresh can reinject the approval card (same as the initial turn).
    """
    rejected = any(isinstance(d, dict) and d.get("type") == "reject" for d in decisions)
    if pending is not None and pending.resume_agent_id:
        from octop.i18n.domains.slash import tr as slash_tr  # noqa: PLC0415
        from octop.infra.utils.locale import normalize_locale  # noqa: PLC0415

        teams = getattr(processor, "teams", None)
        deliver = getattr(teams, "deliver_member_hitl", None) if teams is not None else None
        handed = hitl_coordinator.hand_member_pause(
            pending,
            decisions,
            deliver=deliver if callable(deliver) else None,
            rejected=rejected,
        )
        if handed:
            # The member job keeps streaming on the room socket. A normal
            # ``done`` makes the dashboard reload history immediately, which
            # drops the live member answer before fan-in has saved it.
            yield format_sse(
                "chunk",
                {"type": "done", "team_member_continuing": True},
            )
            return
        yield format_sse(
            "chunk",
            {"type": "error", "message": slash_tr("hitl.expired", normalize_locale(locale))},
        )
        return
    hitl_ctx = HitlStreamContext(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        session_key=session_key,
        channel_type=channel_type,
    )
    disconnected = False
    followup_pause = False
    # Clear the in-memory pause before the (possibly long) resume stream so
    # history reload cannot reinject the same card while the turn continues.
    if pending is not None:
        hitl_coordinator.store.mark_resolved(
            pending.pending_id,
            "rejected" if rejected else "approved",
        )
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
                followup_pause = True
                request_payload = chunk.get("request")
                if isinstance(request_payload, dict):
                    request_payload = normalize_hitl_request(request_payload)
                    await maybe_annotate_secret_payload(request_payload, secret_workspace)
                    record = hitl_coordinator.register_from_request(request_payload, ctx=hitl_ctx)
                    request_payload["pending_id"] = record.pending_id
                    chunk["request"] = request_payload
            if not disconnected:
                yield format_sse("chunk", chunk)
        # A new approval card is still pending. Draining now would start a
        # turn that expires that card. Keep the queue until a resume finishes
        # without another pause. A plain ``done`` would also make the
        # dashboard flush locally queued messages and reload history.
        if followup_pause:
            if not disconnected:
                yield format_sse("chunk", {"type": "done", "hitl_paused": True})
            return
        if not disconnected:
            yield format_sse("chunk", {"type": "done"})
        # Steers parked across the HITL pause drain at this
        # boundary and continue through a normal WS turn — also when the SSE
        # client disconnected, because the resume itself completed here.
        from octop.infra.gateway.ws.ws_channel import resume_parked_steers  # noqa: PLC0415

        try:
            await resume_parked_steers(
                server,
                agent_id=agent_id,
                thread_id=thread_id,
                session_key=session_key,
                channel_type=channel_type,
                user_id=user_id,
            )
        except Exception:
            logging.getLogger(__name__).exception("steer resume drain failed thread=%s", thread_id)
    except Exception as exc:
        # Resume failed after we cleared the pause for reinject safety — do not
        # leave the record looking like a successful approve/reject.
        if pending is not None:
            hitl_coordinator.store.mark_resolved(pending.pending_id, "expired")
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
    requested_id = (body.pending_id or "").strip()
    pending = hitl_coordinator.store.resolve_pending_for_thread(
        body.thread_id,
        agent_id=agent_id,
        user_id=user.id,
        pending_id=requested_id or None,
    )
    if requested_id and pending is None:
        from octop.i18n.domains.slash import tr as slash_tr  # noqa: PLC0415
        from octop.infra.utils.locale import normalize_locale  # noqa: PLC0415

        locale = normalize_locale(resolve_request_locale(request))

        async def missing() -> AsyncIterator[str]:
            yield format_sse(
                "chunk",
                {"type": "error", "message": slash_tr("hitl.expired", locale)},
            )

        return StreamingResponse(missing(), media_type="text/event-stream")
    if pending is not None and is_secret_action_requests(pending.action_requests):
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            "credential cards require the dedicated secret-file endpoint",
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

    if body.hitl_policy is not None:
        hitl_coordinator.session_policies.set(body.thread_id, body.hitl_policy.model_dump())

    assert server.app_runtime is not None
    secret_workspace = server.app_runtime.agent_registry.workspace_for_agent(agent_id)

    async def gen() -> AsyncIterator[str]:
        async for frame in iter_dashboard_hitl_resume_sse(
            server=server,
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
            secret_workspace=secret_workspace,
        ):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post(
    "/agents/{agent_id}/chat/secret-file/submit",
    summary="Submit a credential file for a secret card (SSE)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Resumed turn events; credential contents are never returned.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
    },
)
async def submit_secret_file(
    agent_id: str,
    body: SecretFileSubmitBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Store the user's credential text and resume the paused turn.

    The target path comes from the pending ``request_secret_file`` record —
    the client cannot redirect the write to another path, agent or user.
    First version only serves the owner's own non-shared experts. The secret
    itself is never logged, echoed, or returned; responses and history carry
    metadata only. On write failure the pause reopens so the user can retry;
    the previous file is left untouched. Streams the resumed turn as SSE.
    """
    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    if not user_owns_agent(row, user) or agent_is_shared(row):
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "personal credentials require an owned, non-shared expert",
        )
    assert server.app_runtime is not None
    processor = server.app_runtime.gateway.processor
    hitl_coordinator: HitlChannelCoordinator = processor.hitl_coordinator
    store = hitl_coordinator.store

    record = store.get(body.pending_id)
    if (
        record is None
        or record.status != "pending"
        or record.agent_id != agent_id
        or record.user_id != user.id
        or record.thread_id != body.thread_id
        or not is_secret_action_requests(record.action_requests)
    ):
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            "secret request is stale, cancelled, or does not belong to this chat",
        )
    args = secret_request_args(record.action_requests) or {}
    raw_path = args.get("path")

    locale = resolve_request_locale(request)
    action_count = len(record.action_requests) or 1

    if body.action == "cancel":
        if store.claim_secret(body.pending_id) is None:
            raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "secret request already handled")
        store.mark_resolved(body.pending_id, "cancelled")
        decisions = [
            {"type": "respond", "message": secret_cancelled_message(locale)}
            for _ in range(action_count)
        ]
    else:
        if len(record.action_requests) != 1:
            raise OctopError(
                ErrorCode.SECRET_REQUEST_INVALID,
                "secret submissions require exactly one action request",
            )
        # Acquire the workspace BEFORE claiming the pending record: a stopped
        # agent raises here and must leave the request pending for retry.
        workspace = await require_running_workspace(
            agent_id,
            user=user,
            as_user=None,
            server=server,
            owner_only=True,
        )
        if store.claim_secret(body.pending_id) is None:
            raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "secret request already handled")
        try:
            display_path = await submit_secret_content(
                workspace,
                raw_path=raw_path,
                content=body.content,
            )
        except OctopError:
            store.reopen_secret(body.pending_id)
            raise
        except Exception:
            store.reopen_secret(body.pending_id)
            # Never log the payload; metadata only.
            logger.error(
                "secret-file write failed agent=%s pending=%s",
                agent_id,
                body.pending_id,
            )
            raise OctopError(
                ErrorCode.SECRET_WRITE_FAILED,
                "failed to store the credential file",
            ) from None
        store.mark_resolved(body.pending_id, "filled")
        decisions = [
            {"type": "respond", "message": secret_filled_message(display_path, locale)}
            for _ in range(action_count)
        ]

    secret_workspace = server.app_runtime.agent_registry.workspace_for_agent(agent_id)

    async def gen() -> AsyncIterator[str]:
        async for frame in iter_dashboard_hitl_resume_sse(
            server=server,
            processor=processor,
            hitl_coordinator=hitl_coordinator,
            agent_id=agent_id,
            thread_id=body.thread_id,
            user_id=user.id,
            decisions=decisions,
            pending=None,  # already resolved above — no double marking
            session_key=record.session_key,
            channel_type=record.channel_type,
            locale=locale,
            is_disconnected=request.is_disconnected,
            secret_workspace=secret_workspace,
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
    except Exception:
        logger.exception("polish failed agent=%s model=%s", agent_id, model_ref)
        raise OctopError(ErrorCode.INTERNAL_ERROR, "polish request failed") from None

    if not polished:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "model returned empty polish result")
    return {"text": polished}
