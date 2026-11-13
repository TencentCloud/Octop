"""Per-turn model access used to keep AUTO failover inside the caller's grants."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from octop.infra.users.groups import model_ref_allowed

_TURN_ACCESS: ContextVar[tuple[int, bool] | None] = ContextVar(
    "octop_turn_model_access",
    default=None,
)


def current_turn_model_access() -> tuple[int, bool] | None:
    """``(user_id, is_admin)`` for the active turn, or ``None`` when unset."""
    return _TURN_ACCESS.get()


@contextmanager
def turn_model_access(user_id: int, *, is_admin: bool) -> Iterator[None]:
    """Bind the caller whose model grants constrain this turn's AUTO failover."""
    token: Token[tuple[int, bool] | None] = _TURN_ACCESS.set((user_id, is_admin))
    try:
        yield
    finally:
        _TURN_ACCESS.reset(token)


def filter_auto_route_candidates[T](candidates: Sequence[T], *, repos: Any) -> list[T]:
    """Drop candidates the current turn's user is not allowed to call.

    When no turn access is bound, the candidate list is unchanged.
    """
    access = current_turn_model_access()
    if access is None:
        return list(candidates)
    user_id, is_admin = access
    return [
        candidate
        for candidate in candidates
        if model_ref_allowed(
            repos,
            user_id=user_id,
            is_admin=is_admin,
            model_ref=str(getattr(candidate, "ref", "")),
        )
    ]
