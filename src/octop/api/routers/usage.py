"""Token usage router — query the usage_log ledger.

  GET /api/usage/summary             → caller's own roll-up
  GET /api/usage/summary?as_user=N   → admin scope; another user's roll-up
  GET /api/usage/summary?agent_id=X  → scope to one agent (must be visible)
  GET /api/admin/usage/summary       → global roll-up (admin only)

Query params:
  window      = today | yesterday | last_7d | last_30d | all   (default last_30d)
  granularity = total | by_day | by_agent | by_model            (default by_day)
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


def _resolve_user_scope(
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> int:
    """Mirror of the agents router's ``?as_user=`` semantics: an admin
    may query another user's bucket; non-admins are pinned to their own
    id."""
    if as_user is None or as_user == user.id:
        return int(user.id)
    if not user.is_admin:
        raise OctopError(ErrorCode.FORBIDDEN, "as_user requires admin")
    target = server.user_manager.get_by_id(as_user)
    if target is None:
        raise OctopError(ErrorCode.NOT_FOUND, "user not found")
    return int(target.id)


@router.get("/usage/summary")
async def user_summary(
    window: str = "last_30d",
    granularity: str = "by_day",
    agent_id: str | None = None,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    user_id = _resolve_user_scope(user=user, as_user=as_user, server=server)
    if agent_id is not None:
        # Verify the agent exists in the registry
        assert server.app_runtime is not None
        if server.app_runtime.agent_registry.get_row(agent_id) is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    return cast(
        "dict[str, Any]",
        server.services.usage_repo.summary(
            user_id=user_id,
            agent_id=agent_id,
            window=window,
            granularity=granularity,
        ),
    )


# --- admin --------------------------------------------------------------

admin_router = APIRouter()


@admin_router.get("/usage/summary")
async def admin_summary(
    window: str = "last_30d",
    granularity: str = "by_day",
    user_id: int | None = None,
    agent_id: str | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Global usage roll-up. Optional ``user_id`` / ``agent_id`` narrow
    the scope; absent both fields mean *all rows*. Admin only."""
    if not user.is_admin:
        raise OctopError(ErrorCode.FORBIDDEN, "admin required")
    return cast(
        "dict[str, Any]",
        server.services.usage_repo.summary(
            user_id=user_id,
            agent_id=agent_id,
            window=window,
            granularity=granularity,
        ),
    )
