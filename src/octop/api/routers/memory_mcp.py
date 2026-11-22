"""终端接入：兼容旧 ``/memory-mcp/tokens`` 形态，底层走 octop-memory。

旧面板的交互保持不变（一个 token 绑定一个专家、按客户端统计/启停、
接入配置、切换专家、撤销），只是 token 真正保存在独立记忆服务里。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator

from octop.api.common.agent import assert_agent_access_row
from octop.api.deps import current_user, get_server, require_permission
from octop.api.routers.memory_sharing import require_loaded_session
from octop.infra.agents import memory_sharing
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

SCOPES = ["read", "write", "review"]


class TokenCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expert_ids: list[str] | None = None


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


def _require_session(user: User) -> None:
    if memory_sharing.get_session(int(user.id)) is None:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "还没有连接记忆空间：请在「共享记忆」里用一次性码连接（--all 可管理全部专家）",
        )


def _experts(server: OctopServer, user: User) -> list[dict[str, Any]]:
    """每个专家 → 它原来的记忆库空间。"""
    assert server.app_runtime is not None
    out: list[dict[str, Any]] = []
    for row in server.app_runtime.agent_registry.list_rows():
        try:
            assert_agent_access_row(row, user, repos=server.services.repos if server.services else None)
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


def _mcp_url() -> str:
    return f"{memory_sharing.service_url()}/mcp/"


def _to_out(
    token: dict[str, Any], experts: list[dict[str, Any]], *, plaintext: str | None = None
) -> TokenOut:
    expert = _expert_by_space(experts, str(token.get("space_id") or ""))
    data: dict[str, Any] = {
        "token_id": token["token_id"],
        "name": token.get("client_name") or "",
        "expert_ids": [expert["agent_id"]] if expert else None,
        "disabled_clients": token.get("disabled_clients") or None,
        "client_stats": token.get("client_stats") or None,
        "token_hint": token.get("token_hint") or "",
        "created_at": token.get("created_at") or "",
        "last_used_at": token.get("last_used_at"),
        "revoked_at": token.get("revoked_at"),
        "mcp_url": _mcp_url(),
    }
    if plaintext is not None:
        return TokenCreated(**data, token=plaintext)
    return TokenOut(**data)


def _space_for_expert(
    user: User, experts: list[dict[str, Any]], agent_id: str
) -> dict[str, Any]:
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


@router.get("", response_model=list[TokenOut], summary="List memory MCP tokens")
def list_tokens(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> list[TokenOut]:
    _require_session(user)
    experts = _experts(server, user)
    out: list[TokenOut] = []
    for space_id in {item["space_id"] for item in experts}:
        try:
            payload = memory_sharing.list_tokens_in(int(user.id), space_id)
        except OctopError:
            continue
        for token in payload.get("tokens", []):
            out.append(_to_out(token, experts))
    out.sort(key=lambda item: item.created_at, reverse=True)
    return out


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TokenCreated)
def create_token(
    body: TokenCreateBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> TokenCreated:
    _require_session(user)
    experts = _experts(server, user)
    agent_id = (body.expert_ids or [""])[0]
    if not agent_id and experts:
        agent_id = experts[0]["agent_id"]
    if not agent_id:
        raise OctopError(ErrorCode.AGENT_FAILED, "请选择一个绑定专家")
    expert = _space_for_expert(user, experts, agent_id)
    created = memory_sharing.create_token_in(
        int(user.id), expert["space_id"], body.name.strip(), SCOPES
    )
    payload = memory_sharing.list_tokens_in(int(user.id), expert["space_id"])
    row = next(
        (item for item in payload.get("tokens", []) if item["token_id"] == created["token_id"]),
        created,
    )
    return _to_out(row, experts, plaintext=created["token"])


@router.patch("/{token_id}", response_model=TokenOut)
def patch_token(
    token_id: str,
    body: TokenPatchBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
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
    return _to_out(updated, experts)


@router.post("/{token_id}/rotate", response_model=TokenCreated)
def rotate_token(
    token_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> TokenCreated:
    _require_session(user)
    experts = _experts(server, user)
    rotated = memory_sharing.rotate_token(int(user.id), token_id)
    for space in {item["space_id"] for item in experts}:
        payload = memory_sharing.list_tokens_in(int(user.id), space)
        for token in payload.get("tokens", []):
            if token["token_id"] == token_id:
                return _to_out(token, experts, plaintext=rotated["token"])
    raise OctopError(ErrorCode.NOT_FOUND, "token not found after rotate")


@router.delete("/{token_id}", response_model=TokenRevoked)
def revoke_token(
    token_id: str,
    user: User = Depends(current_user),
) -> TokenRevoked:
    _require_session(user)
    result = memory_sharing.revoke_token(int(user.id), token_id)
    return TokenRevoked(revoked=bool(result.get("revoked")))
