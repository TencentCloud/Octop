"""Desktop device sessions — renew a JWT without a password.

Desktop builds run without an account system: the initial admin gets a
server-minted password nobody types, so ``POST /api/auth/login`` is not a path a
desktop user can take. Instead the shell keeps a per-install device token in the
OS keychain — or, on a host without one, only in memory for the current launch —
and trades it for a normal JWT when the previous one expired.

Three properties keep this from being a back door:

* only the desktop shell can use it (``OCTOP_DESKTOP_SHELL=1``),
* only over loopback, and
* only with a token whose SHA-256 matches the one registered by an
  already-authenticated request.

The token itself never reaches the renderer: the shell generates it, stores it
encrypted (or holds it in memory when the host has no keychain), and talks to
these endpoints from the main process.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, sign_token
from octop.infra.desktop import desktop_shell_enabled
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter()

# ``secrets`` row holding the registered hash; same table as the JWT key.
_SECRET_KEY = "desktop_device"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})
_MAX_FAILURES = 5
_FAILURE_WINDOW_SECONDS = 300
_failures: dict[str, list[float]] = {}


class RegisterBody(BaseModel):
    device_token: str = Field(min_length=32, max_length=200)
    label: str | None = Field(
        default=None,
        max_length=64,
        description="Human-readable device label (platform/arch), for support.",
    )


class DeviceTokenBody(BaseModel):
    device_token: str = Field(min_length=32, max_length=200)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _require_desktop_loopback(request: Request) -> str:
    """Refuse unless this is the desktop sidecar answering its own shell."""
    if not desktop_shell_enabled():
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "device sessions require the desktop shell",
            status=403,
        )
    host = _client_host(request)
    if host not in _LOOPBACK_HOSTS:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "device sessions are loopback only",
            status=403,
        )
    return host


def _recent_failures(host: str) -> int:
    now = time.time()
    stamps = [t for t in _failures.get(host, []) if now - t < _FAILURE_WINDOW_SECONDS]
    _failures[host] = stamps
    return len(stamps)


def _record_failure(host: str) -> None:
    _failures.setdefault(host, []).append(time.time())


def _raise_if_throttled(host: str) -> None:
    if _recent_failures(host) < _MAX_FAILURES:
        return
    logger.warning("desktop device token rejected: too many attempts from %s", host)
    raise OctopError(
        ErrorCode.LOGIN_LOCKED,
        "too many device token attempts",
        details={"retry_after_seconds": _FAILURE_WINDOW_SECONDS},
    )


def _read_secret(server: Any) -> dict[str, Any] | None:
    if server.services is None:
        return None
    raw = server.services.secret_repo.get(_SECRET_KEY)
    if raw is None:
        return None
    try:
        parsed = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("desktop device secret is malformed; ignoring it")
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_secret(server: Any, payload: dict[str, Any]) -> None:
    """Upsert the single ``desktop_device`` row (one install, one device)."""
    repo = server.services.secret_repo
    blob = json.dumps(payload).encode("utf-8")
    if repo.get(_SECRET_KEY) is None:
        repo.get_or_create(_SECRET_KEY, lambda: blob)
    else:
        repo.rotate(_SECRET_KEY, blob)


@router.post("/device/register", summary="Register this device's session credential")
async def register_device(
    body: RegisterBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Bind a shell-generated device token to the signed-in user.

    Called once per shell install, with a valid JWT — which is why it is *not*
    exempt from authentication. Re-registering replaces the previous token, so a
    second machine (or a reinstall) takes over and the old token stops working.
    """
    _require_desktop_loopback(request)
    payload = {
        "v": 1,
        "user_id": int(user.id),
        "hash": _digest(body.device_token),
        "label": body.label or "",
        "created_at": int(time.time()),
    }
    _write_secret(server, payload)
    server.services.audit_repo.write(
        actor=user.username, action="auth.device_registered", target=body.label or "desktop"
    )
    return {"ok": True, "username": user.username}


@router.post("/device/token", summary="Exchange the device credential for an access token")
async def device_token(
    body: DeviceTokenBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Mint a JWT for the user bound to this device token.

    The only unauthenticated endpoint that issues a session, so it is guarded by
    the shell flag, the loopback peer, a constant-time digest compare, and a
    per-host failure throttle.
    """
    host = _require_desktop_loopback(request)
    _raise_if_throttled(host)

    stored = _read_secret(server)
    if not stored or stored.get("revoked"):
        _record_failure(host)
        raise OctopError(ErrorCode.AUTH_FAILED, "no device credential registered")
    expected = str(stored.get("hash") or "")
    if not expected or not hmac.compare_digest(expected, _digest(body.device_token)):
        _record_failure(host)
        raise OctopError(ErrorCode.AUTH_FAILED, "device credential mismatch")

    user = server.user_manager.get_by_id(int(stored.get("user_id") or 0))
    if user is None:
        _record_failure(host)
        raise OctopError(ErrorCode.USER_DISABLED, "user not active")

    secret = server.services.secret_repo.get("jwt")
    ttl = int(server.services.config.access_token_ttl_seconds)
    token = sign_token(secret, sub=user.id, uname=user.username, role=user.role, ttl_seconds=ttl)
    _failures.pop(host, None)
    logger.info("desktop device session renewed for %s", user.username)
    return {"access_token": token, "token_type": "Bearer", "expires_in": ttl}


@router.post("/device/revoke", summary="Revoke this install's device credential")
async def revoke_device(
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Invalidate the registered device token (e.g. a lost laptop).

    The JWT in hand keeps working until it expires; only renewal stops.
    """
    _require_desktop_loopback(request)
    _write_secret(server, {"v": 1, "revoked": True, "revoked_at": int(time.time())})
    server.services.audit_repo.write(actor=user.username, action="auth.device_revoked")
    return {"ok": True}
