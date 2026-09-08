"""Per-user named policies: workspace root, token quota, and future rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.host_dirs import (
    assert_backend_root_dirs_allowed,
    assert_safe_host_path,
    host_path_text,
    iter_local_backend_root_dirs,
)

POLICY_WORKSPACE_ROOT_DIR = "workspace_root_dir"
POLICY_TOKEN_QUOTA = "token_quota"


def active_policy_value(row: Any) -> str | None:
    """Return ``value`` when the policy row exists and is enabled."""
    if row is None:
        return None
    if isinstance(row, str):
        return row.strip() or None
    enabled = True
    value: Any = row
    if isinstance(row, Mapping):
        if "value" in row or "enabled" in row:
            enabled = bool(row.get("enabled", True))
            value = row.get("value")
        else:
            return None
    else:
        enabled = bool(getattr(row, "enabled", True))
        value = getattr(row, "value", None)
    if not enabled:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def workspace_root_dir_of(raw: Any) -> str | None:
    if isinstance(raw, Mapping) and "value" not in raw:
        raw = raw.get(POLICY_WORKSPACE_ROOT_DIR)
        if isinstance(raw, str):
            return raw.strip() or None
        if raw is None:
            return None
    return active_policy_value(raw)


def token_quota_of(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, Mapping) and "value" not in raw:
        raw = raw.get(POLICY_TOKEN_QUOTA)
    text = active_policy_value(raw)
    if text is None:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def public_policy_fields(rows: Sequence[Any] | Mapping[str, str] | None) -> dict[str, Any]:
    """HTTP-facing subset of known policies (disabled / missing = unlimited)."""
    by_name: dict[str, str] = {}
    if isinstance(rows, Mapping):
        by_name = {str(key): str(value) for key, value in rows.items() if value}
    elif rows:
        for row in rows:
            name = getattr(row, "name", None)
            value = active_policy_value(row)
            if isinstance(name, str) and value is not None:
                by_name[name] = value
    quota = token_quota_of(by_name.get(POLICY_TOKEN_QUOTA))
    return {
        "workspace_root_dir": workspace_root_dir_of(by_name),
        "token_quota": quota,
    }


def normalize_workspace_root_dir(raw: str | None) -> str | None:
    """Return a canonical host path, or ``None`` when unrestricted."""
    if raw is None or not str(raw).strip():
        return None
    path = assert_safe_host_path(str(raw).strip(), restrict_to_home=False)
    if not path.is_dir():
        raise OctopError(
            ErrorCode.WORKSPACE_ROOT_RESTRICTED,
            "workspace root must be a directory",
        )
    return host_path_text(path)


def normalize_token_quota(raw: int | None) -> int | None:
    if raw is None:
        return None
    quota = int(raw)
    if quota < 0:
        raise OctopError(ErrorCode.FORBIDDEN, "token quota must be >= 0", status=400)
    return quota


def assert_backend_within_user_root(backend: Any, allowed_root: str | None) -> None:
    """Raise ``ValueError`` when a local backend root is outside *allowed_root*."""
    if backend is None:
        return
    if not allowed_root:
        assert_backend_root_dirs_allowed(backend, restrict_to_home=False)
        return
    for root_dir in iter_local_backend_root_dirs(backend):
        assert_safe_host_path(root_dir, restrict_to_root=allowed_root)


def raise_if_backend_outside_user_root(policy_repo: Any, user_id: int, backend: Any) -> None:
    allowed = workspace_root_dir_of(policy_repo.get(user_id, POLICY_WORKSPACE_ROOT_DIR))
    try:
        assert_backend_within_user_root(backend, allowed)
    except ValueError as exc:
        code = (
            ErrorCode.WORKSPACE_ROOT_RESTRICTED if allowed else ErrorCode.WORKSPACE_OP_UNSUPPORTED
        )
        raise OctopError(code, str(exc)) from exc


def assert_token_quota_available(policy_repo: Any, usage_repo: Any, user_id: int) -> None:
    """Raise when the user's lifetime ``total_tokens`` is at or above quota."""
    quota = token_quota_of(policy_repo.get(user_id, POLICY_TOKEN_QUOTA))
    if quota is None:
        return
    used = int(usage_repo.total_tokens_for_user(user_id))
    if used >= quota:
        raise OctopError(
            ErrorCode.TOKEN_QUOTA_EXCEEDED,
            "token quota exceeded",
            details={"used": used, "quota": quota},
        )
