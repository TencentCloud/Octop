"""FastAPI Depends, JWT helpers, and auth routing."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from fastapi import Depends, Header, Query, Request

from octop.infra.auth.tokens import PURPOSE_ACCESS, token_mfa_version, token_purpose
from octop.infra.auth.tokens import InvalidToken as InvalidToken
from octop.infra.auth.tokens import TokenExpired as TokenExpired
from octop.infra.auth.tokens import decode_token as decode_token
from octop.infra.auth.tokens import sign_token as sign_token
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.permissions import PERMISSIONS, user_has_permission

if TYPE_CHECKING:
    from octop.infra.server import OctopServer
    from octop.infra.users.identity import User
else:
    from octop.infra.users.identity import User


# Sliding renew: when remaining life is below this fraction of configured TTL,
# middleware issues a fresh access token via ACCESS_TOKEN_RESPONSE_HEADER.
ACCESS_TOKEN_RESPONSE_HEADER = "X-Octop-Access-Token"
_SLIDING_RENEW_REMAINING_FRACTION = 1 / 3


# Paths that bypass JWT middleware (setup wizard, health, login).
_JWT_EXEMPT_PREFIXES = (
    "/api/setup/",
    "/api/health/",
    "/api/i18n/",
    "/api/connectors/oauth/callback",
    "/api/internal/mcp/",
    # Short-lived download links: the unguessable token is the credential.
    "/api/downloads/link/",
)
_JWT_EXEMPT_EXACT = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/captcha",
    "/api/auth/mfa/verify",
    "/api/auth/mfa/passkey/options",
    "/api/auth/passkey/login/options",
    "/api/auth/passkey/login/verify",
    "/api/auth/oidc/status",
    "/api/auth/oidc/start",
    "/api/auth/oidc/callback",
    "/api/auth/oidc/exchange",
    "/api/auth/oauth/status",
    "/api/auth/oauth/start",
    "/api/auth/oauth/callback",
    "/api/auth/oauth/exchange",
    "/api/auth/ldap/status",
    "/api/auth/invite/validate",
    "/api/auth/invite/redeem",
    "/api/docs",
    "/api/openapi.json",
)


def is_jwt_exempt_path(path: str) -> bool:
    return path in _JWT_EXEMPT_EXACT or any(path.startswith(p) for p in _JWT_EXEMPT_PREFIXES)


def is_jwt_exempt_request(request: Request) -> bool:
    return is_jwt_exempt_path(request.url.path)


def get_server(request: Request) -> OctopServer:
    server: OctopServer = request.app.state.octop_server
    if not getattr(server, "_started", False):
        raise OctopError(ErrorCode.INTERNAL_ERROR, "server not started")
    return server


def require_database(server: OctopServer) -> None:
    """Raise when the control-plane DB has not been bound yet (deferred setup)."""
    if not server.database_bound:
        raise OctopError(
            ErrorCode.SETUP_REQUIRED,
            "control-plane database not configured yet",
            status=503,
        )


def extract_raw_token(
    *,
    authorization: str | None = None,
    access_token: str | None = None,
) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if access_token:
        return access_token
    return None


def _decode(server: OctopServer, token: str) -> dict[str, Any]:
    assert server.services is not None
    secret = server.services.secret_repo.get("jwt")
    if secret is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
    try:
        return decode_token(secret, token)
    except TokenExpired as exc:
        raise OctopError(ErrorCode.TOKEN_EXPIRED, "token expired") from exc
    except InvalidToken as exc:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid token") from exc


def resolve_user_from_token(server: OctopServer, token: str) -> User:
    payload = _decode(server, token)
    try:
        purpose = token_purpose(payload)
    except InvalidToken as exc:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid token") from exc
    # Fail closed: only access tokens are accepted on normal API paths.
    # Missing purpose ≡ access only while the user's mfa_version is still 0.
    assert server.services is not None
    assert server.user_manager is not None
    user = server.user_manager.get_by_id(int(payload["sub"]))
    if user is None:
        raise OctopError(ErrorCode.USER_DISABLED, "user not active")
    row = server.services.user_repo.get(user.id)
    current_version = int(row.mfa_version) if row is not None else 0
    if purpose is None:
        if current_version != 0:
            raise OctopError(ErrorCode.AUTH_FAILED, "invalid token")
    elif purpose != PURPOSE_ACCESS:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid token")
    try:
        claim_version = token_mfa_version(payload)
    except InvalidToken as exc:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid token") from exc
    if claim_version != current_version:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid token")
    return user


def maybe_sliding_renew_token(server: OctopServer, token: str, user: User) -> str | None:
    """Return a fresh access token when ``token`` is past the sliding renew threshold.

    Threshold is one-third of ``access_token_ttl_seconds`` remaining. Active clients
    that pick up ``ACCESS_TOKEN_RESPONSE_HEADER`` stay signed in without re-login.
    """
    assert server.services is not None
    payload = _decode(server, token)
    try:
        purpose = token_purpose(payload)
    except InvalidToken as exc:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid token") from exc
    if purpose is not None and purpose != PURPOSE_ACCESS:
        return None
    if purpose is None:
        row = server.services.user_repo.get(user.id)
        if row is not None and int(row.mfa_version) != 0:
            return None
    ttl = int(server.services.config.access_token_ttl_seconds)
    remaining = int(payload["exp"]) - int(time.time())
    threshold = max(1, int(ttl * _SLIDING_RENEW_REMAINING_FRACTION))
    if remaining >= threshold:
        return None
    secret = server.services.secret_repo.get("jwt")
    if secret is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
    row = server.services.user_repo.get(user.id)
    mfa_version = int(row.mfa_version) if row is not None else 0
    return sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_ACCESS,
        ttl_seconds=ttl,
        mfa_version=mfa_version,
    )


def authenticate_request(request: Request, server: OctopServer) -> User:
    raw = extract_raw_token(
        authorization=request.headers.get("authorization"),
        access_token=request.query_params.get("access_token"),
    )
    if not raw:
        raise OctopError(ErrorCode.AUTH_FAILED, "missing credentials")
    return resolve_user_from_token(server, raw)


async def current_user(
    request: Request,
    server: OctopServer = Depends(get_server),
    authorization: str | None = Header(None),
    access_token: str | None = Query(None),
) -> User:
    cached = getattr(request.state, "octop_user", None)
    if cached is not None:
        return cast("User", cached)
    raw = extract_raw_token(authorization=authorization, access_token=access_token)
    if not raw:
        raise OctopError(ErrorCode.AUTH_FAILED, "missing credentials")
    return resolve_user_from_token(server, raw)


def require_permission(key: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: require the module permission ``key``.

    ``admin`` is bypassed inside ``user_has_permission``. Unknown keys fail
    fast at construction so typos cannot silently grant access.
    """
    if key not in PERMISSIONS:
        raise RuntimeError(f"unknown permission key: {key}")

    async def _dep(user: User = Depends(current_user)) -> User:
        if not user_has_permission(user, key):
            raise OctopError(
                ErrorCode.FORBIDDEN,
                "permission required",
                details={"permission": key},
            )
        return user

    return _dep


def require_admin() -> Callable[..., Awaitable[User]]:
    """Dependency factory: require the admin role (no module key)."""

    async def _dep(user: User = Depends(current_user)) -> User:
        if not user.is_admin:
            raise OctopError(ErrorCode.FORBIDDEN, "admin required")
        return user

    return _dep
