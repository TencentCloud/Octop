"""Fernet encryption for bridge credentials and peer tokens."""

from __future__ import annotations

from typing import Any

from octop.infra.crypto.fernet import PURPOSE_BRIDGE, decrypt_json, encrypt_json
from octop.infra.db.repos.secrets import SecretRepo


def encrypt_payload(repo: SecretRepo, payload: dict[str, Any]) -> bytes:
    return encrypt_json(repo, PURPOSE_BRIDGE, payload)


def decrypt_payload(repo: SecretRepo, blob: bytes) -> dict[str, Any]:
    return decrypt_json(repo, PURPOSE_BRIDGE, blob)
