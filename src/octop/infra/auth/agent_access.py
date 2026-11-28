"""What an agent may do with the API when it acts as the conversation's user.

The ``octop_api`` tool mints a short-lived ``agent`` token for the user of the
current turn and calls the API with it. That token is never shown to the model.
The API accepts it only inside the boundary below, so a prompt-injected agent
cannot sign in, change credentials, run setup, or mint more tokens, even when
the user is an admin.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

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

# General settings endpoints that can also change TLS or sign-in security
# (``config.json`` form and raw text, captcha, WebAuthn). Agents may read them.
_DENIED_WRITE_PREFIXES = (
    "/api/admin/app-config",
    "/api/settings/captcha",
    "/api/settings/webauthn",
)

READ_METHODS = frozenset({"GET", "HEAD"})
# Reads inside a denied prefix that an agent still needs (who am I talking to).
_ALLOWED_READS = frozenset({"/api/auth/me"})


def routed_path(path: str) -> str | None:
    """The path the router will match for a request target, or ``None`` if it is unsafe.

    Drops the query and fragment and percent-decodes the way the ASGI server
    does, so ``/api/%61uth/login`` is checked as ``/api/auth/login``. Dot
    segments, empty segments, backslashes, and control characters are refused
    instead of guessing how they would be resolved.
    """
    decoded = unquote(path.split("?", 1)[0].split("#", 1)[0])
    if "\\" in decoded or "//" in decoded:
        return None
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in decoded):
        return None
    if any(seg in (".", "..") for seg in decoded.split("/")):
        return None
    return decoded


def agent_request_allowed(method: str, path: str) -> bool:
    """Return whether an ``agent`` token may call ``method path``.

    ``path`` is the routed (decoded) path; pass a raw request target through
    :func:`routed_path` first.
    """
    if not path.startswith("/api/") or ".." in path:
        return False
    verb = method.upper()
    if verb in READ_METHODS and path in _ALLOWED_READS:
        return True
    if any(path == p.rstrip("/") or path.startswith(p) for p in _DENIED_PREFIXES):
        return False
    if verb not in READ_METHODS and any(
        path == p or path.startswith(p + "/") for p in _DENIED_WRITE_PREFIXES
    ):
        return False
    segments = {seg.lower() for seg in path.split("/") if seg}
    if segments & _DENIED_SEGMENTS:
        return False
    return verb in READ_METHODS | {"POST", "PUT", "PATCH", "DELETE"}


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
