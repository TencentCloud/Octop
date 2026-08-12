"""Knowledge-base selection defaults for a single chat turn."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class _KnowledgeBase(Protocol):
    id: str
    default_open: bool
    shared: bool


def merge_knowledge_base_ids(
    visible_bases: Sequence[_KnowledgeBase],
    explicit_ids: list[str] | None,
) -> list[str]:
    """Use private default-open bases only when a turn does not specify a list.

    Shared bases are never auto-injected — they must be selected explicitly.
    """
    if explicit_ids is not None:
        return list(explicit_ids)
    return [base.id for base in visible_bases if base.default_open and not base.shared]
