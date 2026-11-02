"""Installation-scoped Fernet helpers for reversible secrets at rest."""

from __future__ import annotations

from octop.infra.crypto.fernet import (
    PURPOSE_BRIDGE,
    PURPOSE_CONNECTOR,
    PURPOSE_PROVIDER,
    PURPOSE_SETTINGS,
    PURPOSE_SSO,
    PURPOSE_STORAGE,
    PURPOSE_VOICE,
    decrypt_bytes,
    decrypt_json,
    decrypt_str,
    encrypt_bytes,
    encrypt_json,
    encrypt_str,
    open_secret_bytes,
    open_text,
    seal_secret_bytes,
    seal_text,
)

__all__ = [
    "PURPOSE_BRIDGE",
    "PURPOSE_CONNECTOR",
    "PURPOSE_PROVIDER",
    "PURPOSE_SETTINGS",
    "PURPOSE_SSO",
    "PURPOSE_STORAGE",
    "PURPOSE_VOICE",
    "decrypt_bytes",
    "decrypt_json",
    "decrypt_str",
    "encrypt_bytes",
    "encrypt_json",
    "encrypt_str",
    "open_secret_bytes",
    "open_text",
    "seal_secret_bytes",
    "seal_text",
]
