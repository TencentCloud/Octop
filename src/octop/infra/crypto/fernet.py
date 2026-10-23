"""Shared Fernet helpers keyed by purpose via ``SecretRepo``."""

from __future__ import annotations

import json
from typing import Any
from weakref import WeakKeyDictionary

from cryptography.fernet import Fernet, InvalidToken

from octop.infra.db.repos.secrets import SecretRepo

PURPOSE_CONNECTOR = "connector_fernet"
PURPOSE_BRIDGE = "bridge_fernet"
PURPOSE_SSO = "sso_fernet"
PURPOSE_STORAGE = "storage_fernet"
PURPOSE_PROVIDER = "provider_fernet"
PURPOSE_VOICE = "voice_fernet"
PURPOSE_SETTINGS = "settings_secret_fernet"

# One Fernet per (SecretRepo, purpose). Avoids a DB round-trip on every
# seal/open during list_all / hot paths. Cleared when the repo is GC'd.
_fernet_by_repo: WeakKeyDictionary[SecretRepo, dict[str, Fernet]] = WeakKeyDictionary()


def get_fernet(repo: SecretRepo, purpose: str) -> Fernet:
    by_purpose = _fernet_by_repo.get(repo)
    if by_purpose is None:
        by_purpose = {}
        _fernet_by_repo[repo] = by_purpose
    cached = by_purpose.get(purpose)
    if cached is not None:
        return cached
    raw = repo.get_or_create(purpose, Fernet.generate_key)
    fernet = Fernet(raw)
    by_purpose[purpose] = fernet
    return fernet


def encrypt_bytes(repo: SecretRepo, purpose: str, plain: bytes) -> bytes:
    return get_fernet(repo, purpose).encrypt(plain)


def decrypt_bytes(repo: SecretRepo, purpose: str, blob: bytes) -> bytes:
    return get_fernet(repo, purpose).decrypt(blob)


def encrypt_str(repo: SecretRepo, purpose: str, plain: str) -> bytes:
    return encrypt_bytes(repo, purpose, plain.encode("utf-8"))


def decrypt_str(repo: SecretRepo, purpose: str, blob: bytes) -> str:
    return decrypt_bytes(repo, purpose, blob).decode("utf-8")


def encrypt_json(repo: SecretRepo, purpose: str, payload: dict[str, Any]) -> bytes:
    return encrypt_bytes(repo, purpose, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def decrypt_json(repo: SecretRepo, purpose: str, blob: bytes) -> dict[str, Any]:
    data = json.loads(decrypt_bytes(repo, purpose, blob).decode("utf-8"))
    return data if isinstance(data, dict) else {}


def seal_text(repo: SecretRepo, purpose: str, plain: str | None) -> str | None:
    """Encrypt a TEXT-column secret to an ASCII Fernet token."""
    if plain is None:
        return None
    return encrypt_str(repo, purpose, plain).decode("ascii")


def open_text(repo: SecretRepo, purpose: str, stored: str | None) -> str | None:
    """Decrypt a TEXT-column secret; legacy plaintext is returned as-is."""
    if stored is None or stored == "":
        return stored
    try:
        return decrypt_str(repo, purpose, stored.encode("ascii"))
    except (InvalidToken, ValueError, UnicodeEncodeError):
        return stored


def seal_secret_bytes(repo: SecretRepo, purpose: str, plain: bytes) -> bytes:
    """Encrypt a ``secrets.v`` blob."""
    return encrypt_bytes(repo, purpose, plain)


def open_secret_bytes(repo: SecretRepo, purpose: str, stored: bytes) -> bytes:
    """Decrypt a ``secrets.v`` blob; legacy plaintext bytes are returned as-is."""
    try:
        return decrypt_bytes(repo, purpose, stored)
    except (InvalidToken, ValueError):
        return stored
