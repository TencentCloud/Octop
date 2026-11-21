"""PKCE helpers shared by connector OAuth flows."""

from __future__ import annotations

import base64
import hashlib
import secrets


def s256_challenge(verifier: str) -> str:
    """PKCE S256 challenge (RFC 7636). SHA-256 is the protocol hash, not a password hash."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    return verifier, s256_challenge(verifier)
