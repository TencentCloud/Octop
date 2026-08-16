"""Knowledge-base selection defaults for a single chat turn."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class _KnowledgeBase(Protocol):
    id: str
    owner_user_id: int
    default_open: bool


def merge_knowledge_base_ids(
    visible_bases: Sequence[_KnowledgeBase],
    explicit_ids: list[str] | None,
    *,
    owner_user_id: int,
) -> list[str]:
    """Use the actor's own default-open bases when a turn omits a list.

    ``default_open`` is per-owner preference: shared bases marked default-open
    are auto-injected only for the creating user, not for other viewers.
    """
    if explicit_ids is not None:
        return list(explicit_ids)
    return [
        base.id
        for base in visible_bases
        if base.default_open and int(base.owner_user_id) == int(owner_user_id)
    ]
