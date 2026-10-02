"""Per-user named policies: workspace root, token quota, and future rows."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
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
POLICY_MAX_AGENTS = "max_agents"


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


def effective_workspace_root_dir(raw: Any) -> str | None:
    """Stored workspace-root policy, or ``None`` when none is configured.

    Previously this returned ``None`` in container deployments, on the reasoning
    that the container filesystem is already the isolation boundary. That
    reasoning only held while the ``None`` fallback was the host root ``/``.
    Now the fallback is an app-owned per-user jail
    (:func:`default_workspace_root_dir`), and an admin who wants agents to reach
    a mounted volume must still be able to say so.
    """
    return workspace_root_dir_of(raw)


def default_workspace_root_dir(app_root: str | os.PathLike[str], user_id: int) -> str:
    """App-owned default jail for *user_id*: ``<app_root>/workspaces/<user_id>``.

    Pure path arithmetic — it performs no I/O, so it is safe to call from async
    code. Use :func:`ensure_user_workspace_root` when the directory must exist.

    The previous fallback for a user with no admin policy was the host browse
    root (``/``), which meant any authenticated user could point an agent at any
    directory the server uid could read. The default is now app-owned and
    per-user, so it is never ``/``, the process working directory, or the service
    account's home directory. An explicit admin policy still wins.
    """
    base = Path(app_root).expanduser() / "workspaces" / str(int(user_id))
    return host_path_text(Path(os.path.realpath(base)))


def ensure_user_workspace_root(app_root: str | os.PathLike[str], user_id: int) -> str:
    """Create the per-user default jail if needed and return its canonical path.

    Blocking — call from a worker thread in async request handlers.
    """
    base = Path(app_root).expanduser() / "workspaces" / str(int(user_id))
    base.mkdir(parents=True, exist_ok=True)
    return host_path_text(Path(os.path.realpath(base)))


def resolve_workspace_root_dir(
    raw: Any,
    *,
    user_id: int,
    app_root: str | os.PathLike[str],
) -> str:
    """The user's effective jail root: admin policy if set, else the app default.

    Unlike :func:`effective_workspace_root_dir` this never returns ``None``. The
    previous ``None`` meant "unrestricted, use the host root", which is exactly
    the default the per-user jail replaces.
    """
    configured = effective_workspace_root_dir(raw)
    if configured:
        return configured
    return default_workspace_root_dir(app_root, user_id)


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


def max_agents_of(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, Mapping) and "value" not in raw:
        raw = raw.get(POLICY_MAX_AGENTS)
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
    return {
        "workspace_root_dir": workspace_root_dir_of(by_name),
        "token_quota": token_quota_of(by_name.get(POLICY_TOKEN_QUOTA)),
        "max_agents": max_agents_of(by_name.get(POLICY_MAX_AGENTS)),
    }


def normalize_workspace_root_dir(raw: str | None) -> str | None:
    """Return a canonical host path, or ``None`` when unrestricted.

    Container deployments are accepted: the container filesystem is the
    isolation boundary, but that no longer means a policy is meaningless,
    because pointing a jail at a mounted volume is still an explicit choice.
    """
    if raw is None or not str(raw).strip():
        return None
    path = assert_safe_host_path(str(raw).strip(), restrict_to_home=False)
    resolved = os.path.realpath(os.fspath(path))
    drive, _tail = os.path.splitdrive(resolved)
    # Own drive root on Windows, ``/`` on POSIX. ``startswith`` after
    # ``realpath`` is the containment barrier CodeQL requires before isdir.
    base = f"{drive}{os.sep}" if drive else os.sep
    if resolved.startswith(base):
        if not os.path.isdir(resolved):
            raise OctopError(
                ErrorCode.WORKSPACE_ROOT_RESTRICTED,
                "workspace root must be a directory",
            )
        return host_path_text(path)
    raise OctopError(
        ErrorCode.WORKSPACE_ROOT_RESTRICTED,
        "path not allowed",
    )


def normalize_token_quota(raw: int | None) -> int | None:
    if raw is None:
        return None
    quota = int(raw)
    if quota < 0:
        raise OctopError(ErrorCode.FORBIDDEN, "token quota must be >= 0", status=400)
    return quota


def normalize_max_agents(raw: int | None) -> int | None:
    if raw is None:
        return None
    limit = int(raw)
    if limit < 0:
        raise OctopError(ErrorCode.FORBIDDEN, "max agents must be >= 0", status=400)
    return limit


def assert_backend_within_user_root(backend: Any, allowed_root: str | None) -> None:
    """Raise ``ValueError`` when a local backend root is outside *allowed_root*."""
    if backend is None:
        return
    if not allowed_root:
        assert_backend_root_dirs_allowed(backend, restrict_to_home=False)
        return
    for root_dir in iter_local_backend_root_dirs(backend):
        assert_safe_host_path(root_dir, restrict_to_root=allowed_root)


def raise_if_backend_outside_user_root(
    policy_repo: Any,
    user_id: int,
    backend: Any,
    *,
    app_root: str | os.PathLike[str],
) -> None:
    allowed = resolve_workspace_root_dir(
        policy_repo.get(user_id, POLICY_WORKSPACE_ROOT_DIR),
        user_id=user_id,
        app_root=app_root,
    )
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


def assert_agent_quota_available(policy_repo: Any, agent_repo: Any, user_id: int) -> None:
    """Raise when the user already owns ``max_agents`` expert agents."""
    limit = max_agents_of(policy_repo.get(user_id, POLICY_MAX_AGENTS))
    if limit is None:
        return
    owned = int(agent_repo.count_by_user(user_id, kind="expert"))
    if owned >= limit:
        raise OctopError(
            ErrorCode.AGENT_QUOTA_EXCEEDED,
            "agent quota exceeded",
            details={"used": owned, "quota": limit},
        )
