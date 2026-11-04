"""Claim → validate → cross-table write unit → resolve for a secure-form submission.

The dashboard submit endpoint is a thin HTTP wrapper over this module. Values
travel in once, are validated against the REGISTERED schema (never the body's
own declarations), and land in one transaction: env slots (``agent_secrets``),
the vault item (``vault_items``), and the audit row commit or roll back
together. The resumed turn only learns field ids, slot names, statuses, and
the vault item id — never the values.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.secret_input.service import AgentSecretService
from octop.infra.agents.secret_input.slots import AGENT_SECRET_MAX_SLOTS, normalize_slot_name
from octop.infra.agents.secure_form.validation import (
    SECURE_FORM_FIELD_TYPES,
    SECURE_FORM_MAX_FIELD_LENGTH,
    VAULT_ITEM_FIELD_TYPES,
    extract_secure_form_request,
    normalize_secure_form_origin,
)
from octop.infra.agents.secure_form.vault_service import VaultService
from octop.infra.crypto.fernet import PURPOSE_AGENT_SECRET, PURPOSE_VAULT_ITEM, get_fernet
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.format import is_secure_form_action_requests
from octop.infra.gateway.hitl.store import HitlPendingRecord, HitlPendingStore

logger = logging.getLogger(__name__)

# (conn, action, target) — one audit row on the caller-owned unit connection.
# Implementations must log ids/titles only, never blob bytes or values.
AuditWriter = Callable[[Any, str, str], None]

_OTP_RE = re.compile(r"\d{4,8}")
_CARD_NUMBER_RE = re.compile(r"\d{12,19}")
_CARD_EXP_RE = re.compile(r"(\d{2})/(\d{2})")
_CARD_CVV_RE = re.compile(r"\d{3,4}")


@dataclass(frozen=True)
class SecureFormFieldSpec:
    """One registered field, re-derived from the pending record's tool args."""

    id: str
    label: str
    type: str
    required: bool
    max_length: int


@dataclass
class SecureFormSubmissionResult:
    """Terminal state of one submit (or idempotent replay of a lost response)."""

    record: HitlPendingRecord
    decisions: list[dict[str, Any]]
    # Metadata only: action, field ids + statuses, slot names, vault item id,
    # injected flag. Never values.
    summary: dict[str, Any]
    replay: bool = False


def _decisions(record: HitlPendingRecord, *, message: str) -> list[dict[str, Any]]:
    count = len(record.action_requests) or 1
    return [{"type": "respond", "message": message} for _ in range(count)]


def _field_invalid(detail: str, *, field_id: str | None = None) -> OctopError:
    return OctopError(
        ErrorCode.SECURE_FORM_FIELD_INVALID,
        detail,
        details={"field": field_id} if field_id else {},
    )


def _registered_fields(
    record: HitlPendingRecord,
) -> tuple[list[SecureFormFieldSpec], dict[str, Any]]:
    """Registered schema from the pending record — the only trusted source."""
    request = extract_secure_form_request(record.action_requests)
    if not isinstance(request, dict):
        raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "no pending secure form request")
    specs: list[SecureFormFieldSpec] = []
    for raw in request.get("fields") or []:
        if not isinstance(raw, dict):
            raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "corrupt secure form schema")
        field_id = raw.get("id")
        field_type = raw.get("type")
        if not isinstance(field_id, str) or field_type not in SECURE_FORM_FIELD_TYPES:
            raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "corrupt secure form schema")
        raw_max = raw.get("max_length")
        specs.append(
            SecureFormFieldSpec(
                id=field_id,
                label=str(raw.get("label") or field_id),
                type=str(field_type),
                required=bool(raw.get("required", True)),
                max_length=int(raw_max)
                if isinstance(raw_max, int)
                else SECURE_FORM_MAX_FIELD_LENGTH,
            )
        )
    if not specs:
        raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "corrupt secure form schema")
    return specs, request


def _routing(request: Mapping[str, Any]) -> tuple[str, dict[str, str], dict[str, Any] | None]:
    """(kind, field_id -> normalized slot name, vault_meta) from the schema."""
    routing = request.get("routing")
    if not isinstance(routing, dict) or routing.get("kind") not in ("env", "vault"):
        raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "corrupt secure form routing")
    kind = str(routing["kind"])
    slots: dict[str, str] = {}
    raw_slots = routing.get("slots")
    if kind == "env":
        if not isinstance(raw_slots, dict):
            raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "corrupt secure form routing")
        for field_id, raw_slot in raw_slots.items():
            normalized = normalize_slot_name(raw_slot)
            if normalized is None:
                raise OctopError(
                    ErrorCode.SECURE_FORM_SLOT_INVALID,
                    f"registered slot name {raw_slot!r} is invalid or reserved",
                )
            slots[str(field_id)] = normalized
    vault_meta = routing.get("vault_meta")
    if vault_meta is not None and not isinstance(vault_meta, dict):
        raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "corrupt secure form routing")
    return kind, slots, vault_meta


