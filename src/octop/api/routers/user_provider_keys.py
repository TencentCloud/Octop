"""Per-user model-provider API keys (bring-your-own-key).

A stored personal key overrides the provider's global ``api_key`` for that
user's model calls. Keys are write-only: responses only ever say whether one
exists.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.agents.providers.model_flags import (
    is_keyless_provider_row,
    is_local_runtime_provider,
)
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


class ProviderKeyStatus(BaseModel):
    provider_name: str = Field(..., description="Global provider this key overrides")
    has_own_key: bool = Field(..., description="Whether this user stored a personal key")
    updated_at: int | None = Field(
        default=None, description="When the personal key was last set (unix seconds)"
    )
    user_key_required: bool = Field(
        default=False,
        description="Provider has no global key — a personal key is required to use it",
    )
    keyless: bool = Field(
        default=False,
        description="Provider is explicitly marked as needing no API key",
    )


class ProviderKeyBody(BaseModel):
    api_key: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Personal API key. Write-only: it is never returned by any endpoint.",
    )


def _status(row: Any, *, has_own_key: bool, updated_at: int | None) -> ProviderKeyStatus:
    keyless = is_keyless_provider_row(row)
    return ProviderKeyStatus(
        provider_name=row.name,
        has_own_key=has_own_key,
        updated_at=updated_at,
        user_key_required=not (row.api_key or "").strip() and not keyless,
        keyless=keyless,
    )


def _load_provider(server: Any, provider_name: str) -> Any:
    """The named enabled provider the caller may attach a key to."""
    row = server.services.provider_repo.get_by_name(provider_name)
    if row is None or not row.enabled:
        raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
    if is_local_runtime_provider(
        row.name, provider_api_key=row.api_key, provider_base_url=row.base_url
    ):
        raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
    return row


@router.get("", summary="List personal provider keys", response_model=list[ProviderKeyStatus])
async def list_provider_keys(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[ProviderKeyStatus]:
    """Per-provider key status for the caller. Never returns key material."""
    stored = dict(server.services.user_provider_key_repo.list_for_user(user.id))
    out: list[ProviderKeyStatus] = []
    for row in server.services.provider_repo.list_all():
        if not row.enabled or is_local_runtime_provider(
            row.name, provider_api_key=row.api_key, provider_base_url=row.base_url
        ):
            continue
        updated_at = stored.get(row.name)
        out.append(_status(row, has_own_key=row.name in stored, updated_at=updated_at))
    return out


@router.put(
    "/{provider_name}",
    summary="Set personal provider key",
    response_model=ProviderKeyStatus,
)
async def set_provider_key(
    provider_name: str,
    body: ProviderKeyBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ProviderKeyStatus:
    """Store (or replace) the caller's personal key for one provider."""
    row = _load_provider(server, provider_name)
    key = body.api_key.strip()
    if not key:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "api_key must not be blank")
    updated_at = server.services.user_provider_key_repo.set_key(user.id, row.name, key)
    server.services.audit_repo.write(
        actor=user.username, action="user.provider_key_set", target=row.name
    )
    return _status(row, has_own_key=True, updated_at=updated_at)


@router.delete("/{provider_name}", summary="Delete personal provider key", status_code=204)
async def delete_provider_key(
    provider_name: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Remove the caller's personal key so calls fall back to the global key."""
    row = _load_provider(server, provider_name)
    if server.services.user_provider_key_repo.delete_key(user.id, row.name):
        server.services.audit_repo.write(
            actor=user.username, action="user.provider_key_delete", target=row.name
        )
