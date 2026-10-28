"""Provider creation operations shared by API and setup flows."""

from __future__ import annotations

import sqlite3
from typing import Any, cast

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = cast(Any, None)

from octop.infra.errors import ErrorCode, OctopError

_PROVIDER_CREATE_CONFLICTS: tuple[type[BaseException], ...] = (sqlite3.IntegrityError,)
if pg_errors is not None:
    _PROVIDER_CREATE_CONFLICTS += (pg_errors.UniqueViolation,)


def _is_provider_name_unique_violation(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        detail = str(exc).lower()
        return "unique constraint failed" in detail and "providers.name" in detail
    if pg_errors is None or not isinstance(exc, pg_errors.UniqueViolation):
        return False
    diagnostic = getattr(exc, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == "providers_name_key"


def create_provider(provider_repo: Any, **values: Any) -> int:
    """Create a provider, translating its unique-name constraint to a domain error."""
    try:
        return cast(int, provider_repo.create(**values))
    except _PROVIDER_CREATE_CONFLICTS as exc:
        if _is_provider_name_unique_violation(exc):
            raise OctopError.localized(ErrorCode.PROVIDER_NAME_TAKEN) from exc
        raise
