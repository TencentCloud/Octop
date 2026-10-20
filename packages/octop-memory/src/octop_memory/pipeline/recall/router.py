"""Recall router (M4.3) — picks recall sources by parsed query shape.

Decision matrix (design doc §9.2):

| Query shape                         | sources          | notes                              |
|-------------------------------------|------------------|------------------------------------|
| entity hint hits alias              | atom + raw fallback        | anchor on the entity      |
| time-bounded ("yesterday", "last time") | atom (time range) + raw | strict time window         |
| topical / generic                   | atom + raw                  | default route              |
| co-reference only ("that project")  | active-entity stack → atom | needs thread_id           |
| empty / nothing                     | none                        | recall returns empty      |

The router doesn't run I/O itself; it returns a routing decision the
caller passes to :func:`octop_memory.pipeline.recall.multi_source.gather_candidates`
plus thread-state side effects (push hits / mentions to the active
entity stack).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from octop_memory.pipeline.recall.parser import ParsedQuery
from octop_memory.storage.driver_errors import DRIVER_ERRORS

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from octop_memory.core import Memory


@dataclass(frozen=True)
class RoutingDecision:
    """Result of the router. Drives ``gather_candidates`` and ``thread_state.push_query_mentions``.

    Sources are an ordered tuple; gather_candidates iterates in this
    order so the first list runs first (and dedups against later
    sources where applicable, e.g. raw skips events already cited by
    atoms).
    """

    sources: tuple[str, ...]
    resolved_entity_ids: tuple[str, ...] = field(default_factory=tuple)
    """Entities in the query that the alias table resolved. Pushed to
    the active stack via D41a-C ('query_mention')."""
    coref_resolved_entity_id: str | None = None
    """If the parser flagged co-reference and we resolved it from the
    active stack, the resulting entity id. The router has already
    added it to ``resolved_entity_ids`` when it does — exposed
    separately for diagnostics."""


def route(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    thread_id: str | None = None,
) -> RoutingDecision:
    """Decide which recall sources to consult.

    ``thread_id`` is required for co-reference resolution; without it
    we can't read the active-entity stack and pronouns can only fall
    back to topical recall.
    """
    if not parsed.text:
        return RoutingDecision(sources=())

    resolved: list[str] = []

    # ---- entity hints (D41a-C) -----------------------------------------
    for alias in parsed.entity_hints:
        try:
            entity = memory.find_entity_by_alias(alias)
        except DRIVER_ERRORS:
            _log.warning("recall alias lookup failed for %r", alias, exc_info=True)
            continue
        if entity is not None:
            resolved.append(entity.id)

    # ---- co-reference resolution (D41a-A reverse — read from stack) ----
    coref_eid: str | None = None
    if parsed.has_coreference and thread_id and not resolved:
        # Only consult the stack when no explicit entity hint resolved;
        # otherwise the explicit name wins.
        from octop_memory.pipeline.recall.thread_state import top_active_entity

        top = top_active_entity(memory, thread_id)
        if top is not None:
            coref_eid = top.entity_id
            resolved.append(top.entity_id)

    # ---- choose sources ------------------------------------------------
    # The tree is an organizational view over atoms, not an independent
    # recall source. Time-bounded queries still change the atom lookup
    # strategy inside gather_candidates.
    #
    # page_headline: only added when we have resolved entity anchors —
    # headlines are entity-scoped and only useful when we know which
    # entity the query is about. Dirty pages are skipped in gather.
    #
    # vector: added automatically when Memory has a vector_index configured.
    base_sources: list[str] = ["atom", "raw"]
    if resolved:
        base_sources.insert(1, "page_headline")  # after atom, before raw
    if memory.vector_index is not None:
        base_sources.append("vector")
    sources: tuple[str, ...] = tuple(base_sources)

    return RoutingDecision(
        sources=sources,
        resolved_entity_ids=tuple(resolved),
        coref_resolved_entity_id=coref_eid,
    )


__all__ = ["RoutingDecision", "route"]
