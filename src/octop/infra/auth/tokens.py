"""Access-token JWT helpers shared by HTTP auth and infra (Bridge)."""

from __future__ import annotations

import secrets
import time
from typing import Any, Literal, cast

import jwt

TokenPurpose = Literal["access", "mfa", "reauth"]

PURPOSE_ACCESS: TokenPurpose = "access"
PURPOSE_MFA: TokenPurpose = "mfa"
PURPOSE_REAUTH: TokenPurpose = "reauth"

_VALID_PURPOSES = frozenset({"access", "mfa", "reauth"})

# Short-lived challenge tokens (MFA verify / reauth grant).
MFA_TOKEN_TTL_SECONDS = 300
REAUTH_TOKEN_TTL_SECONDS = 300


class InvalidToken(Exception): ...


class TokenExpired(InvalidToken): ...


def sign_token(
    secret: bytes,
    *,
    sub: int,
    uname: str,
    role: str,
    purpose: TokenPurpose,
    ttl_seconds: int = 86400,
    mfa_version: int = 0,
    amr: str | None = None,
    jti: str | None = None,
) -> str:
    """Mint a JWT. ``purpose`` is required; missing purpose must fail closed."""
    if purpose not in _VALID_PURPOSES:
        raise ValueError(f"invalid token purpose: {purpose!r}")
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(sub),
        "uname": uname,
        "role": role,
        "purpose": purpose,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if purpose == PURPOSE_ACCESS:
        payload["mfa_version"] = int(mfa_version)
    elif purpose == PURPOSE_MFA:
        payload["mfa_version"] = int(mfa_version)
        if amr is None:
            raise ValueError("mfa tokens require amr")
        payload["amr"] = amr
        payload["jti"] = jti or secrets.token_urlsafe(16)
    elif purpose == PURPOSE_REAUTH:
        payload["jti"] = jti or secrets.token_urlsafe(16)
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(secret: bytes, token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        if "sub" in payload:
            payload["sub"] = int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpired() from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidToken(str(exc)) from exc


def token_purpose(payload: dict[str, Any]) -> TokenPurpose | None:
    """Return the purpose claim, or None when absent (legacy tokens)."""
    raw = payload.get("purpose")
    if raw is None:
        return None
    if raw not in _VALID_PURPOSES:
        raise InvalidToken(f"invalid purpose: {raw!r}")
    return cast(TokenPurpose, raw)


def token_mfa_version(payload: dict[str, Any]) -> int:
    """Absent ``mfa_version`` claim ≡ 0 (pre-MFA tokens)."""
    raw = payload.get("mfa_version")
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidToken("invalid mfa_version") from exc
