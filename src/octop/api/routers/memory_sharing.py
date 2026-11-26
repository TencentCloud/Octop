"""Memory sharing: connect Octop to a standalone octop-memory service.

The MCP server, tokens and spaces live in ``octop-memory``. Octop keeps:
- a per-user, short-lived management session (from a one-time code),
- the expert → space binding used by the memory panel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from shlex import quote
from typing import Any
from weakref import WeakValueDictionary

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from octop.api.common.agent import assert_agent_access_row, assert_agent_owner, user_owns_agent
from octop.api.common.public_base import resolve_public_base
from octop.api.deps import current_user, get_server, require_permission
from octop.infra.agents import memory_sharing
from octop.infra.agents.memory_shared_access import (
    ExpertBinding,
    get_expert_binding,
    save_expert_binding,
    supports_sharing,
)
from octop.infra.crypto.fernet import open_text, seal_text
from octop.infra.db.repos.agents import AgentRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.users.identity import User


def require_loaded_session(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> None:
    """Hydrate the per-user session from its encrypted row before any call."""
    _load_session(server, int(user.id))


router = APIRouter(
    prefix="/memory-sharing",
    dependencies=[
        Depends(require_permission("memory")),
        Depends(require_loaded_session),
    ],
)

_SESSION_KEY = "memory_sharing.session.{user_id}"
_SECRET_PURPOSE = "memory_sharing_fernet"
_binding_locks: WeakValueDictionary[tuple[int, str], asyncio.Lock] = WeakValueDictionary()
logger = logging.getLogger(__name__)


def _save_session(server: OctopServer, user_id: int, session: Any) -> bool:
    """Persist the management session encrypted at rest (survives restarts).

    返回是否真的写成功；失败时调用方应在响应里标明 ``persisted: false``，
    否则用户会以为会话已保存、重启后却要重新要一次性码。
    """
    repos = server.services.repos if server.services else None
    if repos is None:
        return False
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
    if sealed is None:
        return False
    repos.settings_repo.set(_SESSION_KEY.format(user_id=user_id), sealed)
    return True


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


def _require_session(server: OctopServer, user_id: int) -> None:
    """所有依赖管理会话的路由都要先调它：把加密持久化的会话恢复进内存。

    只调一次 ``get_session`` 是不够的 —— 进程重启后内存里没有会话，
    ``tokens``/``create_token`` 这些接口会直接 403，而用户明明已经连过。
    """
    _load_session(server, user_id)


def _drop_session(server: OctopServer, user_id: int) -> None:
    repos = server.services.repos if server.services else None
    if repos is not None:
        repos.settings_repo.delete(_SESSION_KEY.format(user_id=user_id))
    memory_sharing.clear_session(user_id)


class ExchangeBody(BaseModel):
    code: str = Field(min_length=1, max_length=512)


class TokenCreateBody(BaseModel):
    client_name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])

    @field_validator("scopes")
    @classmethod
    def _known_scopes(cls, value: list[str]) -> list[str]:
        allowed = {"read", "write"}
        unknown = [s for s in value if s not in allowed]
        if unknown:
            raise ValueError(f"unknown scopes: {', '.join(unknown)}（只支持 read/write）")
        return value or ["read", "write"]


class BindBody(BaseModel):
    agent_id: str = Field(min_length=1)
    space_id: str | None = Field(min_length=1, max_length=128)


def memory_client_base(request: Request) -> str:
    """Use the dashboard origin when the shared ingress forwards /mcp/."""
    if os.environ.get("OCTOP_MEMORY_SAME_ORIGIN") == "1":
        return resolve_public_base(request)
    return memory_sharing.service_url()


def _session_payload(user_id: int, client_base: str) -> dict[str, Any]:
    session = memory_sharing.get_session(user_id)
    if session is None:
        return {"connected": False}
    return {
        "connected": True,
        "space_id": session.space_id,
        "scopes": list(session.scopes),
        "expires_at": session.expires_at,
        # 客户端接入指引要用到（S3）：MCP 地址 = f"{base_url}/mcp/"
        "base_url": client_base,
    }


@router.get("/session", summary="Current memory sharing session")
def get_session(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
    client_base: str = Depends(memory_client_base),
) -> dict[str, Any]:
    _load_session(server, int(user.id))
    return _session_payload(int(user.id), client_base)


@router.post("/session", summary="Exchange a one-time code for a management session")
def connect(
    body: ExchangeBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
    client_base: str = Depends(memory_client_base),
) -> dict[str, Any]:
    session = memory_sharing.exchange_code(int(user.id), body.code)
    persisted = _save_session(server, int(user.id), session)
    payload = _session_payload(int(user.id), client_base)
    # persisted=false 时要让前端知道「重启后还得重连」，否则用户以为已保存
    payload["persisted"] = persisted
    return payload


@router.delete("/session", summary="Forget the local management session")
def disconnect(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _drop_session(server, int(user.id))
    return {"connected": False}


# ---------------------------------------------------------------------------
# 终端接入：由 Octop 托管安装脚本
#
# 为什么不直接让用户从 raw.githubusercontent.com 拉（威胁模型 R1）：
# ① 内网常常拉不到；② ``main`` 分支会漂移，装了什么无法复现。
# 所以这里只托管一个**薄壳**：固定 tag、可指向内网镜像、并且**绝不签发 token**
# （token 一律由面板通过 POST 单独签发，见 R7 —— GET 不产生副作用）。
# ---------------------------------------------------------------------------

_INSTALLER_REF = "v1.0.7"
_INSTALLER_TEMPLATE = (
    "https://raw.githubusercontent.com/TencentCloud/octop-memory/{ref}/plugins/harness/install.sh"
)


def installer_source() -> str:
    """安装脚本来源：默认固定 tag；``OCTOP_MEMORY_INSTALLER_URL`` 可指向内网镜像。"""
    override = os.environ.get("OCTOP_MEMORY_INSTALLER_URL")
    if override:
        return override
    return _INSTALLER_TEMPLATE.format(ref=_INSTALLER_REF)


def install_script_body(memory_url: str) -> str:
    """生成给 ``curl | sh`` 的薄壳脚本（不含任何凭证）。"""
    return f"""#!/usr/bin/env sh
