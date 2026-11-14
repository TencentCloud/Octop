"""User-level API tokens for the memory MCP server.

Tokens are personal: a caller acts as the user the token was issued to, so
``X-Octop-User-Id`` is never trusted. Only the SHA-256 digest is stored; the
plaintext token is returned once, at creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator

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


class TokenPatchBody(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="New client name; omit to keep the current one.",
    )
    expert_ids: list[str] | None = Field(
        default=None,
        description=(
            "New expert allow-list. Null or empty removes the restriction "
            "(every expert the user can access). Omit to keep the current list."
        ),
    )
    disabled_clients: list[str] | None = Field(
        default=None,
        description=(
            "Client names (the `X-Octop-Client` header) this token refuses with 403. "
            "Null or empty allows every client. Omit to keep the current list."
        ),
    )

    @model_validator(mode="after")
    def _require_a_field(self) -> TokenPatchBody:
        if not self.model_fields_set.intersection({"name", "expert_ids", "disabled_clients"}):
            raise ValueError("provide name and/or expert_ids and/or disabled_clients")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name must not be null")
        return self


class TokenOut(BaseModel):
    token_id: str = Field(description="Public token id used to revoke it.")
    name: str = Field(description="Client name supplied at creation.")
    expert_ids: list[str] | None = Field(
        default=None,
        description="Expert allow-list; null means no restriction.",
    )
    disabled_clients: list[str] | None = Field(
        default=None,
        description="Clients refused with 403; null means every client is allowed.",
    )
    client_stats: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Per-client usage seen through `X-Octop-Client`: "
            "`{client: {first_seen, last_seen, count}}`; null until a client identifies itself."
        ),
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
        disabled_clients=row.disabled_clients,
        client_stats=row.client_stats,
        token_hint=row.token_hint,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


def _assert_experts_accessible(repos: Any, expert_ids: list[str] | None, user: User) -> None:
    """Every expert in the allow-list must exist and be visible to *user*."""
    for expert_id in expert_ids or []:
        row = repos.agent_repo.get(expert_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {expert_id!r} not found")
        assert_agent_access_row(row, user, repos=repos)


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
    _assert_experts_accessible(repos, body.expert_ids, user)

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


@router.patch(
    "/{token_id}",
    response_model=TokenOut,
    summary="Update a memory MCP token",
    description=(
        "Renames one of the caller's own tokens and/or rebinds its expert allow-list, "
        "and/or disables specific clients (the `X-Octop-Client` header). "
        "Binding a token to a single expert makes it a 唯一令牌: MCP clients then omit "
        "`X-Octop-Agent-Id`. Other users' tokens are not found; revoked tokens cannot be "
        "edited."
    ),
)
def update_token(
    token_id: str,
    body: TokenPatchBody,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> TokenOut:
    assert server.services is not None
    repos = server.services.repos
    repo = repos.memory_mcp_token_repo
    row = repo.get_for_user(token_id, user_id=user.id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"memory MCP token {token_id!r} not found")
    if row.revoked_at:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            f"memory MCP token {token_id!r} was revoked and can no longer be edited",
            status=409,
        )

    name = row.name
    if "name" in body.model_fields_set:
        assert body.name is not None  # guaranteed by TokenPatchBody
        name = body.name
    expert_ids = row.expert_ids
    if "expert_ids" in body.model_fields_set:
        expert_ids = body.expert_ids or None
        _assert_experts_accessible(repos, expert_ids, user)
    disabled_clients = row.disabled_clients
    if "disabled_clients" in body.model_fields_set:
        disabled_clients = body.disabled_clients or None

    updated = repo.update(
        token_id,
        user_id=user.id,
        name=name,
        expert_ids=expert_ids,
        disabled_clients=disabled_clients,
    )
    if updated is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"memory MCP token {token_id!r} not found")
    return _to_out(updated)


@router.post(
    "/{token_id}/rotate",
    response_model=TokenCreated,
    summary="Rotate a memory MCP token",
    description=(
        "Issues a fresh secret for one of the caller's own tokens; the previous plaintext "
        "stops working immediately. Revoked tokens cannot be rotated."
    ),
)
def rotate_token(
    token_id: str,
    user: User = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> TokenCreated:
    assert server.services is not None
    repo = server.services.repos.memory_mcp_token_repo
    plaintext, token_hash = generate_token()
    row = repo.rotate(
        token_id,
        user_id=user.id,
        token_hash=token_hash,
        token_hint=token_hint(plaintext),
    )
    if row is None:
        existing = repo.get_for_user(token_id, user_id=user.id)
        if existing is not None and existing.revoked_at:
            raise OctopError(
                ErrorCode.FORBIDDEN,
                f"memory MCP token {token_id!r} was revoked and can no longer be rotated",
                status=409,
            )
        raise OctopError(ErrorCode.NOT_FOUND, f"memory MCP token {token_id!r} not found")
    return TokenCreated(**_to_out(row).model_dump(), token=plaintext)


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
