"""Claim → encrypt/store → resolve lifecycle for a secret-input submission.

The dashboard submit endpoint is a thin HTTP wrapper over this module: the
value travels in once, is validated against the pending pause, and either
lands encrypted in ``agent_secrets`` (``submit``) or dismisses the card
(``cancel``). The resumed turn only learns the slot name and a status; the
plaintext value never reaches chat history, model context, or logs.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from octop.infra.agents.secret_input.service import AgentSecretService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.format import (
    extract_secret_input_request,
    is_secret_input_action_requests,
)
from octop.infra.gateway.hitl.store import HitlPendingRecord, HitlPendingStore

logger = logging.getLogger(__name__)


def _secret_input_decisions(record: HitlPendingRecord, *, message: str) -> list[dict[str, Any]]:
    count = len(record.action_requests) or 1
    return [{"type": "respond", "message": message} for _ in range(count)]


def _secret_filled_message(slot: str, *, injected: bool) -> str:
    tail = (
        f"It is already injected as the environment variable {slot} for your "
        "command executions — use it right now and finish the task in this "
        "turn."
        if injected
        else (
            f"The harness rebuild failed, so the environment variable {slot} "
            "reaches your command executions only from your NEXT turn — "
            "finish this turn now and read it then."
        )
    )
    return (
        f"The user securely stored a secret in slot {slot} (status=filled). "
        f"Its value is never shown to you. {tail} Do not ask the user to "
        "reveal the value in chat, and never print or echo the variable's "
        "content."
    )


def _secret_cancelled_message(slot: str) -> str:
    return (
        f"The user dismissed the secret input for slot {slot} (status=cancelled). "
        "Do not call request_secret_input for this slot again during this turn; "
        "ask the user how to proceed instead."
    )


async def resolve_secret_input_submission(
    *,
    store: HitlPendingStore,
    agent_secrets: AgentSecretService,
    agent_id: str,
    user_id: int,
    thread_id: str,
    pending_id: str,
    action: str,
    value: str,
    rebuild: Callable[[str], Awaitable[bool]] | None = None,
) -> tuple[HitlPendingRecord, list[dict[str, Any]]]:
    """Validate and settle one secret-input card submission.

    Returns the claimed pending record (already marked ``filled`` /
    ``cancelled``) plus the respond decisions the paused turn resumes with.
    Raises ``OctopError`` without mutating the pending state when the request
    is invalid, already handled, or the slot cannot be persisted.
    """
    record = store.resolve_pending_for_thread(
        thread_id,
        agent_id=agent_id,
        user_id=user_id,
        pending_id=pending_id,
    )
    if record is None or not is_secret_input_action_requests(record.action_requests):
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "no pending secret input request")
    request_meta = extract_secret_input_request(record.action_requests) or {}
    slot = str(request_meta.get("slot") or "")
    if action == "submit" and (len(record.action_requests) != 1 or not slot.strip()):
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            "mixed secret pause can only be cancelled",
        )
    claimed = store.claim_secret_input(record.pending_id)
    if claimed is None:
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "secret input already handled")

    if action == "cancel":
        store.mark_resolved(record.pending_id, "cancelled")
        return record, _secret_input_decisions(
            record, message=_secret_cancelled_message(slot or "—")
        )

    try:
        agent_secrets.store_slot(
            agent_id=agent_id,
            user_id=user_id,
            slot_name=slot,
            value=value,
            display_name=str(request_meta.get("title") or slot),
        )
    except OctopError:
        store.reopen_secret_input(record.pending_id)
        raise
    except Exception:
        logger.exception(
            "secret input submit failed agent=%s pending_id=%s", agent_id, record.pending_id
        )
        store.reopen_secret_input(record.pending_id)
        raise OctopError(
            ErrorCode.SECRET_WRITE_FAILED,
            "failed to persist the secret slot",
        ) from None
    store.mark_resolved(record.pending_id, "filled")
    # Rebuild before the turn resumes so the slot lands in command env for
    # this same turn; a failed rebuild degrades to next-turn visibility.
    injected = bool(await rebuild(agent_id)) if rebuild is not None else False
    return record, _secret_input_decisions(
        record, message=_secret_filled_message(slot, injected=injected)
    )
