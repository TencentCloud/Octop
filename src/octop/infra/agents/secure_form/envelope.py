"""Fernet envelope for user vault items, bound to the row identity."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from octop.infra.crypto.fernet import PURPOSE_VAULT_ITEM, decrypt_json, encrypt_json
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError

ENVELOPE_VERSION = 1
# Always 1 today: the purpose key is effectively permanent and no rewrap
# migration exists. ``kid`` is recorded so a future rotation has a marker to
# work from, not because rotation works now.
KEY_VERSION = 1

# Which field types each item type may persist, applied by the envelope writer
# regardless of the form's routing: ``card_cvv`` and ``otp`` must never enter
# the vault even when the form collected them for env slots.
ITEM_TYPE_FIELD_ALLOWLIST: Mapping[str, frozenset[str]] = {
    "login": frozenset({"text", "password"}),
    "card": frozenset({"card_number", "card_exp"}),
    "contact": frozenset({"text"}),
}


def filter_vault_fields(item_type: str, fields: Mapping[str, str]) -> dict[str, str]:
    """Keep only the field types *item_type* is allowed to persist."""
    allowed = ITEM_TYPE_FIELD_ALLOWLIST.get(item_type, frozenset())
    return {name: value for name, value in fields.items() if name in allowed}


def seal_vault_fields(
    repo: SecretRepo,
    *,
    user_id: int,
    vault_item_id: str,
    item_type: str,
    fields: Mapping[str, str],
) -> bytes:
    """Encrypt *fields* under ``PURPOSE_VAULT_ITEM``, bound to the row identity.

    The allow-list filter is applied here as well so no caller can seal a
    non-storable field type even if it skips the service-level check.
    """
    payload: dict[str, Any] = {
        "v": ENVELOPE_VERSION,
        "kid": KEY_VERSION,
        "bind": {
            "user_id": user_id,
            "vault_item_id": vault_item_id,
            "item_type": item_type,
        },
        "fields": filter_vault_fields(item_type, fields),
    }
    return encrypt_json(repo, PURPOSE_VAULT_ITEM, payload)


def open_vault_fields(
    repo: SecretRepo,
    *,
    row_user_id: int,
    vault_item_id: str,
    item_type: str,
    blob: bytes,
) -> dict[str, str]:
    """Decrypt a vault envelope and verify it against the row reading it.

    A blob transplanted between rows fails the bind check and is reported as
    tampering rather than returned; a payload without our envelope shape is
    rejected the same way instead of failing open.
    """
    payload = decrypt_json(repo, PURPOSE_VAULT_ITEM, blob)
    bind = payload.get("bind")
    if not isinstance(bind, dict):
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "vault envelope has no bind")
    if bind != {
        "user_id": row_user_id,
        "vault_item_id": vault_item_id,
        "item_type": item_type,
    }:
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            "vault envelope bind mismatch — possible tampering",
        )
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "vault envelope has no fields")
    return {str(name): str(value) for name, value in fields.items()}
