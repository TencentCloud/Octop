"""User-level API tokens for the memory MCP server.

Tokens are personal: a caller acts as the user the token was issued to, so
``X-Octop-User-Id`` is never trusted. Only the SHA-256 digest is stored; the
plaintext token is returned once, at creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_access_row
from octop.api.deps import current_user, get_server, require_permission
from octop.infra.agents.memory_tokens import generate_token, token_hint
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.users.identity import User
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.db.repos.memory_mcp_tokens import MemoryMcpTokenRow

router = APIRouter(
    prefix="/memory-mcp/tokens",
    dependencies=[Depends(require_permission("memory"))],
)


class TokenCreateBody(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=64,
        description="Client name shown in the token list, e.g. `codex@macbook`.",
    )
    expert_ids: list[str] | None = Field(
        default=None,
        description=(
            "Experts this token may use. Null or empty means every expert "
            "the issuing user can access."
        ),
    )


class TokenOut(BaseModel):
    token_id: str = Field(description="Public token id used to revoke it.")
    name: str = Field(description="Client name supplied at creation.")
    expert_ids: list[str] | None = Field(
        default=None,
        description="Expert allow-list; null means no restriction.",
    )
    token_hint: str = Field(description="Masked token for display, e.g. `omcp_abcd…wxyz`.")
    created_at: str = Field(description="Creation time (ISO-8601 UTC).")
    last_used_at: str | None = Field(default=None, description="Last authenticated use.")
    revoked_at: str | None = Field(default=None, description="Revocation time, if revoked.")


class TokenCreated(TokenOut):
    token: str = Field(
        description="Plaintext token. Returned only once; the server keeps only its digest."
    )


class TokenRevoked(BaseModel):
    revoked: bool = Field(description="True when this call revoked the token.")


def _to_out(row: MemoryMcpTokenRow) -> TokenOut:
    return TokenOut(
        token_id=row.token_id,
        name=row.name,
        expert_ids=row.expert_ids,
        token_hint=row.token_hint,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenCreated,
    summary="Create a memory MCP token",
    description="Issues a personal token for one MCP client. The plaintext token is returned once.",
)
def create_token(
    body: TokenCreateBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> TokenCreated:
    assert server.services is not None
    repos = server.services.repos
    for expert_id in body.expert_ids or []:
        row = repos.agent_repo.get(expert_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {expert_id!r} not found")
        assert_agent_access_row(row, user, repos=repos)

    plaintext, token_hash = generate_token()
    token_row = repos.memory_mcp_token_repo.create(
        user_id=user.id,
        name=body.name,
        expert_ids=body.expert_ids or None,
        token_id=new_ulid(),
        token_hash=token_hash,
        token_hint=token_hint(plaintext),
    )
    return TokenCreated(**_to_out(token_row).model_dump(), token=plaintext)


@router.get(
    "",
    response_model=list[TokenOut],
    summary="List my memory MCP tokens",
    description="Lists every token issued by the caller, including revoked ones.",
)
def list_tokens(
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> list[TokenOut]:
    assert server.services is not None
    rows = server.services.repos.memory_mcp_token_repo.list_for_user(user.id)
    return [_to_out(row) for row in rows]


@router.delete(
    "/{token_id}",
    response_model=TokenRevoked,
    summary="Revoke a memory MCP token",
    description="Revokes one of the caller's own tokens. Other users' tokens are not found.",
)
def revoke_token(
    token_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> TokenRevoked:
    assert server.services is not None
    repo = server.services.repos.memory_mcp_token_repo
    if repo.get_for_user(token_id, user_id=user.id) is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"memory MCP token {token_id!r} not found")
    return TokenRevoked(revoked=repo.revoke(token_id, user_id=user.id))
