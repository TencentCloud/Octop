"""Cross-router request validation helpers (no FastAPI route definitions)."""

from __future__ import annotations

from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.host_dirs import assert_backend_root_dirs_allowed


def assert_user_backend_root_dirs(_user: Any, backend: Any) -> None:
    """Reject local backend ``root_dir`` values that fail the host denylist.

    All authenticated users may select host paths outside home (UI still
    defaults to home). Sensitive pseudo-fs mounts remain blocked.
    """
    if backend is None:
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
