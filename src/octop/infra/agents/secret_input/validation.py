"""Slot-name rules for chat-collected agent secrets, plus registration-time
validation for ``request_secure_form`` and the manual vault-item creation
payload.

The interrupt fires before the tool body runs, so the model's raw arguments
reach the pending store unvalidated by the pydantic schema. Every pause
registration site validates through :func:`validate_secure_form_action_requests`
*before* the pause is registered: an invalid form never enters the store (it
would evict the user's other in-flight pause) and the already-paused turn is
auto-resumed with an inline refusal respond decision instead.

Error strings here are model- or developer-facing (they travel back as the
respond decision the model reads, or as the ``details`` of a localized API
error), not end-user copy — English by convention.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from octop.infra.agents.secret_input.tool import REQUEST_SECURE_FORM_TOOL_NAME
from octop.infra.errors import ErrorCode, OctopError

# A slot becomes an environment variable in the agent's command executions, so
# its name must be a portable env-var identifier. Uppercase is the convention;
# lowercase is accepted and normalized to upper so one slot cannot appear twice
# under different casings on case-insensitive filesystems/OSes.
_SLOT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# Slots are injected as env vars next to the platform's own identity variables;
# shadowing these would break command execution or leak across concerns. The
# exec-hijack class (loader/runtime config an attacker-controlled value could
# turn into code execution) is denied for every chat-collected slot, including
# env-routed secure-form fields.
_RESERVED_SLOT_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "TERM",
        "HOSTNAME",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "PYTHONPATH",
        "PYTHONHOME",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
    }
)
_RESERVED_SLOT_PREFIXES = ("OCTOP_",)

# One slot per named secret; keep a bounded, auditable set per agent.
AGENT_SECRET_MAX_SLOTS = 32
# Submitted values are short credentials, not file payloads.
AGENT_SECRET_MAX_VALUE_CHARS = 8192


def normalize_slot_name(raw: object) -> str | None:
    """Return the canonical slot name, or ``None`` when the name is invalid.

    Canonical form is upper-case. Reserved platform names and the ``OCTOP_``
    prefix (platform identity namespace) are rejected.
    """
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not _SLOT_RE.match(name):
        return None
    upper = name.upper()
    if upper in _RESERVED_SLOT_NAMES or upper.startswith(_RESERVED_SLOT_PREFIXES):
        return None
    return upper


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

# Per-type submit-time value shapes, shared by the secure-form submit path
# and manual vault-item creation.
_OTP_RE = re.compile(r"\d{4,8}")
_CARD_NUMBER_RE = re.compile(r"\d{12,19}")
_CARD_EXP_RE = re.compile(r"(\d{2})/(\d{2})")
_CARD_CVV_RE = re.compile(r"\d{3,4}")


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


def check_field_value_shape(field_type: str, value: str) -> tuple[str | None, str]:
    """Check one value against its field type's submit-time shape.

    Returns ``(violation detail or None, normalized value)`` — callers raise
    their own error with the detail. Values are stored byte-exact; the only
    explicit normalizations are the ``card_number`` space strip, while
    ``card_exp`` is stored as given.
    """
    if field_type == "otp" and not _OTP_RE.fullmatch(value):
        return "otp must be 4 to 8 digits", value
    if field_type == "card_cvv" and not _CARD_CVV_RE.fullmatch(value):
        return "card security code must be 3 to 4 digits", value
    if field_type == "card_number":
        stripped = value.replace(" ", "")
        if not _CARD_NUMBER_RE.fullmatch(stripped):
            return "card number must be 12 to 19 digits", stripped
        return None, stripped
    if field_type == "card_exp":
        match = _CARD_EXP_RE.fullmatch(value)
        if match is None or not 1 <= int(match.group(1)) <= 12:
            return "expiry must be MM/YY with a month of 01-12", value
    return None, value


def validate_manual_vault_item(
    item_type: str,
    title: str,
    origin: str | None,
    fields: Sequence[Mapping[str, Any]],
) -> tuple[str, str | None, dict[str, str]]:
    """Validate a manually created vault item (dashboard "New item" flow).

    Mirrors the submit-path shapes — origin grammar, per-item-type field
    pairing, title/label/field lengths, per-type value shapes — and returns
    the normalized ``(title, origin, values)`` ready for
    ``VaultService.store_item``. The envelope stores one value per field
    TYPE, so a duplicate type is refused instead of silently collapsing.
    """
    if item_type not in SECURE_FORM_VAULT_ITEM_TYPES:
        raise OctopError(
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            f"item_type must be one of {', '.join(sorted(SECURE_FORM_VAULT_ITEM_TYPES))}",
        )
    stripped_title = title.strip()
    if not 1 <= len(stripped_title) <= SECURE_FORM_MAX_VAULT_TITLE:
        raise OctopError(
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            f"title is required (1 to {SECURE_FORM_MAX_VAULT_TITLE} characters)",
        )
    normalized_origin: str | None = None
    if origin is not None:
        normalized_origin = normalize_secure_form_origin(origin)
        if normalized_origin is None:
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                "origin must be scheme://host[:port] with an http(s) scheme, "
                "lowercase host, no userinfo, no trailing dot, no wildcards, "
                "and no path",
            )
    if not 1 <= len(fields) <= SECURE_FORM_MAX_FIELDS:
        raise OctopError(
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            f"fields must hold 1 to {SECURE_FORM_MAX_FIELDS} entries",
        )
    allowed = VAULT_ITEM_FIELD_TYPES[item_type]
    values: dict[str, str] = {}
    seen_ids: set[str] = set()
    for index, field in enumerate(fields):
        field_id = str(field.get("id") or "")
        if not _FIELD_ID_RE.fullmatch(field_id):
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"fields[{index}].id must match [a-z0-9_]{{1,32}} and be unique",
                details={"field": field_id or None},
            )
        if field_id in seen_ids:
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"duplicate field id {field_id!r}",
                details={"field": field_id},
            )
        seen_ids.add(field_id)
        label = field.get("label")
        if label is not None and (
            not isinstance(label, str) or not label.strip() or len(label) > SECURE_FORM_MAX_LABEL
        ):
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"field {field_id!r}: label must be 1 to {SECURE_FORM_MAX_LABEL} characters",
                details={"field": field_id},
            )
        field_type = str(field.get("type") or "")
        if field_type not in allowed:
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"field {field_id!r} of type {field_type!r} cannot be stored "
                f"for vault item_type {item_type!r} "
                f"(allowed: {', '.join(sorted(allowed))})",
                details={"field": field_id},
            )
        if field_type in values:
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"only one field of each type is allowed; {field_type!r} appears more than once",
                details={"field": field_id},
            )
        value = field.get("value")
        if not isinstance(value, str) or not value.strip():
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"field {field_id!r} is required",
                details={"field": field_id},
            )
        if len(value) > SECURE_FORM_MAX_FIELD_LENGTH:
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"field {field_id!r} exceeds {SECURE_FORM_MAX_FIELD_LENGTH} characters",
                details={"field": field_id},
            )
        violation, normalized = check_field_value_shape(field_type, value)
        if violation is not None:
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"field {field_id!r}: {violation}",
                details={"field": field_id},
            )
        values[field_type] = normalized
    return stripped_title, normalized_origin, values


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
    "AGENT_SECRET_MAX_SLOTS",
    "AGENT_SECRET_MAX_VALUE_CHARS",
    "ExistingSlotNames",
    "FIELD_TYPE_MIN_MAX_LENGTH",
    "SECURE_FORM_FIELD_TYPES",
    "SECURE_FORM_VAULT_ITEM_TYPES",
    "VAULT_ITEM_FIELD_TYPES",
    "check_field_value_shape",
    "extract_secure_form_request",
    "normalize_secure_form_origin",
    "normalize_slot_name",
    "secure_form_refusal_decisions",
    "secure_form_refusal_message",
    "validate_manual_vault_item",
    "validate_secure_form_action_requests",
    "validate_secure_form_args",
]
