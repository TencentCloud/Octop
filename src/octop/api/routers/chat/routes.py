"""Dashboard chat helpers: polish prompt and HITL resume (SSE)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from octop.api.common.agent import agent_is_shared, assert_agent_access, require_agent_owner_row
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import HitlResumeBody, PolishBody, SecretInputSubmitBody
from octop.api.routers.chat.sse import format_sse
from octop.i18n.domains.stream import format_stream_error
from octop.infra.agents.experts.catalog import (
    default_welcome_payload,
    display_task_examples_for_agent,
    parse_task_examples,
    read_workspace_manifest_data,
    welcome_payload_from_manifest_data,
    welcome_payload_has_content,
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
from octop.infra.gateway.hitl.format import (
    extract_secret_input_request,
    is_secret_input_action_requests,
    normalize_hitl_request,
)
from octop.infra.gateway.hitl.store import HitlPendingRecord
from octop.infra.text_assist import require_host_models, run_text_assist
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()
logger = logging.getLogger(__name__)


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
    session_key, channel_type = _dashboard_hitl_stream_context(
        server,
        agent_id=agent_id,
        thread_id=body.thread_id,
        user_id=user.id,
        pending=pending,
    )
    if pending is not None and is_secret_input_action_requests(pending.action_requests):
        # A secret must never ride the generic respond path (its message
        # becomes the tool result and enters the model context verbatim).
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            "secret input requests are submitted via /chat/secret-input/submit",
        )
    if pending is not None:
        reason = decision_rejection_reason(pending, body.decisions)
        if reason is not None:
            raise HTTPException(status_code=400, detail=reason)

    if body.hitl_policy is not None:
        hitl_coordinator.session_policies.set(body.thread_id, body.hitl_policy.model_dump())

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
        ):
            yield frame

    return StreamingResponse(gen(), media_type="text/event-stream")


def _secret_input_decisions(
    record: HitlPendingRecord,
    *,
    message: str,
) -> list[dict[str, Any]]:
    count = len(record.action_requests) or 1
    return [{"type": "respond", "message": message} for _ in range(count)]


def _secret_filled_message(slot: str) -> str:
    return (
        f"The user securely stored a secret in slot {slot} (status=filled). "
        f"Its value is never shown to you. It is injected as the environment "
        f"variable {slot} for the commands you execute from your next turn. "
        "Do not ask the user to reveal the value in chat, and never print or "
        "echo the variable's content."
    )


def _secret_cancelled_message(slot: str) -> str:
    return (
        f"The user dismissed the secret input for slot {slot} (status=cancelled). "
        "Do not call request_secret_input for this slot again during this turn; "
        "ask the user how to proceed instead."
    )


@router.post(
    "/agents/{agent_id}/chat/secret-input/submit",
    summary="Submit a chat secret input (SSE)",
)
async def submit_secret_input(
    agent_id: str,
    body: SecretInputSubmitBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Store a masked-input secret (or cancel the card) and resume the paused turn.

    The value travels exactly once through this endpoint into the encrypted
    ``agent_secrets`` store. It never appears in chat history, thread records,
    logs, or the resumed tool result — the model only learns the slot name and
    status. Owner-only, non-shared agents.
    """
    row = require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    if agent_is_shared(row):
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "secret input is disabled for shared agents",
        )
    processor = server.app_runtime.gateway.processor
    hitl_coordinator = processor.hitl_coordinator
    record = hitl_coordinator.store.resolve_pending_for_thread(
        body.thread_id,
        agent_id=agent_id,
        user_id=user.id,
        pending_id=body.pending_id,
    )
    if record is None or not is_secret_input_action_requests(record.action_requests):
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "no pending secret input request")
    request_meta = extract_secret_input_request(record.action_requests) or {}
    slot = str(request_meta.get("slot") or "")
    if body.action == "submit" and (len(record.action_requests) != 1 or not slot.strip()):
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            "mixed secret pause can only be cancelled",
        )
    claimed = hitl_coordinator.store.claim_secret_input(record.pending_id)
    if claimed is None:
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "secret input already handled")

    decisions: list[dict[str, Any]]
    if body.action == "cancel":
        hitl_coordinator.store.mark_resolved(record.pending_id, "cancelled")
        decisions = _secret_input_decisions(record, message=_secret_cancelled_message(slot or "—"))
    else:
        registry = server.app_runtime.agent_registry
        try:
            registry.agent_secrets.store_slot(
                agent_id=agent_id,
                user_id=user.id,
                slot_name=slot,
                value=body.value or "",
                display_name=str(request_meta.get("title") or slot),
            )
        except OctopError:
            hitl_coordinator.store.reopen_secret_input(record.pending_id)
            raise
        except Exception:
            logger.exception(
                "secret input submit failed agent=%s pending_id=%s", agent_id, record.pending_id
            )
            hitl_coordinator.store.reopen_secret_input(record.pending_id)
            raise OctopError(
                ErrorCode.SECRET_WRITE_FAILED,
                "failed to persist the secret slot",
            ) from None
        hitl_coordinator.store.mark_resolved(record.pending_id, "filled")
        decisions = _secret_input_decisions(record, message=_secret_filled_message(slot))

    session_key, channel_type = _dashboard_hitl_stream_context(
        server,
        agent_id=agent_id,
        thread_id=body.thread_id,
        user_id=user.id,
        pending=record,
    )

    async def gen() -> AsyncIterator[str]:
        try:
            async for frame in iter_dashboard_hitl_resume_sse(
                server=server,
                processor=processor,
                hitl_coordinator=hitl_coordinator,
                agent_id=agent_id,
                thread_id=body.thread_id,
                user_id=user.id,
                decisions=decisions,
                # The record is already resolved (filled/cancelled); passing it
                # would mark it approved/rejected. Follow-up interrupts during
                # the resumed turn still register fresh pendings.
                pending=None,
                session_key=session_key,
                channel_type=channel_type,
                locale=resolve_request_locale(request),
                is_disconnected=request.is_disconnected,
            ):
                yield frame
        finally:
            if body.action == "submit":
                # The harness env overlay is baked at build time; rebuild after
                # the resumed turn settles so the slot reaches command execution.
                server.app_runtime.agent_registry.schedule_reload(agent_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post(
    "/agents/{agent_id}/chat/polish",
    summary="Polish prompt (compat)",
    deprecated=True,
)
async def polish_prompt(
    agent_id: str,
    body: PolishBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """Compat alias for ``POST /api/text/assist`` with ``kind=chat.prompt``."""
    assert_agent_access(server, agent_id, user)
    polished = await run_text_assist(
        models=require_host_models(server),
        kind="chat.prompt",
        text=body.text,
        locale=resolve_request_locale(request),
        default_model=body.default_model,
    )
    return {"text": polished}
