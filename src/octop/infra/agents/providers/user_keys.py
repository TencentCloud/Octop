"""Per-user provider API-key overrides (bring-your-own-key) at call time.

A user's personal key replaces the provider's global ``api_key`` for their
model calls. A provider without a global key is usable only through personal
keys: the failure must be loud, never a silent fallback to an unusable key.
"""

from __future__ import annotations

from typing import Any

from octop.infra.agents.providers.model_flags import is_keyless_provider_row
from octop.infra.errors import ErrorCode, OctopError


def resolve_api_key_override(
    *,
    user_id: int,
    model_ref: str | None,
    provider_repo: Any,
    user_provider_key_repo: Any,
) -> str | None:
    """The personal key for this turn's provider, or ``None`` for the global key.

    Raises :class:`OctopError` (``PROVIDER_KEY_REQUIRED``) when the provider has
    no global key, no personal key, and is not explicitly marked as keyless.
    Non-user callers (``user_id <= 0``) always fall back to the global key.
    """
    if user_id <= 0 or not model_ref:
        return None
    provider_name, _, _ = model_ref.partition("/")
    row = provider_repo.get_by_name(provider_name)
    if row is None:
        return None
    key: str | None = user_provider_key_repo.get_key(user_id, provider_name)
    if key:
        return key
    if (getattr(row, "api_key", None) or "").strip():
        return None
    if is_keyless_provider_row(row):
        return None
    raise OctopError(
        ErrorCode.PROVIDER_KEY_REQUIRED,
        "this provider requires a personal API key",
    )