def _check_shape(spec: SecureFormFieldSpec, value: str) -> str:
    """Validate the per-type shape; returns the (possibly normalized) value.

    Values are stored byte-exact; the only explicit normalizations are
    ``card_number`` space strip and ``card_exp`` which is stored as given.
    """

    def bad(detail: str) -> OctopError:
        return _field_invalid(f"field {spec.id!r}: {detail}", field_id=spec.id)

    if spec.type == "otp" and not _OTP_RE.fullmatch(value):
        raise bad("otp must be 4 to 8 digits")
    if spec.type == "card_cvv" and not _CARD_CVV_RE.fullmatch(value):
        raise bad("card security code must be 3 to 4 digits")
    if spec.type == "card_number":
        stripped = value.replace(" ", "")
        if not _CARD_NUMBER_RE.fullmatch(stripped):
            raise bad("card number must be 12 to 19 digits")
        return stripped
    if spec.type == "card_exp":
        match = _CARD_EXP_RE.fullmatch(value)
        if match is None or not 1 <= int(match.group(1)) <= 12:
            raise bad("expiry must be MM/YY with a month of 01-12")
    return value


def _validate_values(specs: list[SecureFormFieldSpec], values: Mapping[str, str]) -> dict[str, str]:
    """Pre-claim validation against the registered schema. Never mutates stored bytes."""
    known = {spec.id for spec in specs}
    unknown = sorted({str(key) for key in values} - known)
    if unknown:
        raise _field_invalid(f"unknown field id(s): {', '.join(unknown)}")
    filled: dict[str, str] = {}
    for spec in specs:
        raw = values.get(spec.id)
        if raw is None or not str(raw).strip():
            if spec.required:
                raise _field_invalid(f"field {spec.id!r} is required", field_id=spec.id)
            continue
        value = str(raw)
        if len(value) > spec.max_length:
            raise _field_invalid(
                f"field {spec.id!r} exceeds {spec.max_length} characters", field_id=spec.id
            )
        filled[spec.id] = _check_shape(spec, value)
    return filled


def _scope_ok(
    record: HitlPendingRecord,
    *,
    thread_id: str | None,
    agent_id: str,
    user_id: int,
) -> bool:
    if record.user_id != user_id:
        return False
    if record.agent_id != agent_id and record.resume_agent_id != agent_id:
        return False
    if thread_id is None:
        return True
    room_match = record.thread_id == thread_id and record.agent_id == agent_id
    member_match = bool(
        record.resume_thread_id
        and record.resume_thread_id == thread_id
        and record.resume_agent_id == agent_id
    )
    return room_match or member_match


def load_secure_form_record(
    store: HitlPendingStore,
    *,
    agent_id: str,
    user_id: int,
    pending_id: str,
    thread_id: str | None = None,
    expired_code: ErrorCode = ErrorCode.SECURE_FORM_PENDING_EXPIRED,
) -> HitlPendingRecord:
    """Fetch one secure-form pending record with owner/scope checks.

    ``expired_code`` selects the failure semantics per surface: GET raises
    ``SECURE_FORM_PENDING_EXPIRED`` (410); submit raises
    ``SECURE_FORM_ALREADY_HANDLED`` (409) for expired/terminal records.
    """
    record = store.get(pending_id)
    if record is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"unknown secure form pending id {pending_id!r}")
    if record.status == "expired":
        raise OctopError(expired_code, "the secure form expired or was replaced by a newer form")
    if not _scope_ok(record, thread_id=thread_id, agent_id=agent_id, user_id=user_id):
        raise OctopError(ErrorCode.NOT_FOUND, "secure form pending does not belong to this scope")
    if not is_secure_form_action_requests(record.action_requests):
        raise OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "no pending secure form request")
    return record


