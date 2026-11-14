"""User-level API token helpers for the memory MCP server.

Shared by the HTTP router that issues tokens and by MCP request
authentication. Only the SHA-256 hex digest is persisted; the plaintext
token is returned once at creation and never stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_PREFIX = "omcp_"

_TOKEN_BYTES = 32
_HINT_HEAD = len(TOKEN_PREFIX) + 4
_HINT_TAIL = 4


def generate_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hex)`` for a fresh token."""
    plaintext = f"{TOKEN_PREFIX}{secrets.token_urlsafe(_TOKEN_BYTES)}"
    return plaintext, hash_token(plaintext)


def hash_token(token: str) -> str:
    """SHA-256 hex digest of *token* — the only form that is stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    """Constant-time check of *token* against a stored digest."""
    return hmac.compare_digest(hash_token(token), token_hash)


def token_hint(token: str) -> str:
    """Display form with the middle hidden, e.g. ``omcp_abcd…wxyz``."""
    return f"{token[:_HINT_HEAD]}…{token[-_HINT_TAIL:]}"
