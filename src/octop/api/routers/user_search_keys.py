"""Per-user web-search API keys (self-service).

A stored personal key overrides the global env key for that user's turns.
Keys are write-only: responses only ever say whether one exists.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.search_probe import probe_search_provider
from octop.infra.utils.search_providers import (
    SEARCH_PROVIDERS,
    SearchProviderSpec,
    get_search_provider,
)

router = APIRouter()

_MAX_VALUE_LENGTH = 4096


class SearchKeyStatus(BaseModel):
    provider_id: str = Field(..., description="Catalog provider id")
    label_key: str = Field(default="", description="i18n key for the provider label")
    env_vars: list[str] = Field(default_factory=list, description="Required env vars")
    optional_env_vars: list[str] = Field(
        default_factory=list, description="Optional env vars accepted with a personal key"
    )
    personal_key: bool = Field(..., description="Whether this provider accepts a personal key")
    has_own_key: bool = Field(..., description="Whether this user stored a personal key")
    updated_at: int | None = Field(
        default=None, description="When the personal key was last set (unix seconds)"
    )
    user_key_required: bool = Field(
        default=False,
        description="Provider has no usable global key — a personal key is required",
    )


class SearchKeyBody(BaseModel):
    env: dict[str, str] = Field(
        ...,
        description=(
            "Complete env set for this provider, e.g. {DEEPSEEK_API_KEY: ...}. "
            "Write-only: values are never returned by any endpoint."
        ),
    )


class TestSearchKeyBody(BaseModel):
    env: dict[str, str] | None = Field(
        default=None,
        description="Values to test instead of the stored personal key (not persisted).",
    )


def _user_key_required(spec: SearchProviderSpec) -> bool:
    return bool(spec.env_vars) and any(
        not (os.getenv(name) or "").strip() for name in spec.env_vars
    )


def _status(
    spec: SearchProviderSpec,
    *,
    has_own_key: bool,
    updated_at: int | None,
) -> SearchKeyStatus:
    return SearchKeyStatus(
        provider_id=spec.id,
        label_key=spec.label_key,
        env_vars=list(spec.env_vars),
        optional_env_vars=list(spec.optional_env_vars),
        personal_key=spec.personal_key,
        has_own_key=has_own_key,
        updated_at=updated_at,
        user_key_required=_user_key_required(spec),
    )


def _load_provider(provider_id: str) -> SearchProviderSpec:
    spec = get_search_provider(provider_id)
    if spec is None or not spec.personal_key:
        raise OctopError(ErrorCode.NOT_FOUND, "search provider not found")
    return spec


def _validate_env(spec: SearchProviderSpec, raw: dict[str, str]) -> dict[str, str]:
    allowed = set(spec.env_vars) | set(spec.optional_env_vars)
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if key not in allowed:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"unexpected env var for {spec.id}: {key!r}",
            )
        text = str(value).strip()
        if not text:
            continue
        if len(text) > _MAX_VALUE_LENGTH:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"{key} is longer than {_MAX_VALUE_LENGTH} characters",
            )
        cleaned[key] = text
    missing = [key for key in spec.env_vars if key not in cleaned]
    if missing:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"missing required env var(s): {', '.join(missing)}",
        )
    if not cleaned:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "at least one value is required")
    return cleaned


@router.get("", summary="List personal search keys", response_model=list[SearchKeyStatus])
async def list_search_keys(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[SearchKeyStatus]:
    """Per-provider personal-key status for the caller. Never returns key material."""
    stored = dict(server.services.user_search_key_repo.list_for_user(user.id))
    return [
        _status(
            spec,
            has_own_key=spec.id in stored,
            updated_at=stored.get(spec.id),
        )
        for spec in SEARCH_PROVIDERS
    ]


@router.put("/{provider_id}", summary="Set personal search key", response_model=SearchKeyStatus)
async def set_search_key(
    provider_id: str,
    body: SearchKeyBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> SearchKeyStatus:
    """Store (or replace) the caller's env set for one search provider."""
    spec = _load_provider(provider_id)
    env = _validate_env(spec, body.env)
    updated_at = server.services.user_search_key_repo.set_env(user.id, spec.id, env)
    server.services.audit_repo.write(
        actor=user.username, action="user.search_key_set", target=spec.id
    )
    return _status(spec, has_own_key=True, updated_at=updated_at)


@router.delete("/{provider_id}", summary="Delete personal search key", status_code=204)
async def delete_search_key(
    provider_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Remove the caller's personal key so calls fall back to the global env."""
    spec = _load_provider(provider_id)
    if server.services.user_search_key_repo.delete_key(user.id, spec.id):
        server.services.audit_repo.write(
            actor=user.username, action="user.search_key_delete", target=spec.id
        )


@router.post("/{provider_id}/test", summary="Test personal search key")
async def test_search_key(
    provider_id: str,
    body: TestSearchKeyBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe ``provider_id`` with the supplied values or the stored personal key."""
    spec = _load_provider(provider_id)
    raw = (
        body.env
        if body.env is not None
        else server.services.user_search_key_repo.get_env(user.id, spec.id)
    )
    if not raw:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "no personal key stored for this provider")
    env = _validate_env(spec, raw)
    return await probe_search_provider(spec.id, env)


__all__ = ["router"]
