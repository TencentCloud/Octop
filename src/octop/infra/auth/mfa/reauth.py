"""Reauth grant: proof of possession → short-lived purpose=reauth JWT + DB jti."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from octop.infra.auth.tokens import (
    PURPOSE_REAUTH,
    REAUTH_TOKEN_TTL_SECONDS,
    decode_token,
    sign_token,
    token_purpose,
)
from octop.infra.db.repos.auth_challenges import KIND_REAUTH, AuthChallengeRepo
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.password import verify_password


async def prove_password(
    services: SharedServices,
    *,
    user_id: int,
    password: str,
    ldap_service: Any | None = None,
    ldap_bind_throttle: Any | None = None,
    client_ip: str = "",
) -> None:
    """Validate local password, else throttled LDAP bind. SSO-only → PASSWORD_NOT_SET."""
    if not password:
        raise OctopError(ErrorCode.PASSWORD_NOT_SET, "password required for reauth")
    row = services.user_repo.get(user_id)
    if row is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "user not found")
    if row.password_hash:
        if verify_password(password, row.password_hash):
            return
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid credentials")
    # No local password: directory-provisioned accounts may prove via LDAP.
    if ldap_service is None or not ldap_service.is_enabled():
        raise OctopError(ErrorCode.PASSWORD_NOT_SET, "no local password for reauth")
    throttle = ldap_bind_throttle
    if throttle is not None:
        retry_after = throttle.retry_after(row.username, client_ip)
        if retry_after > 0:
            minutes = max(1, (retry_after + 59) // 60)
            raise OctopError(
                ErrorCode.LOGIN_LOCKED,
                "too many directory login attempts",
                details={"retry_after_seconds": retry_after, "minutes": minutes},
            )
    identity = await asyncio.get_running_loop().run_in_executor(
        None, ldap_service.directory_authenticate, row.username, password
    )
    if identity is None:
        if throttle is not None:
            retry_after = throttle.record_failure(row.username, client_ip)
            if retry_after > 0:
                minutes = max(1, (retry_after + 59) // 60)
                raise OctopError(
                    ErrorCode.LOGIN_LOCKED,
                    "too many directory login attempts",
                    details={"retry_after_seconds": retry_after, "minutes": minutes},
                )
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid credentials")
    if throttle is not None:
        throttle.clear(row.username, client_ip)


def issue_reauth_token(
    services: SharedServices,
    *,
    user_id: int,
    username: str,
    role: str,
) -> str:
    secret = services.secret_repo.get("jwt")
    if secret is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
    token = sign_token(
        secret,
        sub=user_id,
        uname=username,
        role=role,
        purpose=PURPOSE_REAUTH,
        ttl_seconds=REAUTH_TOKEN_TTL_SECONDS,
    )
    payload = decode_token(secret, token)
    jti = str(payload.get("jti") or "")
    if not jti:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "reauth token missing jti")
    expires = int(time.time()) + REAUTH_TOKEN_TTL_SECONDS
    services.auth_challenge_repo.insert(
        kind=KIND_REAUTH,
        jti=jti,
        user_id=user_id,
        expires_at=expires,
    )
    return token


def validate_reauth_grant(
    services: SharedServices,
    *,
    user_id: int,
    reauth_token: str,
) -> str:
    """Validate a reauth JWT + live challenge row. Returns jti (does not burn)."""
    secret = services.secret_repo.get("jwt")
    if secret is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
    try:
        payload = decode_token(secret, reauth_token)
    except Exception as exc:  # noqa: BLE001 - TokenExpired/InvalidToken
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required") from exc
    try:
        purpose = token_purpose(payload)
    except Exception as exc:  # noqa: BLE001
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required") from exc
    if purpose != PURPOSE_REAUTH:
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required")
    if int(payload.get("sub") or 0) != user_id:
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required")
    jti = str(payload.get("jti") or "")
    if not jti:
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required")
    row = services.auth_challenge_repo.get_by_jti(jti)
    if (
        row is None
        or row.kind != KIND_REAUTH
        or row.user_id != user_id
        or row.consumed_at is not None
        or row.expires_at < int(time.time())
    ):
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required")
    return jti


def burn_reauth_grant(challenge_repo: AuthChallengeRepo, jti: str) -> None:
    """Consume the reauth challenge exactly once at the committing step."""
    consumed = challenge_repo.try_consume_jti(jti)
    if consumed is None:
        raise OctopError(ErrorCode.MFA_REAUTH_REQUIRED, "reauth required")
