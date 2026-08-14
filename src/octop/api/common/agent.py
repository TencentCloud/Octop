"""Shared agent ownership / existence checks for HTTP routers."""

from __future__ import annotations

from typing import Any

from octop.infra.errors import ErrorCode, OctopError


def agent_is_shared(row: Any) -> bool:
    return int(getattr(row, "is_shared", 0) or 0) == 1


def user_owns_agent(row: Any, user: Any) -> bool:
    return row.user_id is not None and row.user_id == user.id


def assert_agent_owner(row: Any, user: Any) -> None:
    """Raise if the user may not mutate this agent row (admin bypasses)."""
    if user.is_admin:
        return
    if row.user_id is None or row.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by user")


def _user_may_access(row: Any, user: Any) -> bool:
    if user.is_admin:
        return True
    if row.user_id is not None and row.user_id == user.id:
        return True
    return bool(agent_is_shared(row))


def assert_agent_access_row(row: Any, user: Any) -> None:
    if not _user_may_access(row, user):
        raise OctopError(ErrorCode.FORBIDDEN, "agent not accessible to user")


def require_agent_row(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> Any:
    """Load an agent row after owner / shared-agent / admin ``as_user`` checks."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    if as_user is not None and as_user != user.id:
        if not user.is_admin:
            raise OctopError(ErrorCode.FORBIDDEN, "as_user requires admin")
        target = server.user_manager.get_by_id(as_user)
        if target is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"user {as_user} not found")
        if row.user_id is not None and row.user_id != as_user:
            raise OctopError(ErrorCode.FORBIDDEN, "agent not owned by as_user")
    else:
        assert_agent_access_row(row, user)
    return row


def require_agent_owner_row(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> Any:
    """Load an agent row and require owner-level access."""
    row = require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    assert_agent_owner(row, user)
    return row


def assert_agent_access(server: Any, agent_id: str, user: Any) -> None:
    """Ensure agent exists and is accessible to the current user."""
    require_agent_row(agent_id, user=user, as_user=None, server=server)