def secure_form_pending_facts(
    store: HitlPendingStore,
    *,
    agent_id: str,
    user_id: int,
    pending_id: str,
    agent_secrets: AgentSecretService,
    vault: VaultService,
) -> dict[str, Any]:
    """Structured GET view: registered schema + banner facts re-derived per call.

    Collision (``existing_vault_item_id``) and slot facts are looked up fresh
    so drift between registration and submit stays visible, and a
    ``VAULT_REPLACE_REQUIRED`` refusal is recoverable. Never includes values.
    """
    record = load_secure_form_record(
        store,
        agent_id=agent_id,
        user_id=user_id,
        pending_id=pending_id,
        expired_code=ErrorCode.SECURE_FORM_PENDING_EXPIRED,
    )
    specs, request = _registered_fields(record)
    kind, slots, vault_meta = _routing(request)
    existing_slots = {row.slot_name for row in agent_secrets.list_slots(agent_id)}
    existing_slot_names = sorted(set(slots.values()) & existing_slots) if slots else []
    existing_vault_item_id: str | None = None
    storable_ids: list[str] = []
    if vault_meta is not None:
        item_type = str(vault_meta.get("item_type"))
        title = str(vault_meta.get("title") or "").strip()
        allowed = VAULT_ITEM_FIELD_TYPES.get(item_type, frozenset())
        storable_ids = [spec.id for spec in specs if spec.type in allowed]
        existing = vault.repo.find_by_title(user_id=user_id, item_type=item_type, title=title)
        existing_vault_item_id = existing.vault_item_id if existing is not None else None
    return {
        "pending_id": record.pending_id,
        "thread_id": record.thread_id,
        "agent_id": record.agent_id,
        "title": request.get("title"),
        "prompt": str(request.get("prompt") or ""),
        "status": record.status,
        "fields": [
            {
                "id": spec.id,
                "label": spec.label,
                "type": spec.type,
                "required": spec.required,
                "max_length": spec.max_length,
            }
            for spec in specs
        ],
        "routing": {
            "kind": kind,
            "slots": dict(slots) if slots else None,
            "vault_meta": dict(vault_meta) if vault_meta is not None else None,
        },
        "existing_vault_item_id": existing_vault_item_id,
        "existing_slot_names": existing_slot_names,
        "vault_storable_field_ids": storable_ids,
    }


def _filled_message(
    filled: Mapping[str, str],
    slots: Mapping[str, str],
    vault_item_id: str | None,
    vault_meta: Mapping[str, Any] | None,
    *,
    injected: bool,
) -> str:
    parts = ["The user completed the secure form (status=filled)."]
    destinations = ", ".join(
        f"{field_id} -> environment variable {slots[field_id]}"
        for field_id in slots
        if field_id in filled
    )
    if destinations:
        # Only speak about env availability when at least one slot was written.
        parts.append(f"Collected fields: {destinations}.")
        parts.append(
            "The values are stored as this agent's environment secrets and are never shown to you."
        )
        if injected:
            parts.append(
                "They are already injected into your command executions — use them "
                "right now and finish the task in this turn."
            )
        else:
            parts.append(
                "The harness rebuild failed, so these environment variables reach "
                "your command executions only from your NEXT turn — finish this turn "
                "now and read them then."
            )
    if vault_item_id is not None and vault_meta is not None:
        parts.append(
            f"The vault-storable fields were saved as an encrypted vault item "
            f"(type={vault_meta.get('item_type')}, id={vault_item_id}). "
            "The values are never shown to you."
        )
    parts.append(
        "Do not ask the user to reveal any of these values in chat, and never print or echo them."
    )
    return " ".join(parts)


def _cancelled_message() -> str:
    return (
        "The user dismissed the secure form (status=cancelled). Do not call "
        "request_secure_form again for these fields during this turn; ask the "
        "user how to proceed instead."
    )


def _field_statuses(
    specs: list[SecureFormFieldSpec], status: str, filled: set[str]
) -> list[dict[str, str]]:
    if status == "filled":
        return [
            {"id": spec.id, "status": "filled" if spec.id in filled else "omitted"}
            for spec in specs
        ]
    return [{"id": spec.id, "status": status} for spec in specs]


