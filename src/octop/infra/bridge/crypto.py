"""Fernet encryption for bridge credentials and peer tokens."""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet

from octop.infra.db.repos.secrets import SecretRepo

_FERNET_KEY = "bridge_fernet"


def _get_fernet(repo: SecretRepo) -> Fernet:
    raw = repo.get_or_create(_FERNET_KEY, Fernet.generate_key)
    return Fernet(raw)


def encrypt_payload(repo: SecretRepo, payload: dict[str, Any]) -> bytes:
    f = _get_fernet(repo)
    return f.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def decrypt_payload(repo: SecretRepo, blob: bytes) -> dict[str, Any]:
    f = _get_fernet(repo)
    data = json.loads(f.decrypt(blob).decode("utf-8"))
    return data if isinstance(data, dict) else {}
