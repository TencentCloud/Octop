"""Cross-router request validation helpers (no FastAPI route definitions)."""

from __future__ import annotations

from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.resource_policy import raise_if_backend_outside_user_root
from octop.infra.utils.host_dirs import (
    apply_jail_to_local_roots,
    assert_backend_root_dirs_allowed,
)


def assert_user_backend_root_dirs(
    user: Any,
    backend: Any,
    *,
    policy_repo: Any | None = None,
    app_root: str | None = None,
) -> None:
    """Reject local backend ``root_dir`` values that fail denylist or user policy.

    When *policy_repo* is provided, ``local_shell`` / ``filesystem`` roots must
    stay under the user's jail: their ``workspace_root_dir`` policy when set,
    otherwise the app-owned ``<app_root>/workspaces/<user-id>`` default.
    Sensitive pseudo-fs mounts remain blocked.
    """
    if backend is None:
        return
    if policy_repo is not None and user is not None and app_root is not None:
        from octop.infra.users.resource_policy import (  # noqa: PLC0415
            POLICY_WORKSPACE_ROOT_DIR,
            resolve_workspace_root_dir,
        )

        jail = resolve_workspace_root_dir(
            policy_repo.get(int(user.id), POLICY_WORKSPACE_ROOT_DIR),
            user_id=int(user.id),
            app_root=app_root,
        )
        # An omitted local-backend root_dir means the host root, which is now
        # outside the jail; resolve it to the jail first so the request is
        # validated against the root it will actually use.
        backend = apply_jail_to_local_roots(backend, jail)
        raise_if_backend_outside_user_root(policy_repo, int(user.id), backend, app_root=app_root)
        return
    try:
        assert_backend_root_dirs_allowed(backend, restrict_to_home=False)
    except ValueError as exc:
        raise OctopError(ErrorCode.WORKSPACE_OP_UNSUPPORTED, str(exc)) from exc


async def validate_chat_mcp_servers(
    server: Any,
    *,
    user_id: int,
    names: list[str] | None,
) -> list[str] | None:
    if names is None:
        return None
    if not names:
        return []
    from octop.infra.connectors.service import ConnectorService

    svc = ConnectorService(
        repo=server.services.repos.connector_repo,
        secret_repo=server.services.secret_repo,
        settings_repo=server.services.settings_repo,
        config=server.services.config,
    )
    try:
        return list(svc.validate_mcp_servers_for_user(user_id, names))
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_NOT_BOUND, str(exc)) from exc


async def validate_chat_skills(
    server: Any,
    *,
    agent_id: str,
    user: Any,
    names: list[str] | None,
) -> list[str] | None:
    """Validate per-turn skill filter for chat.

    ``None`` leaves the full skill set; ``[]`` disables all skills.
    """
    if names is None:
        return None
    assert server.app_runtime is not None
    allowed: set[str] = set()
    for summary in await server.app_runtime.agent_registry.list_skill_summaries(agent_id):
        if summary.get("enabled"):
            allowed.add(str(summary["name"]))
            slug = summary.get("slug")
            if slug:
                allowed.add(str(slug))
    bad = [n for n in names if n not in allowed]
    if bad:
        raise OctopError(
            ErrorCode.NOT_FOUND,
            f"skill(s) not found or disabled: {', '.join(bad)}",
        )
    return list(names)
