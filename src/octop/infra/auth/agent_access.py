"""What an agent may do with the API when it acts as the conversation's user.

The ``octop_api`` tool mints a short-lived ``agent`` token for the user of the
current turn and calls the API with it. That token is never shown to the model.
The API accepts it only inside the boundary below, so a prompt-injected agent
cannot sign in, change credentials, run setup, or mint more tokens, even when
the user is an admin.
"""

from __future__ import annotations

from typing import Any

from octop.infra.auth.tokens import AGENT_TOKEN_TTL_SECONDS, PURPOSE_AGENT, sign_token

# Credentials, sign-in, and instance setup stay with the person at the keyboard.
_DENIED_PREFIXES = (
    "/api/auth/",
    "/api/setup",
    "/api/internal/",
    "/api/admin/security",
    "/api/admin/tls",
    "/api/terminal",
)
# Path segments that change how someone signs in, wherever they appear
# (``/api/users/{id}/reset-password``, ``/api/users/{id}/mfa``, …).
_DENIED_SEGMENTS = frozenset({"password", "reset-password", "mfa", "passkey", "passkeys"})

READ_METHODS = frozenset({"GET", "HEAD"})
# Reads inside a denied prefix that an agent still needs (who am I talking to).
_ALLOWED_READS = frozenset({"/api/auth/me"})


def agent_request_allowed(method: str, path: str) -> bool:
    """Return whether an ``agent`` token may call ``method path``."""
    if not path.startswith("/api/") or ".." in path:
        return False
    if method.upper() in READ_METHODS and path in _ALLOWED_READS:
        return True
    if any(path == p.rstrip("/") or path.startswith(p) for p in _DENIED_PREFIXES):
        return False
    segments = {seg.lower() for seg in path.split("/") if seg}
    if segments & _DENIED_SEGMENTS:
        return False
    return method.upper() in READ_METHODS | {"POST", "PUT", "PATCH", "DELETE"}


def mint_agent_token(services: Any, *, user_id: int, agent_id: str) -> str:
    """Sign an ``agent`` token for an active user, bound to their current credentials."""
    row = services.user_repo.get(user_id)
    if row is None or int(row.disabled):
        raise PermissionError("user not active")
    secret = services.secret_repo.get("jwt")
    if secret is None:
        raise RuntimeError("jwt secret missing")
    return sign_token(
        secret,
        sub=int(row.id),
        uname=str(row.username),
        role=str(row.role),
        purpose=PURPOSE_AGENT,
        ttl_seconds=AGENT_TOKEN_TTL_SECONDS,
        mfa_version=int(row.mfa_version),
        password_version=int(row.password_version),
        agent_id=agent_id,
    )
