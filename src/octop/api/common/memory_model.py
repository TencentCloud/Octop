"""Shared validation for a user-selected memory extraction model."""

from typing import Any

from fastapi import HTTPException

from octop.infra.errors import ErrorCode, OctopError


def validate_memory_model_ref(value: str | None, registry: Any, user_id: int) -> str | None:
    """Normalize an ``aux_model`` patch value: None / empty / "auto" → None (AUTO)."""
    if value is None:
        return None
    ref = value.strip()
    if not ref or ref.lower() == "auto":
        return None
    if not registry.providers.is_model_ref_usable(ref):
        raise HTTPException(
            status_code=400,
            detail=f"aux_model {ref!r} is not an enabled model on a usable provider",
        )
    if not registry.model_ref_allowed_for_user(user_id, ref):
        raise OctopError(ErrorCode.RESOURCE_NOT_ALLOWED, "resource is not visible to this user")
    return ref
