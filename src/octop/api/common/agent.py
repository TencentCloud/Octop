"""Shared agent ownership / existence checks for HTTP routers.

The **predicates** now live in ``infra/agents/access.py`` — that module is the
single source of truth, and this module re-exports them so every existing
``from octop.api.common.agent import assert_agent_owner`` keeps working unchanged.

Why they moved, and why you must not re-implement them here (or anywhere else):
``AGENTS.md §5`` forbids ``infra/`` → ``api/``, so while the rule lived *only* in
this file, **no infra-side entry point could reach it**. The concrete cost was a
real privilege-escalation path — ``TeamRunService.create`` does not check
user↔agent ownership, so the ``/team`` slash surface accepted runs that the HTTP
surface refuses with 403. ``infra/agents/access.py``'s module docstring carries the
full forensics, the equivalence argument, and the "no second copy" rule.

What stays here is only what needs a ``server``: the row **loaders**
(``require_agent_row`` / ``require_agent_owner_row`` / ``assert_agent_access``).
"""

from __future__ import annotations

from typing import Any

from octop.infra.agents.access import (
    AgentOwnerSubject,
    agent_is_shared,
    assert_agent_access_row,
    assert_agent_owner,
    user_may_access_agent,
    user_owns_agent,
)
from octop.infra.errors import ErrorCode, OctopError

__all__ = [
    "AgentOwnerSubject",
    "agent_is_shared",
    "assert_agent_access",
    "assert_agent_access_row",
    "assert_agent_owner",
    "require_agent_owner_row",
    "require_agent_row",
    "user_may_access_agent",
    "user_owns_agent",
]


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
