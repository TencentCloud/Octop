"""Single source of truth for per-user expert visibility.

Both the HTTP routers and the memory MCP middleware gate access with the same
rule; keeping one implementation means an admin/shared-expert change cannot
silently diverge between the two surfaces.
"""

from __future__ import annotations

from typing import Any


def agent_is_shared(row: Any) -> bool:
    return int(getattr(row, "is_shared", 0) or 0) == 1


def user_owns_agent(row: Any, user: Any) -> bool:
    return row.user_id is not None and row.user_id == user.id


def user_may_access_agent(row: Any, user: Any, *, repos: Any | None = None) -> bool:
    """Owner, admin, or shared expert visible to the user's groups.

    ``repos`` is optional for call sites without the repo bundle: a shared expert
    is then treated as visible (the historical HTTP behaviour).
    """
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    if user_owns_agent(row, user):
        return True
    if not agent_is_shared(row):
        return False
    if repos is None:
        return True
    from octop.infra.users.groups import expert_visible_to  # noqa: PLC0415

    return bool(expert_visible_to(repos, row, user_id=user.id, is_admin=False))
