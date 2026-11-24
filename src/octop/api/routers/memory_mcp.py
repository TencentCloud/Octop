"""Manage shared Memory credentials through the existing Octop token API."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, overload

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator, model_validator

from octop.api.common.agent import assert_agent_access_row
from octop.api.deps import current_user, get_server, require_permission
from octop.api.routers.memory_sharing import memory_client_base, require_loaded_session
from octop.infra.agents import codex_memory_review, memory_sharing
from octop.infra.agents.memory_default_space import default_space_for
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(
    prefix="/memory-mcp/tokens",
    dependencies=[
        Depends(require_permission("memory")),
        Depends(require_loaded_session),
    ],
)

_LEGACY_SCOPES = ("read", "write", "review")


class TokenCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expert_ids: list[str] | None = None
    space_id: str | None = Field(default=None, min_length=1, max_length=128)
    scopes: list[Literal["read", "write"]] | None = Field(default=None, max_length=2)

    @field_validator("name")
    @classmethod
    def _client_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("client name is required")
        return name

    @model_validator(mode="after")
    def _scope_and_target(self) -> TokenCreateBody:
        if self.space_id is not None:
            if self.expert_ids:
                raise ValueError("choose a space or a default expert, not both")
            if self.scopes is None:
                raise ValueError("choose read-only or read/write access")
        if self.scopes is not None and (
            "read" not in self.scopes or len(set(self.scopes)) != len(self.scopes)
        ):
            raise ValueError("choose read-only or read/write access")
        return self


class TokenPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    expert_ids: list[str] | None = None
    disabled_clients: list[str] | None = None

    @model_validator(mode="after")
    def _require_a_field(self) -> TokenPatchBody:
        if not self.model_fields_set.intersection({"name", "expert_ids", "disabled_clients"}):
            raise ValueError("provide name and/or expert_ids and/or disabled_clients")
        return self


class TokenOut(BaseModel):
    token_id: str
    name: str
    expert_ids: list[str] | None = None
    space_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    disabled_clients: list[str] | None = None
    client_stats: dict[str, dict[str, Any]] | None = None
    token_hint: str
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None
    mcp_url: str = ""


class TokenCreated(TokenOut):
    token: str


class TokenRevoked(BaseModel):
    revoked: bool


def _require_session(user: User) -> memory_sharing.SharingSession:
    session = memory_sharing.get_session(int(user.id))
    if session is None:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "请在「共享记忆」里用一次性码连接记忆空间",
        )
    return session


def _experts(server: OctopServer, user: User) -> list[dict[str, Any]]:
    """每个专家 → 它原来的记忆库空间。"""
    assert server.app_runtime is not None
    out: list[dict[str, Any]] = []
    for row in server.app_runtime.agent_registry.list_rows():
        try:
            assert_agent_access_row(
                row, user, repos=server.services.repos if server.services else None
            )
        except OctopError:
            continue
        cfg: dict[str, Any]
        try:
            parsed = json.loads(row.config_json or "{}")
            cfg = parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            cfg = {}
        workspace = Path(cfg.get("workspace_dir") or server.paths.agent_workspace(row.agent_id))
        space = default_space_for(
            agent_id=row.agent_id,
            cfg=cfg,
            octop_config=server.config,
            workspace_dir=workspace,
        )
        out.append(
            {
                "agent_id": row.agent_id,
                "name": row.name,
                "space_id": space.space_id,
                "usable": space.usable,
                "reason": space.reason,
                "backend": space.backend,
                "backend_config": space.backend_config,
            }
        )
    return out


def _expert_by_space(experts: list[dict[str, Any]], space_id: str) -> dict[str, Any] | None:
    return next((item for item in experts if item["space_id"] == space_id), None)


@overload
def _to_out(token: dict[str, Any], experts: list[dict[str, Any]], client_base: str) -> TokenOut: ...


@overload
def _to_out(
    token: dict[str, Any], experts: list[dict[str, Any]], client_base: str, *, plaintext: str
) -> TokenCreated: ...


def _to_out(
    token: dict[str, Any],
    experts: list[dict[str, Any]],
    client_base: str,
    *,
    plaintext: str | None = None,
) -> TokenOut:
    expert = _expert_by_space(experts, str(token.get("space_id") or ""))
    data: dict[str, Any] = {
        "token_id": token["token_id"],
        "name": token.get("client_name") or "",
        "expert_ids": [expert["agent_id"]] if expert else None,
        "space_id": token.get("space_id"),
        "scopes": token.get("scopes") or [],
        "disabled_clients": token.get("disabled_clients") or None,
        "client_stats": token.get("client_stats") or None,
        "token_hint": token.get("token_hint") or "",
        "created_at": token.get("created_at") or "",
        "last_used_at": token.get("last_used_at"),
        "revoked_at": token.get("revoked_at"),
        "mcp_url": f"{client_base}/mcp/",
    }
    if plaintext is not None:
        return TokenCreated(**data, token=plaintext)
    return TokenOut(**data)


def _space_for_expert(user: User, experts: list[dict[str, Any]], agent_id: str) -> dict[str, Any]:
    expert = next((item for item in experts if item["agent_id"] == agent_id), None)
    if expert is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    if not expert["usable"]:
        raise OctopError(ErrorCode.AGENT_FAILED, str(expert["reason"]))
    memory_sharing.ensure_space(
        int(user.id),
        expert["space_id"],
        expert["backend"],
        expert["backend_config"],
        display_name=f"{expert['name']} 的记忆",
    )
    return expert


def _legacy_space_ids(
    experts: list[dict[str, Any]], session: memory_sharing.SharingSession
) -> list[str]:
    return list(
        dict.fromkeys(
            item["space_id"] for item in experts if session.space_id in {"*", item["space_id"]}
        )
    )


@router.get("", response_model=list[TokenOut], summary="List memory MCP tokens")
def list_tokens(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
    client_base: str = Depends(memory_client_base),
    space_id: str | None = None,
) -> list[TokenOut]:
    session = _require_session(user)
    experts = _experts(server, user) if space_id is None else []
    spaces = [space_id] if space_id is not None else _legacy_space_ids(experts, session)
    out: list[TokenOut] = []
    for space in spaces:
        try:
            payload = memory_sharing.list_tokens_in(int(user.id), space)
        except OctopError as exc:
            if space_id is None and exc.code == ErrorCode.NOT_FOUND:
                continue
            raise
        for token in payload.get("tokens", []):
            out.append(_to_out(token, experts, client_base))
    out.sort(key=lambda item: item.created_at, reverse=True)
    return out


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TokenCreated)
def create_token(
    body: TokenCreateBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
    client_base: str = Depends(memory_client_base),
) -> TokenCreated:
    _require_session(user)
    experts: list[dict[str, Any]] = []
    space_id = body.space_id
    if space_id is None:
        experts = _experts(server, user)
        agent_id = (body.expert_ids or [""])[0]
        if not agent_id and experts:
            agent_id = experts[0]["agent_id"]
        if not agent_id:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "请选择一个绑定专家")
        space_id = _space_for_expert(user, experts, agent_id)["space_id"]
    scopes: list[str] = list(body.scopes) if body.scopes is not None else list(_LEGACY_SCOPES)
    created = memory_sharing.create_token_in(int(user.id), space_id, body.name, scopes)
    # #59's create response omits row metadata. Keep the one-time secret in
    # the HTTP response even if a separate list request would have failed.
    row = {
        "space_id": space_id,
        "scopes": scopes,
        "created_at": datetime.now(UTC).isoformat(),
        **created,
    }
    return _to_out(row, experts, client_base, plaintext=created["token"])


@router.patch("/{token_id}", response_model=TokenOut)
def patch_token(
    token_id: str,
    body: TokenPatchBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
    client_base: str = Depends(memory_client_base),
) -> TokenOut:
    _require_session(user)
    experts = _experts(server, user)
    space_id: str | None = None
    if body.expert_ids is not None:
        agent_id = (body.expert_ids or [""])[0]
        if not agent_id and experts:
            agent_id = experts[0]["agent_id"]
        if not agent_id:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, "请选择一个绑定专家")
        space_id = _space_for_expert(user, experts, agent_id)["space_id"]
    updated = memory_sharing.patch_token(
        int(user.id),
        token_id,
        client_name=body.name,
        disabled_clients=body.disabled_clients,
        space_id=space_id,
    )
    return _to_out(updated, experts, client_base)


@router.post("/{token_id}/rotate", response_model=TokenCreated)
def rotate_token(
    token_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
    client_base: str = Depends(memory_client_base),
    space_id: str | None = None,
) -> TokenCreated:
    session = _require_session(user)
    experts = _experts(server, user) if space_id is None else []
    spaces = [space_id] if space_id is not None else _legacy_space_ids(experts, session)
    for space in spaces:
        try:
            payload = memory_sharing.list_tokens_in(int(user.id), space)
        except OctopError as exc:
            if space_id is None and exc.code == ErrorCode.NOT_FOUND:
                continue
            raise
        for token in payload.get("tokens", []):
            if token["token_id"] == token_id:
                rotated = memory_sharing.rotate_token(int(user.id), token_id)
                return _to_out(token | rotated, experts, client_base, plaintext=rotated["token"])
    raise OctopError(ErrorCode.NOT_FOUND, "token not found in the requested memory space")


@router.delete("/{token_id}", response_model=TokenRevoked)
def revoke_token(
    token_id: str,
    user: User = Depends(current_user),
) -> TokenRevoked:
    _require_session(user)
    result = memory_sharing.revoke_token(int(user.id), token_id)
    return TokenRevoked(revoked=bool(result.get("revoked")))


class CodexModelChoice(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=512)


def _require_writable_token(user: User, token_id: str, space_id: str) -> None:
    records = memory_sharing.list_tokens_in(user.id, space_id)
    if not any(
        t["token_id"] == token_id
        and not t.get("revoked_at")
        and "write" in t.get("scopes", [])
        and "read" in t.get("scopes", [])
        for t in records.get("tokens", [])
    ):
        raise OctopError(
            ErrorCode.FORBIDDEN, "An active read/write token in this space is required"
        )


@router.get("/{token_id}/codex-model")
def get_codex_model(
    token_id: str,
    space_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> CodexModelChoice:
    _require_writable_token(user, token_id, space_id)
    assert server.services is not None
    saved = server.services.settings_repo.get(codex_memory_review.binding_key(token_id, space_id))
    return CodexModelChoice(model=json.loads(saved)["model"] if saved else None)


@router.put("/{token_id}/codex-model")
def set_codex_model(
    token_id: str,
    space_id: str,
    body: CodexModelChoice,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> CodexModelChoice:
    _require_writable_token(user, token_id, space_id)
    assert server.services is not None
    key = codex_memory_review.binding_key(token_id, space_id)
    if body.model is None:
        server.services.settings_repo.delete(key)
    else:
        codex_memory_review.check_model(server, user, body.model)
        server.services.settings_repo.set(
            key, json.dumps({"model": body.model, "user_id": user.id})
        )
    return body
