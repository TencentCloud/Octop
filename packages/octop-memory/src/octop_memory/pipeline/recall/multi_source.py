"""Multi-source recall — atom + raw fanout per route.

Pure I/O orchestration: takes a parsed query + memory handle + budgets
and returns a flat ``list[RerankCandidate]`` ready for the reranker.
Per D39-A this is **synchronous sequential** in the router-provided
source order.

Each source call is wrapped in :func:`octop_memory.pipeline.recall.timeout.with_deadline`
so a stuck SQLite call can't drag the whole pipeline past the global
hard deadline. Per-source timeouts are taken from D43-A defaults but
clamped to the remaining global budget so we don't spend 50ms on
atom when only 30ms is left overall.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from octop_memory.domain.retention import is_runtime_error
from octop_memory.pipeline.recall.parser import ParsedQuery
from octop_memory.pipeline.recall.rerank import (
    RerankCandidate,
    from_atom,
    from_episode,
    from_page_headline,
    from_raw,
)
from octop_memory.pipeline.recall.suppress import duplicates_manual_context, manual_recall_policy
from octop_memory.pipeline.recall.timeout import (
    DEFAULT_ATOM_BUDGET_MS,
    DEFAULT_RAW_BUDGET_MS,
    Stopwatch,
    TimeoutExceededError,
    with_deadline,
)
from octop_memory.storage.driver_errors import DRIVER_ERRORS, VECTOR_ERRORS
from octop_memory.types import AtomCard, Episode, RawEvent

if TYPE_CHECKING:
    from octop_memory.core import Memory
    from octop_memory.types import EntityPage

_log = logging.getLogger(__name__)


def gather_candidates(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    sources: Sequence[str] = ("atom", "raw"),
    per_source_limit: int = 10,
    sw: Stopwatch | None = None,
    entity_anchor_ids: Sequence[str] = (),
    manual_context: dict[str, str] | None = None,
) -> list[RerankCandidate]:
    """Run each enabled source, collect ``RerankCandidate``s.

    ``entity_anchor_ids`` is the set of entity IDs that the router
    resolved (either from explicit entity-name mention or from
    co-reference against the active-entity stack). When non-empty,
    the atom source ALSO fetches recent atoms for those entities
    directly, regardless of FTS — this is critical for queries like
    "那个项目最近怎么样" where the surface text doesn't contain any
    searchable token for the resolved entity.

    Order in ``sources`` controls execution priority. The default is
    ``("atom", "raw")``.

    Sources are advisory; missing data simply yields zero candidates
    for that source rather than raising.
    """
    if not parsed.text:
        return []

    stopwatch = sw or Stopwatch()
    out: list[RerankCandidate] = []
    manual_policy = manual_recall_policy(memory)
    raw_seen_ids: set[str] = set(manual_policy.get("demoted_raw_ids", []))
    seen_atom_ids: set[str] = set()

    for source in sources:
        if stopwatch.expired:
            break

        if source == "atom":
            atom_budget = min(DEFAULT_ATOM_BUDGET_MS, max(1, stopwatch.remaining_ms))
            try:
                atoms = with_deadline(
                    lambda: _gather_atoms(memory, parsed, limit=per_source_limit, anchor_ids=entity_anchor_ids),
                    stage="atom",
                    budget_ms=atom_budget,
                )
            except TimeoutExceededError:
                stopwatch.split("atom_timeout")
                continue
            except DRIVER_ERRORS:
                _log.warning("recall atom gather failed", exc_info=True)
                continue
            for idx, atom in enumerate(atoms):
                if duplicates_manual_context(atom, manual_policy, manual_context):
                    raw_seen_ids.update(atom.raw_event_ids)
                    raw_seen_ids.add(atom.quote_event_id)
                    continue
                if atom.id in seen_atom_ids:
                    continue
                seen_atom_ids.add(atom.id)
                out.append(from_atom(atom, rank_index=idx))
                raw_seen_ids.add(atom.quote_event_id)
                raw_seen_ids.update(atom.raw_event_ids)
            stopwatch.split("atom")
            continue

        if source == "raw":
            raw_budget = min(DEFAULT_RAW_BUDGET_MS, max(1, stopwatch.remaining_ms))
            try:
                events = with_deadline(
                    lambda: _per_token_raw_search(memory, parsed, limit=per_source_limit * 2),
                    stage="raw",
                    budget_ms=raw_budget,
                )
            except TimeoutExceededError:
                stopwatch.split("raw_timeout")
                continue
            except DRIVER_ERRORS:
                _log.warning("recall raw gather failed", exc_info=True)
                continue
            kept = 0
            for event in events:
                if event.payload.get("manual_document_evidence"):
                    continue
                if kept >= per_source_limit:
                    break
                if event.id in raw_seen_ids:
                    continue  # already covered by an accepted atom
                out.append(from_raw(event, rank_index=kept))
                kept += 1
            stopwatch.split("raw")
            continue

        if source == "page_headline":
            # EntityPage headline gather — one headline per entity.
            # Only fires when the router includes this source (e.g. when
            # entity_anchor_ids are resolved and the entity has a page).
            ph_budget = min(DEFAULT_ATOM_BUDGET_MS, max(1, stopwatch.remaining_ms))
            try:
                pages = with_deadline(
                    lambda: _gather_page_headlines(memory, entity_anchor_ids, limit=per_source_limit),
                    stage="page_headline",
                    budget_ms=ph_budget,
                )
            except TimeoutExceededError:
                stopwatch.split("page_headline_timeout")
                continue
            except DRIVER_ERRORS:
                _log.warning("recall page_headline gather failed", exc_info=True)
                continue
            for idx, page in enumerate(pages):
                if page.dirty and page.entity_id in manual_policy.get("demoted_entity_ids", []):
                    continue
                if page.entity_id in {c.entity_id for c in out}:
                    continue  # entity already represented by an atom hit
                out.append(from_page_headline(page, rank_index=idx))
            stopwatch.split("page_headline")
            continue

        if source == "vector":
            # Vector semantic search (optional enhancement layer).
            # Requires Memory to be configured with vector_index and
            # embedding_provider.
            vector_budget = min(DEFAULT_ATOM_BUDGET_MS, max(1, stopwatch.remaining_ms))
            try:
                vector_atoms = with_deadline(
                    lambda: _gather_vector_atoms(memory, parsed, limit=per_source_limit),
                    stage="vector",
                    budget_ms=vector_budget,
                )
            except TimeoutExceededError:
                stopwatch.split("vector_timeout")
                continue
            except DRIVER_ERRORS:
                _log.warning("recall vector gather failed", exc_info=True)
                continue
            for idx, atom in enumerate(vector_atoms):
                if duplicates_manual_context(atom, manual_policy, manual_context):
                    raw_seen_ids.update(atom.raw_event_ids)
                    raw_seen_ids.add(atom.quote_event_id)
                    continue
                if atom.id in seen_atom_ids:
                    continue  # already matched by FTS, skip duplicate
                seen_atom_ids.add(atom.id)
                # Vector hits get rank_index starting at per_source_limit,
                # to avoid colliding with FTS atoms' rank_index (FTS has
                # higher priority).
                out.append(from_atom(atom, rank_index=per_source_limit + idx))
                raw_seen_ids.add(atom.quote_event_id)
                raw_seen_ids.update(atom.raw_event_ids)
            stopwatch.split("vector")
            continue

        if source == "episode":
            # M5 — user-diary recall. Returns ``Episode`` rows from FTS
            # over summary + verbatim + people + topics. Independent of
            # the atom layer; useful for lived-experience queries without
            # entity anchors.
            ep_budget = min(DEFAULT_ATOM_BUDGET_MS, max(1, stopwatch.remaining_ms))
            try:
                episodes = with_deadline(
                    lambda: _gather_episodes(memory, parsed, limit=per_source_limit),
                    stage="episode",
                    budget_ms=ep_budget,
                )
            except TimeoutExceededError:
                stopwatch.split("episode_timeout")
                continue
            seen_ep_ids: set[str] = set()
            for idx, ep in enumerate(episodes):
                if ep.id in seen_ep_ids:
                    continue
                seen_ep_ids.add(ep.id)
                out.append(from_episode(ep, rank_index=idx))
                # Mark covered raw events so the raw source doesn't
                # double-up on the same quote.
                raw_seen_ids.add(ep.quote_event_id)
                raw_seen_ids.update(ep.raw_event_ids)
            stopwatch.split("episode")
            continue

        # Unknown source: be loud rather than silent.
        raise ValueError(f"gather_candidates: unknown source {source!r}")

    return out


# ---------------------------------------------------------------------------
# Per-source helpers
# ---------------------------------------------------------------------------


def _gather_atoms(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    limit: int,
    anchor_ids: Sequence[str] = (),
) -> list[AtomCard]:
    """Pick the right atom-search variant based on parsed hints.

    Order of preference:
    1. ``anchor_ids`` set → fetch the most recent atoms for those
       entities directly (no FTS). Critical for co-reference queries
       like "那个项目最近怎么样" where the surface text has no
       searchable token for the entity.
    2. Time window present → ``search_atoms_by_time_range``
       (entity_id used as additional filter if exactly one anchor).
    3. Otherwise → per-token FTS, merged + deduped by atom id.

    Anchor + time window: combine — fetch each anchor's atoms inside
    the time window and merge.

    The per-token approach avoids SQLite FTS5's phrase-match trap:
    the M2.9 ``search_atoms`` wraps the whole query in quotes which
    only matches exact phrases, useless for natural-language queries
    like "Hermes 现在怎么样". By splitting into the parser's already-
    extracted word tokens we get OR-style matching at the cost of a
    few extra cheap SQLite calls — well within the per-source 50ms
    budget.
    """
    if anchor_ids:
        out: dict[str, AtomCard] = {}
        if parsed.time_window is not None:
            for eid in anchor_ids:
                for atom in memory.search_atoms_by_time_range(
                    start=parsed.time_window.start,
                    end=parsed.time_window.end,
                    entity_id=eid,
                    limit=limit,
                ):
                    out.setdefault(atom.id, atom)
        else:
            for eid in anchor_ids:
                for atom in memory.list_atoms(entity_id=eid, limit=limit):
                    out.setdefault(atom.id, atom)
        # Mix in topical hits as well so anchor-narrowed recall isn't
        # blind to other useful matches (e.g. when anchors come from
        # a stale stack but the query still has good FTS tokens).
        for atom in _per_token_atom_search(memory, parsed, limit=limit):
            out.setdefault(atom.id, atom)
        return list(out.values())[:limit]

    if parsed.time_window is not None:
        return memory.search_atoms_by_time_range(
            start=parsed.time_window.start,
            end=parsed.time_window.end,
            limit=limit,
        )
    return _per_token_atom_search(memory, parsed, limit=limit)


def _per_token_atom_search(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    limit: int,
) -> list[AtomCard]:
    """Run :meth:`Memory.search_atoms` once per token and merge results."""
    seen: dict[str, tuple[int, int, AtomCard]] = {}  # atom_id -> (token_idx, atom_idx, atom)
    tokens = parsed.raw_tokens or (parsed.text,)
    for token_idx, token in enumerate(tokens):
        if not token.strip():
            continue
        try:
            atoms = memory.search_atoms(token, limit=limit * 2)
        except DRIVER_ERRORS as exc:
            _log.warning("recall atom search failed for token %r: %s", token, exc, exc_info=True)
            continue
        for atom_idx, atom in enumerate(atoms):
            if atom.id not in seen:
                seen[atom.id] = (token_idx, atom_idx, atom)
    # Lower (token_idx, atom_idx) is better — ranks tokens that appear
    # earlier higher, which roughly maps to "more specific match".
    ranked = sorted(seen.values(), key=lambda kv: (kv[0], kv[1]))
    return [item[2] for item in ranked[:limit]]


def _per_token_raw_search(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    limit: int,
) -> list[RawEvent]:
    """Same approach as :func:`_per_token_atom_search` but for raw events."""
    seen: dict[str, tuple[int, int, RawEvent]] = {}
    tokens = parsed.raw_tokens or (parsed.text,)
    for token_idx, token in enumerate(tokens):
        if not token.strip():
            continue
        try:
            events = memory.search_raw(token, limit=limit * 2)
        except DRIVER_ERRORS as exc:
            _log.warning("recall raw search failed for token %r: %s", token, exc, exc_info=True)
            continue
        for evt_idx, event in enumerate(events):
            if is_runtime_error(event):
                continue
            if event.id not in seen:
                seen[event.id] = (token_idx, evt_idx, event)
    ranked = sorted(seen.values(), key=lambda kv: (kv[0], kv[1]))
    return [item[2] for item in ranked[:limit]]


def _gather_page_headlines(
    memory: Memory,
    anchor_ids: Sequence[str],
    *,
    limit: int,
) -> list[EntityPage]:
    """Fetch EntityPage headlines for the given entity anchor IDs.

    Only returns pages that have a non-empty headline and are not dirty
    (dirty pages have stale content — better to skip than show outdated
    summaries). Pages are returned in the order of ``anchor_ids``.

    If ``anchor_ids`` is empty, returns an empty list — page headlines
    are only useful when we know which entity the query is about.
    """

    if not anchor_ids:
        return []

    pages: list[EntityPage] = []
    seen: set[str] = set()
    for entity_id in anchor_ids:
        if entity_id in seen:
            continue
        seen.add(entity_id)
        try:
            page = memory.get_entity_page(entity_id)
        except DRIVER_ERRORS as exc:
            _log.warning(
                "recall page_headline fetch failed for entity %r: %s",
                entity_id,
                exc,
                exc_info=True,
            )
            continue
        if page is None:
            continue
        if not page.headline.strip():
            continue  # no headline yet (page not yet regenerated)
        if page.dirty:
            continue  # stale — skip to avoid showing outdated summary
        pages.append(page)
        if len(pages) >= limit:
            break
    return pages


def _gather_vector_atoms(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    limit: int,
) -> list[AtomCard]:
    """Recall AtomCards via vector semantic search.

    Requires Memory to have both vector_index and embedding_provider
    configured. If either is missing, returns an empty list immediately
    (silent degradation, doesn't affect FTS recall).

    Flow:
    1. embedding_provider.embed(query) -> query vector
    2. vector_index.search(vec, limit=limit) -> [atom_id, ...]
    3. backend.get_atom(atom_id) x N -> [AtomCard, ...]
    """
    vector_index = getattr(memory, "_vector_index", None)
    embedding_provider = getattr(memory, "_embedding_provider", None)

    if vector_index is None or embedding_provider is None:
        return []

    try:
        query_vec = embedding_provider.embed(parsed.text)
    except VECTOR_ERRORS:
        _log.warning("recall vector embed failed", exc_info=True)
        return []

    try:
        atom_ids = vector_index.search(query_vec, limit=limit)
    except VECTOR_ERRORS:
        _log.warning("recall vector search failed", exc_info=True)
        return []

    atoms: list[AtomCard] = []
    for atom_id in atom_ids:
        try:
            atom = memory.get_atom(atom_id)
            if atom is not None:
                atoms.append(atom)
        except DRIVER_ERRORS:
            _log.warning("recall vector atom fetch failed for %r", atom_id, exc_info=True)
            continue
    return atoms


def _gather_episodes(
    memory: Memory,
    parsed: ParsedQuery,
    *,
    limit: int,
) -> list[Episode]:
    """Per-token FTS search over Episodes.

    Same per-token strategy as :func:`_per_token_atom_search` to avoid
    SQLite FTS5's phrase-match trap for natural language queries.
    Time-window queries narrow by ``occurred_at``; otherwise use FTS.
    """
    if parsed.time_window is not None:
        # Time-bounded list: episodes are diary entries, so time scoping
        # is the most natural filter for "how was last week" style queries.
        try:
            return memory.list_episodes(
                after=parsed.time_window.start,
                before=parsed.time_window.end,
                limit=limit,
            )
        except DRIVER_ERRORS as exc:
            _log.warning("recall episode time-range failed: %s", exc, exc_info=True)
            return []

    seen: dict[str, tuple[int, int, Episode]] = {}
    tokens = parsed.raw_tokens or (parsed.text,)
    for token_idx, token in enumerate(tokens):
        if not token.strip():
            continue
        try:
            episodes = memory.search_episodes(token, limit=limit * 2)
        except DRIVER_ERRORS as exc:
            _log.warning("recall episode search failed for token %r: %s", token, exc, exc_info=True)
            continue
        for ep_idx, ep in enumerate(episodes):
            if ep.id not in seen:
                seen[ep.id] = (token_idx, ep_idx, ep)
    ranked = sorted(seen.values(), key=lambda kv: (kv[0], kv[1]))
    return [item[2] for item in ranked[:limit]]


__all__ = ["gather_candidates"]