async def resolve_secure_form_submission(
    *,
    store: HitlPendingStore,
    agent_secrets: AgentSecretService,
    vault: VaultService,
    audit: AuditWriter | None = None,
    agent_id: str,
    user_id: int,
    thread_id: str,
    pending_id: str,
    action: str,
    values: Mapping[str, str],
    replace_confirmed: bool = False,
    save_to_vault: bool = False,
    rebuild: Callable[[str], Awaitable[bool]] | None = None,
) -> SecureFormSubmissionResult:
    """Validate and settle one secure-form submission.

    Pre-claim validation raises the 422 family without consuming the lease.
    The claim is the existing atomic single-use claim; the cross-table write
    unit runs on ONE pooled transaction (slots + vault + audit). Recoverable
    drift found inside the unit releases the lease without spending a reopen
    credit; a hard DB failure rolls everything back, releases the lease
    spending one credit, and raises ``SECURE_FORM_WRITE_FAILED``.
    """
    record = load_secure_form_record(
        store,
        agent_id=agent_id,
        user_id=user_id,
        pending_id=pending_id,
        thread_id=thread_id,
        expired_code=ErrorCode.SECURE_FORM_ALREADY_HANDLED,
    )
    if record.status in {"filled", "cancelled"}:
        # Idempotent lost-response replay: the terminal outcome already
        # happened, so its metadata is returned again instead of a second
        # write or a 409 that would strand the client.
        replayed = record.secure_form_result
        if replayed is not None:
            return SecureFormSubmissionResult(record, [], dict(replayed), replay=True)
        raise OctopError(ErrorCode.SECURE_FORM_ALREADY_HANDLED, "secure form already handled")
    if record.status != "pending":
        raise OctopError(ErrorCode.SECURE_FORM_ALREADY_HANDLED, "secure form already handled")

    specs, request = _registered_fields(record)
    if action == "submit" and len(record.action_requests) != 1:
        raise OctopError(
            ErrorCode.SECURE_FORM_REQUEST_INVALID, "mixed secure-form pause can only be cancelled"
        )

    if action != "submit":
        # Cancel: no writes, no values touched.
        if store.claim_secret_input(pending_id) is None:
            raise OctopError(ErrorCode.SECURE_FORM_ALREADY_HANDLED, "secure form already handled")
        store.mark_resolved(pending_id, "cancelled")
        summary: dict[str, Any] = {
            "action": "cancelled",
            "fields": _field_statuses(specs, "cancelled", set()),
            "slot_names": [],
            "vault_item_id": None,
            "injected": False,
        }
        record.secure_form_result = summary
        return SecureFormSubmissionResult(
            record, _decisions(record, message=_cancelled_message()), summary
        )

    # ------------------------------------------------ pre-claim (422 family)
    kind, slots, vault_meta = _routing(request)
    filled = _validate_values(specs, values)
    if save_to_vault and vault_meta is None:
        raise _field_invalid("save_to_vault requires the form to have registered vault metadata")
    vault_write = kind == "vault" or save_to_vault

    slot_values: dict[str, str] = {}
    slot_labels: dict[str, str] = {}
    if kind == "env":
        labels = {spec.id: spec.label for spec in specs}
        existing_slots = {row.slot_name for row in agent_secrets.list_slots(agent_id)}
        new_slots = {slot for slot in slots.values() if slot not in existing_slots}
        if len(existing_slots | new_slots) > AGENT_SECRET_MAX_SLOTS:
            raise OctopError(
                ErrorCode.SECURE_FORM_SLOT_INVALID,
                f"slot capacity exceeded: the agent has {len(existing_slots)} slots and "
                f"this form adds {len(new_slots)} new ones; the per-agent cap is "
                f"{AGENT_SECRET_MAX_SLOTS}",
            )
        for field_id, slot in slots.items():
            if field_id in filled:
                slot_values[slot] = filled[field_id]
                slot_labels[slot] = labels.get(field_id, slot)

    vault_fields: dict[str, str] = {}
    if vault_write:
        if vault_meta is None:
            raise _field_invalid("vault routing requires registered vault metadata")
        item_type = str(vault_meta.get("item_type"))
        title = str(vault_meta.get("title") or "").strip()
        if item_type not in VAULT_ITEM_FIELD_TYPES:
            raise _field_invalid(f"unknown vault item type {item_type!r}")
        allowed = VAULT_ITEM_FIELD_TYPES[item_type]
        vault_fields = {
            spec.type: filled[spec.id]
            for spec in specs
            if spec.id in filled and spec.type in allowed
        }
        if not vault_fields:
            raise _field_invalid(
                f"none of the submitted fields can be saved to a {item_type} vault item"
            )
        existing = vault.repo.find_by_title(user_id=user_id, item_type=item_type, title=title)
        if existing is not None:
            if not replace_confirmed:
                raise OctopError(
                    ErrorCode.VAULT_REPLACE_REQUIRED,
                    f"a {item_type} item titled {title!r} already exists",
                    details={"existing_vault_item_id": existing.vault_item_id},
                )
        else:
            vault.check_insert_capacity(user_id)

    # ------------------------------------------------ claim (single-use lease)
    claimed = store.claim_secret_input(pending_id)
    if claimed is None:
        raise OctopError(ErrorCode.SECURE_FORM_ALREADY_HANDLED, "secure form already handled")

    # ------------------------------------------------ cross-table write unit
    vault_item_id: str | None = None
    if slot_values or vault_write:
        db = vault.repo.db
        try:
            # Warm the purpose keys BEFORE the transaction opens (the
            # get_or_create bootstrap opens its own transaction, which SQLite
            # cannot nest) and INSIDE the try so a bootstrap failure still
            # releases the lease instead of wedging the record in `filling`.
            if slot_values:
                get_fernet(agent_secrets.secret_repo, PURPOSE_AGENT_SECRET)
            if vault_write:
                get_fernet(vault.secret_repo, PURPOSE_VAULT_ITEM)
            with db.transaction() as conn:
                if vault_write and db.dialect == "postgresql":
                    # Per-user serialization for the title lookup + cap-guarded
                    # insert (transaction-scoped, released on COMMIT/ROLLBACK).
                    conn.execute("SELECT pg_advisory_xact_lock(?)", (user_id,))
                if slot_values:
                    agent_secrets.store_slots_in_unit(
                        conn,
                        agent_id=agent_id,
                        user_id=user_id,
                        values=slot_values,
                        display_names=slot_labels,
                    )
                if vault_write:
                    # Narrowed by the pre-claim checks above.
                    assert vault_meta is not None
                    prior = vault.repo.find_by_title(
                        user_id=user_id, item_type=item_type, title=title, conn=conn
                    )
                    origin_raw = vault_meta.get("origin")
                    origin = (
                        normalize_secure_form_origin(origin_raw)
                        if isinstance(origin_raw, str)
                        else None
                    )
                    row = vault.store_item(
                        user_id,
                        item_type,
                        title,
                        origin or (origin_raw if isinstance(origin_raw, str) else None),
                        vault_fields,
                        replace_confirmed=replace_confirmed,
                        conn=conn,
                    )
                    vault_item_id = row.vault_item_id
                    if audit is not None:
                        audit(
                            conn,
                            "vault.rotate" if prior is not None else "vault.create",
                            vault_item_id,
                        )
        except OctopError:
            # Recoverable drift (replace required / cap): the transaction
            # rolled back, nothing persisted — release without a credit so a
            # corrected resubmit is not penalized.
            store.reopen_secure_form(pending_id, spend_credit=False)
            raise
        except Exception:
            logger.exception(
                "secure form write unit failed agent=%s pending_id=%s", agent_id, pending_id
            )
            reopened = store.reopen_secure_form(pending_id, spend_credit=True)
            if not reopened:
                logger.error(
                    "secure form reopen budget exhausted agent=%s pending_id=%s",
                    agent_id,
                    pending_id,
                )
            raise OctopError(
                ErrorCode.SECURE_FORM_WRITE_FAILED,
                "failed to persist the secure form; nothing was stored",
            ) from None

    store.mark_resolved(pending_id, "filled")
    # Terminal metadata is stashed BEFORE the awaited rebuild so no failure or
    # cancellation between them can leave a `filled` record without a
    # replayable summary; the rebuild only refreshes the injected flag.
    summary = {
        "action": "filled",
        "fields": _field_statuses(specs, "filled", set(filled)),
        "slot_names": sorted(slot_values),
        "vault_item_id": vault_item_id,
        "injected": False,
    }
    record.secure_form_result = summary
    try:
        injected = bool(slot_values) and rebuild is not None and bool(await rebuild(agent_id))
    except BaseException:
        # reload() already degrades ordinary exceptions to a bool; anything
        # that still escapes must not break the terminal state.
        logger.exception("secure form rebuild crashed agent=%s pending_id=%s", agent_id, pending_id)
        injected = False
    summary["injected"] = injected
    record.secure_form_result = summary
    message = _filled_message(
        filled, slots if kind == "env" else {}, vault_item_id, vault_meta, injected=injected
    )
    return SecureFormSubmissionResult(record, _decisions(record, message=message), summary)


__all__ = [
    "AuditWriter",
    "SecureFormFieldSpec",
    "SecureFormSubmissionResult",
    "load_secure_form_record",
    "resolve_secure_form_submission",
    "secure_form_pending_facts",
]
