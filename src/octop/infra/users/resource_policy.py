"""Per-user named policies: workspace root, token quota, backend types, and future rows."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.host_dirs import (
    assert_backend_root_dirs_allowed,
    assert_safe_host_path,
    host_path_text,
    is_host_filesystem_root,
    iter_local_backend_root_dirs,
    running_in_container,
)

_LOCAL_BACKEND_KINDS = {"local_shell", "filesystem"}

POLICY_WORKSPACE_ROOT_DIR = "workspace_root_dir"
POLICY_TOKEN_QUOTA = "token_quota"
POLICY_MAX_AGENTS = "max_agents"
POLICY_ALLOWED_BACKEND_TYPES = "allowed_backend_types"

# Expert-picker types. Storage kind ``shell`` is the same capability as builtin
# ``local_shell``. Builtin filesystem and storage kind ``filesystem`` share one
# type. ``composite`` is a wrapper, not a policy value.
BACKEND_POLICY_TYPES: tuple[str, ...] = (
    "local_shell",
    "filesystem",
    "cos",
    "s3",
    "oss",
    "obs",
    "tos",
    "custom",
    "postgres",
    "docker",
    "opensandbox",
)
_BACKEND_POLICY_TYPE_SET = frozenset(BACKEND_POLICY_TYPES)
_POLICY_TYPE_ALIASES = {"shell": "local_shell"}


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
    """Stored workspace-root policy, ignored when Octop runs in a container."""
    if running_in_container():
        return None
    return workspace_root_dir_of(raw)


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
        "allowed_backend_types": allowed_backend_types_of(
            by_name.get(POLICY_ALLOWED_BACKEND_TYPES)
        ),
    }


def normalize_workspace_root_dir(raw: str | None) -> str | None:
    """Return a canonical host path, or ``None`` when unrestricted.

    Setting a non-empty root is refused in container deployments — the
    container filesystem is already the isolation boundary.
    """
    if raw is None or not str(raw).strip():
        return None
    if running_in_container():
        raise OctopError(
            ErrorCode.WORKSPACE_ROOT_CONTAINER_UNSUPPORTED,
            "workspace root policy is unavailable in container deployments",
        )
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


def _backend_type_tokens(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise OctopError(
                    ErrorCode.FORBIDDEN,
                    "invalid backend type list",
                    status=400,
                ) from exc
            raw = parsed
        else:
            raw = [part.strip() for part in text.split(",")]
    if isinstance(raw, (list, tuple, set)):
        tokens: list[str] = []
        seen: set[str] = set()
        for item in raw:
            token = str(item).strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
        return tokens
    raise OctopError(ErrorCode.FORBIDDEN, "invalid backend type list", status=400)


def _canonical_policy_type(token: str) -> str:
    return _POLICY_TYPE_ALIASES.get(token, token)


def normalize_allowed_backend_types(raw: Any) -> str | None:
    """Return catalog-ordered types, or ``None`` when the user is unrestricted.

    Empty input clears the policy. Unknown names are rejected. ``shell`` is
    stored as ``local_shell``.
    """
    tokens = _backend_type_tokens(raw)
    if not tokens:
        return None
    selected = {_canonical_policy_type(token) for token in tokens}
    unknown = [
        token for token in tokens if _canonical_policy_type(token) not in _BACKEND_POLICY_TYPE_SET
    ]
    if unknown:
        raise OctopError(
            ErrorCode.FORBIDDEN,
            f"unknown backend types: {unknown}",
            status=400,
        )
    return ",".join(token for token in BACKEND_POLICY_TYPES if token in selected)


def allowed_backend_types_of(raw: Any) -> list[str] | None:
    """Enabled allow-list, or ``None`` when this policy does not apply."""
    if isinstance(raw, (list, tuple, set)):
        stored = normalize_allowed_backend_types(raw)
        return stored.split(",") if stored else None
    if isinstance(raw, Mapping) and "value" not in raw and POLICY_ALLOWED_BACKEND_TYPES in raw:
        raw = raw.get(POLICY_ALLOWED_BACKEND_TYPES)
    text = active_policy_value(raw)
    if text is None:
        return None
    selected = [
        _canonical_policy_type(token)
        for token in (part.strip().lower() for part in text.split(","))
        if _canonical_policy_type(token) in _BACKEND_POLICY_TYPE_SET
    ]
    ordered = [token for token in BACKEND_POLICY_TYPES if token in selected]
    return ordered or None


def backend_policy_types_in(
    spec: Any,
    *,
    named_kind: Callable[[str], str | None],
) -> set[str]:
    """Policy types referenced by an agent backend spec, including composites."""
    found: set[str] = set()

    def add_named(name: str) -> None:
        kind = named_kind(name)
        if kind:
            found.add(_canonical_policy_type(kind.strip().lower()))

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            text = node.strip()
            if not text:
                return
            if text.startswith("named:"):
                add_named(text.split(":", 1)[1])
                return
            found.add(_canonical_policy_type(text.lower()))
            return
        if not isinstance(node, dict):
            return
        kind = node.get("type")
        if not isinstance(kind, str) or not kind.strip():
            return
        kind = kind.strip().lower()
        if kind == "named":
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                add_named(name.strip())
            return
        if kind == "composite":
            walk(node.get("default"))
            routes = node.get("routes")
            if isinstance(routes, dict):
                for sub in routes.values():
                    walk(sub)
            return
        found.add(_canonical_policy_type(kind))

    walk(spec)
    return found


def raise_if_backend_types_disallowed(
    policy_repo: Any,
    user_id: int,
    backend: Any,
    *,
    named_kind: Callable[[str], str | None],
    previous: Any = None,
    require_present: bool = False,
) -> None:
    """Reject backend types outside the user's allow-list.

    A missing policy is unrestricted. On update, types already stored on the
    agent stay valid so an unrelated edit can still save. A create that omits
    the backend is treated as the default ``local_shell``.
    """
    allowed = allowed_backend_types_of(policy_repo.get(user_id, POLICY_ALLOWED_BACKEND_TYPES))
    if not allowed:
        return
    allowed_set = set(allowed)
    if backend in (None, {}) and require_present:
        used = {"local_shell"}
    else:
        used = backend_policy_types_in(backend, named_kind=named_kind)
    if previous is not None:
        used -= backend_policy_types_in(previous, named_kind=named_kind)
    blocked = [
        token for token in BACKEND_POLICY_TYPES if token in used and token not in allowed_set
    ]
    blocked.extend(sorted(used - allowed_set - _BACKEND_POLICY_TYPE_SET))
    if not blocked:
        return
    types = ", ".join(blocked)
    raise OctopError(
        ErrorCode.BACKEND_TYPE_NOT_ALLOWED,
        f"backend types not allowed: {types}",
        details={"types": types},
    )


def assert_backend_within_user_root(
    backend: Any,
    allowed_root: str | None,
    *,
    reject_host_root: bool = False,
) -> None:
    """Raise ``ValueError`` when a local backend root is outside *allowed_root*.

    A missing ``root_dir`` or the host filesystem root is not a violation unless
    *reject_host_root* is set. Create snaps those sentinels onto the allowed
    directory. An update whose workspace already lives outside that directory
    must reject them instead of rewriting ``root_dir`` away from the files.
    """
    if backend is None:
        return
    if not allowed_root:
        assert_backend_root_dirs_allowed(backend, restrict_to_home=False)
        return
    for root_dir in iter_local_backend_root_dirs(backend):
        if is_host_filesystem_root(root_dir) and not reject_host_root:
            continue
        assert_safe_host_path(root_dir, restrict_to_root=allowed_root)


def raise_if_workspace_dir_outside_user_root(
    policy_repo: Any,
    user_id: int,
    config: Mapping[str, Any],
) -> None:
    """Raise when a user-assigned ``workspace_dir`` sits outside the allowed root.

    No-op when the user has no workspace-root policy or the config omits
    ``workspace_dir``. Call this only for a path the user just chose — a stored
    directory that predates the policy must not block unrelated edits.
    """
    allowed = effective_workspace_root_dir(policy_repo.get(user_id, POLICY_WORKSPACE_ROOT_DIR))
    if not allowed:
        return
    raw = config.get("workspace_dir")
    if not isinstance(raw, str) or not raw.strip():
        return
    from octop.infra.agents.workspace.dir import resolve_workspace_host_path

    try:
        host = resolve_workspace_host_path(raw, dict(config))
        assert_safe_host_path(os.fspath(host), restrict_to_root=allowed)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_ROOT_RESTRICTED, str(exc)) from exc


def raise_if_backend_outside_user_root(
    policy_repo: Any,
    user_id: int,
    backend: Any,
    *,
    reject_host_root: bool = False,
) -> None:
    allowed = effective_workspace_root_dir(policy_repo.get(user_id, POLICY_WORKSPACE_ROOT_DIR))
    try:
        assert_backend_within_user_root(backend, allowed, reject_host_root=reject_host_root)
    except ValueError as exc:
        code = (
            ErrorCode.WORKSPACE_ROOT_RESTRICTED if allowed else ErrorCode.WORKSPACE_OP_UNSUPPORTED
        )
        raise OctopError(code, str(exc)) from exc


def persisted_workspace_within_root(config: Mapping[str, Any], allowed_root: str | None) -> bool:
    """True when the on-disk workspace already sits inside *allowed_root*.

    Rewriting a local root is safe only in that case. A host workspace such as
    ``~/.octop/agents/<id>`` stays put; snapping its backend root would hide
    the agent's files.
    """
    if not allowed_root:
        return False
    raw = config.get("workspace_dir")
    if not isinstance(raw, str) or not raw.strip():
        return False
    from octop.infra.agents.workspace.dir import resolve_workspace_host_path

    try:
        host = resolve_workspace_host_path(raw, dict(config))
    except (OSError, ValueError):
        return False
    try:
        assert_safe_host_path(os.fspath(host), restrict_to_root=allowed_root)
    except ValueError:
        return False
    return True


def clamp_backend_to_workspace_root(backend: Any, allowed_root: str | None) -> Any:
    """Snap local roots to *allowed_root*.

    ``local_shell`` and ``filesystem`` (including every composite ``default``
    and route) use *allowed_root* when ``root_dir`` is missing or is the host
    filesystem root. An explicit root inside the jail is kept; one outside
    raises ``ValueError``. Other backend types are returned unchanged. A
    missing backend becomes the default local backend rooted at *allowed_root*.
    """
    if not allowed_root:
        return backend
    if not isinstance(backend, Mapping) or not backend:
        if backend not in (None, {}):
            return backend
        # Lazy: ``default_agent`` imports this module at load time.
        from octop.infra.agents.experts.default_agent import default_home_local_backend

        return default_home_local_backend(root_dir=allowed_root)
    return _clamp_backend_tree(backend, allowed_root)


def _clamp_backend_tree(spec: Mapping[str, Any], allowed_root: str) -> Any:
    kind = str(spec.get("type") or "").strip().lower()
    if kind in _LOCAL_BACKEND_KINDS:
        root = spec.get("root_dir")
        if is_host_filesystem_root(root):
            return {**spec, "root_dir": allowed_root}
        if not isinstance(root, str):
            raise ValueError("invalid path")
        assert_safe_host_path(root, restrict_to_root=allowed_root)
        return spec
    if kind == "composite":
        out = dict(spec)
        default = out.get("default")
        if isinstance(default, Mapping):
            out["default"] = _clamp_backend_tree(default, allowed_root)
        routes = out.get("routes")
        if isinstance(routes, Mapping):
            out["routes"] = {
                str(prefix): (
                    _clamp_backend_tree(route, allowed_root)
                    if isinstance(route, Mapping)
                    else route
                )
                for prefix, route in routes.items()
            }
        return out
    return spec


def apply_workspace_root_to_config(
    policy_repo: Any,
    user_id: int,
    config: dict[str, Any],
    *,
    fill_missing: bool,
) -> None:
    """Persist :func:`clamp_backend_to_workspace_root` onto *config*.

    *fill_missing* is for create: an omitted backend is stored as the default
    local backend under the user's workspace root, so the workspace lands in
    that directory. Updates leave a missing backend alone and only snap roots
    that the caller included.
    """
    allowed = effective_workspace_root_dir(policy_repo.get(user_id, POLICY_WORKSPACE_ROOT_DIR))
    if not allowed:
        return
    backend = config.get("backend")
    if backend in (None, {}) and not fill_missing:
        return
    try:
        config["backend"] = clamp_backend_to_workspace_root(backend, allowed)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_ROOT_RESTRICTED, str(exc)) from exc


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
