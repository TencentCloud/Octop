"""Registration-time validation for ``request_secure_form``.

The interrupt fires before the tool body runs, so the model's raw arguments
reach the pending store unvalidated by the pydantic schema. Every pause
registration site validates through :func:`validate_secure_form_action_requests`
*before* the pause is registered: an invalid form never enters the store (it
would evict the user's other in-flight pause) and the already-paused turn is
auto-resumed with an inline refusal respond decision instead.

Error strings here are model-facing (they travel back as the respond decision
the model reads), not end-user copy — English by convention.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from typing import Any
from urllib.parse import urlsplit

from octop.infra.agents.secret_input.slots import (
    AGENT_SECRET_MAX_SLOTS,
    normalize_slot_name,
)
from octop.infra.agents.secure_form.tool import REQUEST_SECURE_FORM_TOOL_NAME

SECURE_FORM_MAX_FIELDS = 8
SECURE_FORM_MAX_LABEL = 60
SECURE_FORM_MAX_TITLE = 60
SECURE_FORM_MAX_PROMPT = 500
SECURE_FORM_MAX_VAULT_TITLE = 120
SECURE_FORM_MAX_FIELD_LENGTH = 256

SECURE_FORM_FIELD_TYPES = frozenset(
    {"text", "password", "otp", "card_number", "card_exp", "card_cvv"}
)
SECURE_FORM_VAULT_ITEM_TYPES = frozenset({"login", "card", "contact"})

# Shortest max_length that can still hold the field type's submit-time shape.
FIELD_TYPE_MIN_MAX_LENGTH: dict[str, int] = {
    "text": 1,
    "password": 1,
    "otp": 4,
    "card_number": 12,
    "card_exp": 5,
    "card_cvv": 3,
}

# Vault routing accepts only fields the item type may persist (card_cvv and
# otp are never persisted to the vault, whatever the routing).
VAULT_ITEM_FIELD_TYPES: dict[str, frozenset[str]] = {
    "login": frozenset({"text", "password"}),
    "card": frozenset({"card_number", "card_exp"}),
    "contact": frozenset({"text"}),
}

_FIELD_ID_RE = re.compile(r"[a-z0-9_]{1,32}")

# Reads the agent's existing secret-slot names for the capacity check.
# Injectable so unit callers can stub it; ``None`` skips the check.
ExistingSlotNames = Callable[[str], Collection[str]]


def normalize_secure_form_origin(raw: object) -> str | None:
    """Return the normalized ``scheme://host[:port]`` origin, or ``None``.

    Grammar: http(s) scheme only, lowercase host, no userinfo, no trailing
    dot, no wildcards; IP literals allowed; non-ASCII hosts rejected (no
    punycode handling). Stored and compared as this exact string.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        return None
    if not parts.netloc or "@" in parts.netloc:
        return None
    host = parts.hostname or ""
    if not host or not host.isascii() or host.endswith(".") or "*" in host:
        return None
    # DNS labels / IPv4 literals, or a bracket-less IPv6 literal (urlsplit
    # strips the brackets; a colon must then be present).
    if not (
        re.fullmatch(r"[a-z0-9._-]+", host) or (":" in host and re.fullmatch(r"[a-f0-9:]+", host))
    ):
        return None
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return None
    # urlsplit strips IPv6 brackets; re-add them so the normalized string
    # stays a valid origin.
    host_part = f"[{host}]" if ":" in host else host
    if port is None:
        return f"{scheme}://{host_part}"
    return f"{scheme}://{host_part}:{port}"


