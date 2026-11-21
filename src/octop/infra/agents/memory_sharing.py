"""Client for the standalone octop-memory admin API.

Octop no longer hosts the memory MCP server: it keeps only the expert → space
binding and a per-user management session, and proxies space/token operations to
``octop-memory``. The session is per-user, in-memory and short-lived; a long-lived
session can be added later without changing this interface.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from octop.infra.errors import ErrorCode, OctopError

_DEFAULT_URL = "http://127.0.0.1:8790"


def service_url() -> str:
    return (os.environ.get("OCTOP_MEMORY_SERVICE_URL") or _DEFAULT_URL).rstrip("/")


@dataclass(frozen=True)
class SharingSession:
    token: str
    space_id: str
    scopes: tuple[str, ...]
    expires_at: str
    stored_at: float


class _SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_user: dict[int, SharingSession] = {}

    def set(self, user_id: int, session: SharingSession) -> None:
        with self._lock:
            self._by_user[user_id] = session

    def get(self, user_id: int) -> SharingSession | None:
        with self._lock:
            session = self._by_user.get(user_id)
        if session is None:
            return None
        # Prefer the upstream expiry; fall back to a 7-day local guard.
        try:
            from datetime import datetime

            if datetime.fromisoformat(session.expires_at) <= datetime.now().astimezone():
                self.clear(user_id)
                return None
        except ValueError:
            if time.time() - session.stored_at > 7 * 86400:
                self.clear(user_id)
                return None
        return session

    def clear(self, user_id: int) -> None:
        with self._lock:
            self._by_user.pop(user_id, None)


_sessions = _SessionStore()


def get_session(user_id: int) -> SharingSession | None:
    return _sessions.get(user_id)


def clear_session(user_id: int) -> None:
    _sessions.clear(user_id)


def adopt_session(user_id: int, session: SharingSession) -> None:
    """Fill the in-process cache from a persisted (encrypted) session."""
    _sessions.set(user_id, session)


def _request(method: str, path: str, *, session: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"accept": "application/json"}
    if session:
        headers["authorization"] = f"Bearer {session}"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.request(
                method,
                f"{service_url()}{path}",
                headers=headers,
                json=body,
            )
    except httpx.HTTPError as exc:
        raise OctopError(
            ErrorCode.BAD_REQUEST,
            f"memory service unreachable: {exc}",
            details={"service": service_url()},
        ) from exc
    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text[:300]
        raise OctopError(
            ErrorCode.BAD_REQUEST,
            f"memory service rejected the request: {detail}",
            details={"status": response.status_code},
        )
    if not response.content:
        return {}
    return response.json()


def exchange_code(user_id: int, code: str) -> SharingSession:
    payload = _request("POST", "/api/admin/session/exchange", body={"code": code})
    token = str(payload.get("session_token") or "")
    if not token:
        raise OctopError(ErrorCode.BAD_REQUEST, "memory service returned no session token")
    session = SharingSession(
        token=token,
        space_id=str(payload.get("space_id") or ""),
        scopes=tuple(payload.get("scopes") or ()),
        expires_at=str(payload.get("expires_at") or ""),
        stored_at=time.time(),
    )
    _sessions.set(user_id, session)
    return session


def _session_or_fail(user_id: int) -> SharingSession:
    session = get_session(user_id)
    if session is None:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "no memory sharing session; connect a space first (octop-memory auth code)",
        )
    return session


def list_spaces(user_id: int) -> dict[str, Any]:
    session = _session_or_fail(user_id)
    return _request("GET", "/api/admin/spaces", session=session.token)


def list_tokens(user_id: int) -> dict[str, Any]:
    session = _session_or_fail(user_id)
    return _request(
        "GET", f"/api/admin/spaces/{session.space_id}/tokens", session=session.token
    )


def create_token(user_id: int, client_name: str, scopes: list[str]) -> dict[str, Any]:
    session = _session_or_fail(user_id)
    return _request(
        "POST",
        f"/api/admin/spaces/{session.space_id}/tokens",
        session=session.token,
        body={"client_name": client_name, "scopes": scopes},
    )


def rotate_token(user_id: int, token_id: str) -> dict[str, Any]:
    session = _session_or_fail(user_id)
    return _request(
        "POST", f"/api/admin/tokens/{token_id}/rotate", session=session.token
    )


def revoke_token(user_id: int, token_id: str) -> dict[str, Any]:
    session = _session_or_fail(user_id)
    return _request("DELETE", f"/api/admin/tokens/{token_id}", session=session.token)


def list_clients(user_id: int) -> dict[str, Any]:
    session = _session_or_fail(user_id)
    return _request(
        "GET", f"/api/admin/spaces/{session.space_id}/clients", session=session.token
    )


__all__ = [
    "SharingSession",
    "clear_session",
    "create_token",
    "exchange_code",
    "get_session",
    "list_clients",
    "list_spaces",
    "list_tokens",
    "revoke_token",
    "rotate_token",
    "service_url",
]
