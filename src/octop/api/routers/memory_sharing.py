"""Memory sharing: connect Octop to a standalone octop-memory service.

The MCP server, tokens and spaces live in ``octop-memory``. Octop keeps:
- a per-user, short-lived management session (from a one-time code),
- the expert → space binding used by the memory panel.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_access_row
from octop.api.deps import current_user, get_server, require_permission
from octop.infra.agents import memory_sharing
from octop.infra.crypto.fernet import open_text, seal_text
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(
    prefix="/memory-sharing",
    dependencies=[Depends(require_permission("memory"))],
)

_SESSION_KEY = "memory_sharing.session.{user_id}"
_SECRET_PURPOSE = "memory_sharing_fernet"


def _save_session(server: OctopServer, user_id: int, session: Any) -> None:
    """Persist the management session encrypted at rest (survives restarts)."""
    repos = server.services.repos if server.services else None
    if repos is None:
        return
    payload = json.dumps(
        {
            "token": session.token,
            "space_id": session.space_id,
            "scopes": list(session.scopes),
            "expires_at": session.expires_at,
            "stored_at": session.stored_at,
        },
        ensure_ascii=False,
    )
    sealed = seal_text(repos.secret_repo, _SECRET_PURPOSE, payload)
    if sealed is not None:
        repos.settings_repo.set(_SESSION_KEY.format(user_id=user_id), sealed)


def _load_session(server: OctopServer, user_id: int) -> None:
    repos = server.services.repos if server.services else None
    if repos is None or memory_sharing.get_session(user_id) is not None:
        return
    sealed = repos.settings_repo.get(_SESSION_KEY.format(user_id=user_id))
    raw = open_text(repos.secret_repo, _SECRET_PURPOSE, sealed)
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    session = memory_sharing.SharingSession(
        token=str(data.get("token") or ""),
        space_id=str(data.get("space_id") or ""),
        scopes=tuple(data.get("scopes") or ()),
        expires_at=str(data.get("expires_at") or ""),
        stored_at=float(data.get("stored_at") or 0),
    )
    if not session.token:
        return
    memory_sharing.adopt_session(user_id, session)


def _drop_session(server: OctopServer, user_id: int) -> None:
    repos = server.services.repos if server.services else None
    if repos is not None:
        repos.settings_repo.delete(_SESSION_KEY.format(user_id=user_id))
    memory_sharing.clear_session(user_id)


class ExchangeBody(BaseModel):
    code: str = Field(min_length=1, max_length=512)


class TokenCreateBody(BaseModel):
    client_name: str = Field(min_length=1, max_length=64)
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])


class BindBody(BaseModel):
    agent_id: str = Field(min_length=1)
    space_id: str = Field(min_length=1, max_length=128)


def _session_payload(user_id: int) -> dict[str, Any]:
    session = memory_sharing.get_session(user_id)
    if session is None:
        return {"connected": False}
    return {
        "connected": True,
        "space_id": session.space_id,
        "scopes": list(session.scopes),
        "expires_at": session.expires_at,
    }


@router.get("/session", summary="Current memory sharing session")
def get_session(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _load_session(server, int(user.id))
    return _session_payload(int(user.id))


@router.post("/session", summary="Exchange a one-time code for a management session")
def connect(
    body: ExchangeBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    session = memory_sharing.exchange_code(int(user.id), body.code)
    _save_session(server, int(user.id), session)
    return _session_payload(int(user.id))


@router.delete("/session", summary="Forget the local management session")
def disconnect(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _drop_session(server, int(user.id))
    return {"connected": False}


@router.get("/spaces", summary="Spaces visible to the management session")
def spaces(user: User = Depends(current_user)) -> dict[str, Any]:
    return memory_sharing.list_spaces(int(user.id))


@router.get("/tokens", summary="Tokens of the connected space")
def tokens(user: User = Depends(current_user)) -> dict[str, Any]:
    return memory_sharing.list_tokens(int(user.id))


@router.post("/tokens", summary="Issue a token for one client")
def create_token(
    body: TokenCreateBody,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return memory_sharing.create_token(int(user.id), body.client_name, body.scopes)


@router.post("/tokens/{token_id}/rotate", summary="Rotate a client token")
def rotate(token_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return memory_sharing.rotate_token(int(user.id), token_id)


@router.delete("/tokens/{token_id}", summary="Revoke a client token")
def revoke(token_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return memory_sharing.revoke_token(int(user.id), token_id)


@router.get("/clients", summary="Clients seen in the connected space")
def clients(user: User = Depends(current_user)) -> dict[str, Any]:
    return memory_sharing.list_clients(int(user.id))


@router.get("/binding/{agent_id}", summary="Space bound to an expert")
def binding(
    agent_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    row = _agent_row(server, agent_id)
    assert_agent_access_row(row, user, repos=server.services.repos if server.services else None)
    config = _parse_config(row.config_json)
    return {"agent_id": agent_id, "space_id": (config.get("memory_sharing") or {}).get("space_id")}


@router.post("/binding", summary="Bind an expert to a memory space")
async def bind(
    body: BindBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    row = _agent_row(server, body.agent_id)
    assert_agent_access_row(row, user, repos=server.services.repos if server.services else None)
    config = _parse_config(row.config_json)
    config["memory_sharing"] = {"space_id": body.space_id}
    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.update(
        body.agent_id, config_json=json.dumps(config)
    )
    return {"agent_id": body.agent_id, "space_id": body.space_id}


def _agent_row(server: OctopServer, agent_id: str) -> Any:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    return row


def _parse_config(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = ["router"]
