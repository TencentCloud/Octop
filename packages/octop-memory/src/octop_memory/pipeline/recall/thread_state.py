"""Thread active-entity stack helpers (D41a-D + D41b-B).

Sits one level above the backend's ``upsert_active_entity`` /
``list_active_entities`` so the recall pipeline can push entities
without thinking about LRU eviction or pin-time. Two push paths
(D41a-D = A + C):

- :func:`push_recall_hits` — fed by reranker output: every entity
  that contributed a top-K snippet bumps to the head of the stack.
- :func:`push_query_mentions` — fed by the parser: literal entity
  names found in the query text bump even if recall didn't hit them
  (covers the "user explicitly named the entity but we have no
  atoms yet" edge case).

Read path:

- :func:`top_active_entity` — what does "that" (pronoun) point to right now?
- :func:`list_active_entities` — full stack for diagnostics / CLI.

The stack lives in the backend's ``thread_active_entities`` table
(D41b-B); calls are idempotent and survive host restarts.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from octop_memory.types import ActiveEntity

if TYPE_CHECKING:
    from octop_memory.core import Memory


DEFAULT_KEEP = 5
"""Stack depth — older entries get evicted after each upsert. 5 is
enough for "that project" co-reference, beyond that the pronoun is
ambiguous anyway."""


def push_recall_hits(
    memory: Memory,
    thread_id: str,
    *,
    entity_ids: Iterable[str],
    when: datetime | None = None,
    keep: int = DEFAULT_KEEP,
) -> int:
    """Push the entity_ids that scored top in the latest recall (D41a-A).

    Returns the count of distinct entities pushed. ``entity_ids`` may
    contain duplicates (e.g. multiple atoms from the same entity);
    we de-dup so each entity entry only refreshes its timestamp once.
    """
    return _push_many(
        memory,
        thread_id=thread_id,
        entity_ids=entity_ids,
        source="recall_hit",
        when=when,
        keep=keep,
    )


def push_query_mentions(
    memory: Memory,
    thread_id: str,
    *,
    entity_ids: Iterable[str],
    when: datetime | None = None,
    keep: int = DEFAULT_KEEP,
) -> int:
    """Push entities literally named in the query (D41a-C).

    The router calls this after the parser turns up entity hints that
    resolved against the alias table — even if the subsequent FTS
    didn't match anything (the user *named* the thing, that's enough
    signal to remember the active entity).
    """
    return _push_many(
        memory,
        thread_id=thread_id,
        entity_ids=entity_ids,
        source="query_mention",
        when=when,
        keep=keep,
    )


def top_active_entity(
    memory: Memory,
    thread_id: str,
) -> ActiveEntity | None:
    """Return the most-recently-active entity in ``thread_id``, or ``None``."""
    rows = memory.list_active_entities(thread_id, limit=1)
    return rows[0] if rows else None


def list_active_entities(
    memory: Memory,
    thread_id: str,
    *,
    limit: int = DEFAULT_KEEP,
) -> list[ActiveEntity]:
    """Full stack for ``thread_id``, newest first."""
    return memory.list_active_entities(thread_id, limit=limit)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _push_many(
    memory: Memory,
    *,
    thread_id: str,
    entity_ids: Iterable[str],
    source: str,
    when: datetime | None,
    keep: int,
) -> int:
    seen: set[str] = set()
    pushed = 0
    pin = when or datetime.now(UTC)
    for eid in entity_ids:
        if not eid or eid in seen:
            continue
        seen.add(eid)
        memory.upsert_active_entity(
            thread_id,
            eid,
            source=source,
            when=pin,
            keep=keep,
        )
        pushed += 1
    return pushed


__all__ = [
    "DEFAULT_KEEP",
    "list_active_entities",
    "push_query_mentions",
    "push_recall_hits",
    "top_active_entity",
]