# octop 托管 · 终端接入安装薄壳（来源固定 tag，可用 OCTOP_MEMORY_INSTALLER_URL 指向内网镜像）
set -eu
DEFAULT_SRC={quote(installer_source())}
DEFAULT_MEMORY_URL={quote(memory_url)}
SRC="${{OCTOP_MEMORY_INSTALLER_URL:-$DEFAULT_SRC}}"
MEMORY_URL="${{OCTOP_MEMORY_URL:-$DEFAULT_MEMORY_URL}}"

export OCTOP_MEMORY_REF="${{OCTOP_MEMORY_REF:-{_INSTALLER_REF}}}"
needs_token=1
for arg in "$@"; do
  case "$arg" in --token|-h|--help) needs_token=0 ;; esac
done
if [ "$needs_token" = 1 ] && [ -z "${{OCTOP_MEMORY_TOKEN:-}}" ]; then
  OCTOP_MEMORY_TOKEN=$(python3 -c 'import getpass; print(getpass.getpass("Token: "))' </dev/tty) || exit 2
  export OCTOP_MEMORY_TOKEN
fi

echo "→ 目标记忆服务：$MEMORY_URL"
if [ -t 0 ]; then
  printf "继续安装？[y/N] " && read -r _ans
  case "$_ans" in y|Y) ;; *) echo "已取消。"; exit 1 ;; esac
fi