def validate_secure_form_args(
    args: object,
    *,
    agent_id: str = "",
    existing_slot_names: ExistingSlotNames | None = None,
) -> str | None:
    """Return the refusal reason for invalid form args, or ``None`` when valid.

    ``args`` is the model's raw tool-call payload (untrusted): the interrupt
    precedes pydantic validation, so nothing here may assume schema shapes.
    """
    if not isinstance(args, dict):
        return "the tool arguments must be an object"
    fields = args.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= SECURE_FORM_MAX_FIELDS:
        return f"fields must be a list of 1 to {SECURE_FORM_MAX_FIELDS} entries"

    field_types: dict[str, str] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            return f"fields[{index}] must be an object"
        field_id = field.get("id")
        if not isinstance(field_id, str) or not _FIELD_ID_RE.fullmatch(field_id):
            return f"fields[{index}].id must match [a-z0-9_]{{1,32}} and be unique"
        if field_id in field_types:
            return f"duplicate field id {field_id!r}"
        label = field.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > SECURE_FORM_MAX_LABEL:
            return f"field {field_id!r}: label must be 1 to {SECURE_FORM_MAX_LABEL} characters"
        field_type = field.get("type")
        if field_type not in SECURE_FORM_FIELD_TYPES:
            return (
                f"field {field_id!r}: type must be one of "
                f"{', '.join(sorted(SECURE_FORM_FIELD_TYPES))}"
            )
        required = field.get("required", True)
        if not isinstance(required, bool):
            return f"field {field_id!r}: required must be a boolean"
        max_length = field.get("max_length")
        if max_length is not None:
            if isinstance(max_length, bool) or not isinstance(max_length, int):
                return f"field {field_id!r}: max_length must be an integer"
            minimum = FIELD_TYPE_MIN_MAX_LENGTH[str(field_type)]
            if not minimum <= max_length <= SECURE_FORM_MAX_FIELD_LENGTH:
                return (
                    f"field {field_id!r}: max_length must be at least {minimum} "
                    f"for type {field_type} and at most {SECURE_FORM_MAX_FIELD_LENGTH}"
                )
        field_types[field_id] = str(field_type)

    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > SECURE_FORM_MAX_PROMPT:
        return f"prompt is required (1 to {SECURE_FORM_MAX_PROMPT} characters)"
    title = args.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > SECURE_FORM_MAX_TITLE):
        return f"title must be a string of at most {SECURE_FORM_MAX_TITLE} characters"

    routing = args.get("routing")
    if not isinstance(routing, dict):
        return "routing must be an object with kind 'env' or 'vault'"
    kind = routing.get("kind")
    if kind not in ("env", "vault"):
        return "routing.kind must be 'env' or 'vault'"

    new_slots: set[str] = set()
    if kind == "env":
        slots = routing.get("slots")
        if not isinstance(slots, dict) or not slots:
            return "routing.kind 'env' requires routing.slots mapping every field id to a slot name"
        if set(slots) != set(field_types):
            return "routing.slots must contain exactly one entry per field id"
        for field_id, raw_slot in slots.items():
            normalized = normalize_slot_name(raw_slot)
            if normalized is None:
                return f"field {field_id!r}: invalid or reserved slot name {raw_slot!r}"
            if normalized in new_slots:
                return (
                    f"slot names must be pairwise distinct after normalization "
                    f"({normalized} is mapped more than once)"
                )
            new_slots.add(normalized)
        if existing_slot_names is not None:
            existing = {str(name).upper() for name in existing_slot_names(agent_id)}
            if len(existing | new_slots) > AGENT_SECRET_MAX_SLOTS:
                return (
                    f"slot capacity exceeded: the agent has {len(existing)} slots and "
                    f"this form adds {len(new_slots - existing)} new ones; the per-agent "
                    f"cap is {AGENT_SECRET_MAX_SLOTS}"
                )

    vault_meta = routing.get("vault_meta")
    vault_allowed_fields: frozenset[str] | None = None
    if vault_meta is not None:
        if not isinstance(vault_meta, dict):
            return "routing.vault_meta must be an object"
        item_type = vault_meta.get("item_type")
        if item_type not in SECURE_FORM_VAULT_ITEM_TYPES:
            return (
                "routing.vault_meta.item_type must be one of "
                f"{', '.join(sorted(SECURE_FORM_VAULT_ITEM_TYPES))}"
            )
        vault_allowed_fields = VAULT_ITEM_FIELD_TYPES[str(item_type)]
        vault_title = vault_meta.get("title")
        if (
            not isinstance(vault_title, str)
            or not 1 <= len(vault_title.strip()) <= SECURE_FORM_MAX_VAULT_TITLE
        ):
            return (
                "routing.vault_meta.title is required "
                f"(1 to {SECURE_FORM_MAX_VAULT_TITLE} characters)"
            )
        origin = vault_meta.get("origin")
        if origin is not None and normalize_secure_form_origin(origin) is None:
            return (
                "routing.vault_meta.origin must be scheme://host[:port] with an "
                "http(s) scheme, lowercase host, no userinfo, no trailing dot, "
                "no wildcards, and no path"
            )
    if kind == "vault":
        if vault_meta is None:
            return "routing.vault_meta is required when routing.kind is 'vault'"
        allowed = vault_allowed_fields or frozenset()
        for field_id, field_type in field_types.items():
            if field_type not in allowed:
                return (
                    f"field {field_id!r} of type {field_type} cannot be persisted for "
                    f"vault item_type {vault_meta.get('item_type')!r} "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
    return None


def validate_secure_form_action_requests(
    action_requests: list[dict[str, Any]],
    *,
    agent_id: str = "",
    existing_slot_names: ExistingSlotNames | None = None,
) -> str | None:
    """Refusal reason for the first invalid ``request_secure_form`` action.

    Returns ``None`` when no action in the pause uses the tool or every use is
    a valid form.
    """
    for action in action_requests:
        if not isinstance(action, dict) or action.get("name") != REQUEST_SECURE_FORM_TOOL_NAME:
            continue
        reason = validate_secure_form_args(
            action.get("args"),
            agent_id=agent_id,
            existing_slot_names=existing_slot_names,
        )
        if reason is not None:
            return reason
    return None


def extract_secure_form_request(
    action_requests: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Raw ``request_secure_form`` args from a pending record's actions.

    The pending store already carries the tool's raw args in
    ``action_requests``; the registered schema is re-derived on demand from
    them (validate + normalize via :func:`normalize_secure_form_origin`) rather
    than duplicated onto the store record — that keeps the pending payload the
    single source of truth for a later GET /secure-form/{pending_id}.
    """
    for action in action_requests:
        if isinstance(action, dict) and action.get("name") == REQUEST_SECURE_FORM_TOOL_NAME:
            args = action.get("args")
            return args if isinstance(args, dict) else {}
    return None


def secure_form_refusal_message(reason: str) -> str:
    return (
        f"The secure form request was rejected: {reason}. "
        "Fix the arguments or continue without it. Do not retry within this turn."
    )


def secure_form_refusal_decisions(
    action_requests: list[dict[str, Any]],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    """One respond decision per action — the member-refusal shape."""
    count = len(action_requests) or 1
    return [
        {"type": "respond", "message": secure_form_refusal_message(reason)} for _ in range(count)
    ]


__all__ = [
    "ExistingSlotNames",
    "FIELD_TYPE_MIN_MAX_LENGTH",
    "SECURE_FORM_FIELD_TYPES",
    "SECURE_FORM_VAULT_ITEM_TYPES",
    "VAULT_ITEM_FIELD_TYPES",
    "extract_secure_form_request",
    "normalize_secure_form_origin",
    "secure_form_refusal_decisions",
    "secure_form_refusal_message",
    "validate_secure_form_action_requests",
    "validate_secure_form_args",
]
