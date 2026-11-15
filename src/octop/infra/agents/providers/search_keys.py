"""Per-user web-search credentials at call time.

Resolves the caller's personal search keys into the ``tool_env`` mapping the
harness injects for one turn. Only values the user explicitly stored are
included; the harness falls back to the process env for everything else, so an
administrator's global key still works without a personal one.
"""

from __future__ import annotations

from typing import Any, cast


def resolve_search_tool_env(*, user_id: int, search_key_repo: Any) -> dict[str, str]:
    """The personal search env for this turn (may be empty).

    Non-user callers (``user_id <= 0``) never get a personal override. One
    ``secrets`` scan covers every provider so the chat hot path does not run a
    query per provider.
    """
    if user_id <= 0:
        return {}
    return cast("dict[str, str]", search_key_repo.get_all_env(user_id))


__all__ = ["resolve_search_tool_env"]