installer=$(curl -fsSL "$SRC")
exec sh -c "$installer" sh --url "$MEMORY_URL" "$@"
"""


@router.get(
    "/terminal/install.sh",
    response_class=PlainTextResponse,
    summary="Octop-hosted terminal installer wrapper (read-only, no credentials)",
)
def install_script(client_base: str = Depends(memory_client_base)) -> PlainTextResponse:
    # 只读：不签发 token、不写库（威胁模型 R7）
    return PlainTextResponse(
        install_script_body(f"{client_base}/mcp/"),
        media_type="text/x-shellscript; charset=utf-8",
    )


@router.get("/spaces", summary="Spaces visible to the management session")
def spaces(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _require_session(server, int(user.id))
    return memory_sharing.list_spaces(int(user.id))


@router.get("/tokens", summary="Tokens of the connected space")
def tokens(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _require_session(server, int(user.id))
    return memory_sharing.list_tokens(int(user.id))


@router.post("/tokens", summary="Issue a token for one client")
def create_token(
    body: TokenCreateBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _require_session(server, int(user.id))
    return memory_sharing.create_token(int(user.id), body.client_name, body.scopes)


@router.post("/tokens/{token_id}/rotate", summary="Rotate a client token")
def rotate(
    token_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _require_session(server, int(user.id))
    return memory_sharing.rotate_token(int(user.id), token_id)


@router.delete("/tokens/{token_id}", summary="Revoke a client token")
def revoke(
    token_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _require_session(server, int(user.id))
    return memory_sharing.revoke_token(int(user.id), token_id)


@router.get("/clients", summary="Clients seen in the connected space")
def clients(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    _require_session(server, int(user.id))
    return memory_sharing.list_clients(int(user.id))


@router.get("/binding/{agent_id}", summary="Space bound to an expert")
def binding(
    agent_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    row = _agent_row(server, agent_id)
    assert_agent_access_row(row, user, repos=server.services.repos if server.services else None)
    assert server.services is not None
    saved = get_expert_binding(server.services.repos.secret_repo, agent_id)
    return _binding_payload(row, user, saved)


@router.post("/binding", summary="Bind an expert to a memory space")
async def bind(
    body: BindBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    assert server.app_runtime is not None and server.services is not None
    registry = server.app_runtime.agent_registry
    repo = server.services.repos.secret_repo
    user_id = int(user.id)
    lock = _binding_locks.setdefault((id(registry), body.agent_id), asyncio.Lock())
    async with lock:
        row = _agent_row(server, body.agent_id)
        assert_agent_owner(row, user)
        saved = get_expert_binding(repo, row.agent_id)
        replacement = ExpertBinding()
        if body.space_id is not None:
            if not supports_sharing(row):
                raise OctopError(
                    ErrorCode.FORBIDDEN, "Only private local experts can join a memory space"
                )
            replacement = await asyncio.to_thread(
                _credential_for_space, user_id, row, body.space_id, saved
            )

        if replacement != saved:
            try:
                latest = _agent_row(server, row.agent_id)
                assert_agent_owner(latest, user)
                if replacement.space_id is not None and not replacement.active_for(latest):
                    raise OctopError(
                        ErrorCode.FORBIDDEN, "The expert changed while joining the space"
                    )
                save_expert_binding(repo, row.agent_id, replacement)
            except Exception:
                await asyncio.to_thread(_revoke_expert_binding, user_id, replacement)
                raise
            previous_revoked = await asyncio.to_thread(_revoke_expert_binding, user_id, saved)
        else:
            previous_revoked = True

        await registry.reload(row.agent_id)
        payload = _binding_payload(row, user, replacement)
        if not previous_revoked:
            payload["previous_token_revoked"] = False
        return payload


def _binding_payload(row: AgentRow, user: User, saved: ExpertBinding | None) -> dict[str, Any]:
    is_owner = user.is_admin or user_owns_agent(row, user)
    can_manage = is_owner and supports_sharing(row)
    space_id = None
    if is_owner and saved is None:
        legacy = _parse_config(row.config_json).get("memory_sharing")
        if isinstance(legacy, dict) and isinstance(legacy.get("space_id"), str):
            space_id = legacy["space_id"]
    elif (
        is_owner and saved is not None and (saved.owner_id is None or saved.owner_id == row.user_id)
    ):
        space_id = saved.space_id
    return {
        "agent_id": row.agent_id,
        "space_id": space_id,
        "has_credential": bool(can_manage and saved is not None and saved.active_for(row)),
        "can_manage": can_manage,
    }


def _credential_for_space(
    user_id: int, row: AgentRow, space_id: str, saved: ExpertBinding | None
) -> ExpertBinding:
    spaces = memory_sharing.list_spaces(user_id).get("spaces", [])
    if not any(space.get("space_id") == space_id for space in spaces):
        raise OctopError(ErrorCode.FORBIDDEN, "Memory session cannot access this space")
    if (
        saved is not None
        and saved.token is not None
        and saved.space_id == space_id
        and saved.active_for(row)
    ):
        tokens = memory_sharing.list_tokens_in(user_id, space_id).get("tokens", [])
        if any(
            token.get("token_id") == saved.token_id
            and not token.get("revoked_at")
            and token.get("token_hint") == saved.token[-4:]
            for token in tokens
        ):
            return saved

    created = memory_sharing.create_token_in(
        user_id, space_id, f"Octop expert {row.agent_id}", ["read", "write"]
    )
    credential = ExpertBinding(
        space_id=space_id,
        owner_id=row.user_id,
        base_url=memory_sharing.service_url(),
        token_id=created.get("token_id"),
        token=created.get("token"),
    )
    if not credential.active_for(row):
        _revoke_expert_binding(user_id, credential)
        raise OctopError(
            ErrorCode.INTERNAL_ERROR, "Memory service did not issue a usable expert credential"
        )
    return credential


def _revoke_expert_binding(user_id: int, saved: ExpertBinding | None) -> bool:
    if saved is None or saved.token_id is None:
        return True
    if saved.base_url != memory_sharing.service_url():
        return False
    try:
        memory_sharing.revoke_token(user_id, saved.token_id)
    except OctopError as exc:
        if exc.code == ErrorCode.NOT_FOUND:
            return True
        logger.warning("Unable to revoke the previous shared-memory expert token: %s", exc.code)
        return False
    return True


def _agent_row(server: OctopServer, agent_id: str) -> AgentRow:
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
