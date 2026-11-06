"""Fernet encryption for connector credentials."""

from __future__ import annotations

from typing import Any

from octop.infra.crypto.fernet import PURPOSE_CONNECTOR, decrypt_json, encrypt_json
from octop.infra.db.repos.secrets import SecretRepo


def encrypt_credentials(repo: SecretRepo, payload: dict[str, Any]) -> bytes:
    return encrypt_json(repo, PURPOSE_CONNECTOR, payload)


def decrypt_credentials(repo: SecretRepo, blob: bytes) -> dict[str, Any]:
    return decrypt_json(repo, PURPOSE_CONNECTOR, blob)
