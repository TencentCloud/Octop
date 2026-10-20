"""Recall path: query → atom (primary) + raw fallback → prompt-injectable text.

The L2 atom layer is the **primary** recall source, with raw events kept as a
**fallback** for things that haven't been promoted yet. The output is a single
``RecallResult`` with each snippet tagged by the layer it came from, so adapters
can render or trace per-layer. A single-source raw FTS recall is still available
via ``sources=("raw",)``.

Order of operations (default ``sources=("atom","raw")``):
1. FTS5 search atoms; collect up to ``limit`` snippets, ranked by
   importance + BM25.
2. If atoms returned fewer than ``limit`` snippets, top up with raw
   events FTS, deduping against any raw event that already underlies
   the atom snippets (i.e. don't show a quote AND its raw twice).

Caller can opt into single-source via ``sources=("raw",)``
or ``sources=("atom",)`` (skip raw fallback). The set is small and
ordered: order in the tuple determines priority.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from octop_memory.core import Memory
from octop_memory.domain.retention import MANUAL_DOCUMENTS_RECALL_KEY, is_runtime_error
from octop_memory.pipeline.recall.rerank import RerankCandidate
from octop_memory.pipeline.recall.suppress import manual_recall_policy
from octop_memory.storage.driver_errors import DRIVER_ERRORS
from octop_memory.types import AtomCard, RawEvent

_log = logging.getLogger(__name__)

RecallLayer = Literal["atom", "raw"]
"""Which storage layer a snippet came from. Used by adapters / debug trace."""


@dataclass(frozen=True)
class RecallSnippet:
    """One unit of recalled content ready for injection.

    ``layer`` tags which source the snippet came from. It is a strictly
    additive field — callers that don't consume it keep working.
    """

    source_id: str
    timestamp_iso: str
    role_hint: str  # "user" | "assistant" | "tool" | host event_type | "atom"
    text: str
    layer: RecallLayer = "raw"


@dataclass(frozen=True)
class RecallResult:
    """End-to-end recall output.

    ``snippets`` is rank-ordered (most relevant first) up to ``limit``.
    ``rendered`` is a single markdown block ready to inject. Adapters
    that prefer their own formatting can ignore ``rendered`` and use
    ``snippets`` directly.
    """

    snippets: list[RecallSnippet]
    rendered: str


# Soft caps to avoid blowing up the host's prompt budget. M4 introduces
# real token budget allocation; here we just use char count as a proxy.
_DEFAULT_PER_SNIPPET_CHARS = 200
_DEFAULT_TOTAL_CHARS = 1500
_DEFAULT_SOURCES: tuple[RecallLayer, ...] = ("atom", "raw")
"""Default recall composition: atom-first, raw fallback.

For raw-only recall explicitly: ``sources=("raw",)``.
"""

QUERY_PREVIEW_LEN = 60
"""Max characters of query text shown in the recall footer annotation."""


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def _role_for_raw(event: RawEvent) -> str:
    role = event.payload.get("role")
    if isinstance(role, str) and role:
        return role
    return event.event_type


def _role_for_atom(atom: AtomCard) -> str:
    """Atoms don't have a role per se; surface the importance level instead.

    Adapters can map ``"atom:high"`` → bold, etc. We keep the prefix so
    a renderer that strips role can still tell layer apart.
    """
    return f"atom:{atom.importance}"


def _atom_to_snippet(atom: AtomCard, *, per_snippet_chars: int) -> RecallSnippet:
    # Prefer assertion (which == verbatim_quote for high importance).
    text = _truncate(atom.assertion.strip(), per_snippet_chars)
    return RecallSnippet(
        source_id=atom.id,
        timestamp_iso=atom.occurred_at.isoformat(),
        role_hint=_role_for_atom(atom),
        text=text,
        layer="atom",
    )


def _raw_to_snippet(event: RawEvent, *, per_snippet_chars: int) -> RecallSnippet:
    return RecallSnippet(
        source_id=event.id,
        timestamp_iso=event.timestamp.isoformat(),
        role_hint=_role_for_raw(event),
        text=_truncate(event.content.strip(), per_snippet_chars),
        layer="raw",
    )


def recall_multi_source(
    memory: Memory,
    query: str,
    *,
    limit: int = 5,
    sources: Sequence[RecallLayer] = _DEFAULT_SOURCES,
    per_snippet_chars: int = _DEFAULT_PER_SNIPPET_CHARS,
    total_chars: int = _DEFAULT_TOTAL_CHARS,
) -> RecallResult:
    """Run multi-source FTS recall and return text ready for prompt injection.

    Args:
        memory: backing :class:`Memory` instance.
        query: user prompt or extracted query phrase. Empty input
            short-circuits to an empty result.
        limit: hard cap on total snippets across all sources.
        sources: source layers to consult, in priority order. The
            default ``("atom", "raw")`` returns atoms first and tops
            up with raw events. ``("raw",)`` consults raw only.
            ``("atom",)`` skips raw fallback entirely.
        per_snippet_chars / total_chars: budget caps. ``per_snippet_chars``
            truncates each unit; ``total_chars`` stops the loop once the
            sum of accepted snippet bodies would exceed it. Both are simple
            char-count caps (a token-budget allocator may replace them).

    Returns an empty result (``snippets=[]``, ``rendered=""``) when
    nothing matches — adapters MUST handle empty by injecting nothing,
    NOT by injecting a placeholder.
    """
    if not query.strip():
        return RecallResult(snippets=[], rendered="")
    if not sources:
        return RecallResult(snippets=[], rendered="")

    snippets: list[RecallSnippet] = []
    consumed = 0
    # Track raw event ids already represented by an accepted atom so we
    # don't double-count when raw fallback runs next.
    raw_ids_in_atoms: set[str] = set(manual_recall_policy(memory).get("demoted_raw_ids", []))

    # Tokenize the query once so per-source FTS can do OR-match instead
    # of phrase-match (FTS5 phrase mode misses any natural-language
    # query, so the M2 baseline was effectively useless on real queries
    # — we share the tokenizer with the M4 parser for consistency).
    from octop_memory.pipeline.recall.parser import parse_query

    parsed_for_baseline = parse_query(query)
    or_tokens = parsed_for_baseline.raw_tokens or (query,)

    for source in sources:
        if len(snippets) >= limit:
            break

        if source == "atom":
            atoms = _multi_token_atoms(memory, or_tokens, limit=limit)
            for a in atoms:
                if len(snippets) >= limit:
                    break
                snippet = _atom_to_snippet(a, per_snippet_chars=per_snippet_chars)
                if consumed + len(snippet.text) > total_chars:
                    break
                consumed += len(snippet.text)
                snippets.append(snippet)
                # Atom backs one raw event (quote_event_id). Suppress
                # that exact event in the raw fallback so we don't echo.
                raw_ids_in_atoms.add(a.quote_event_id)
                raw_ids_in_atoms.update(a.raw_event_ids)
            continue

        if source == "raw":
            # Pull a few extra so we have headroom after dedup.
            wanted = max(0, limit - len(snippets))
            if wanted == 0:
                continue
            events = _multi_token_raw(memory, or_tokens, limit=wanted * 2)
            for e in events:
                if is_runtime_error(e) or e.payload.get("manual_document_evidence"):
                    continue
                if len(snippets) >= limit:
                    break
                if e.id in raw_ids_in_atoms:
                    continue  # already covered by an accepted atom
                snippet = _raw_to_snippet(e, per_snippet_chars=per_snippet_chars)
                if consumed + len(snippet.text) > total_chars:
                    break
                consumed += len(snippet.text)
                snippets.append(snippet)
            continue

        # Unknown source string — be loud rather than silent.
        raise ValueError(f"recall_multi_source: unknown source layer {source!r}")

    if not snippets:
        return RecallResult(snippets=[], rendered="")

    return RecallResult(snippets=snippets, rendered=_render(snippets, query))


def _render(snippets: list[RecallSnippet], query: str) -> str:
    """Render snippets as a markdown block. Stable, ASCII-friendly.

    Each snippet line is prefixed by its layer in brackets so a quick
    glance at the prompt tells you which side the recall came from.
    """
    lines: list[str] = [
        "[memory] Earlier in this workspace, related to your question:",
    ]
    for s in snippets:
        lines.append(f"- [{s.layer}] ({s.role_hint} @ {s.timestamp_iso}) {s.text}")
    footer = "[/memory] (recalled by FTS query: "
    preview = query[:QUERY_PREVIEW_LEN] + "…" if len(query) > QUERY_PREVIEW_LEN else query
    lines.append(footer + preview + ")")
    return "\n".join(lines)


def _multi_token_atoms(memory: Memory, tokens: tuple[str, ...] | Sequence[str], *, limit: int) -> list[AtomCard]:
    """Run :meth:`Memory.search_atoms` per token; merge + dedup atom by id.

    Order preserved: first-seen wins. Lower-ranked tokens still bring in
    their hits but rank below earlier-token hits.
    """
    seen: dict[str, AtomCard] = {}
    for token in tokens:
        if not token.strip():
            continue
        try:
            for atom in memory.search_atoms(token, limit=limit * 2):
                if atom.id not in seen:
                    seen[atom.id] = atom
                if len(seen) >= limit:
                    return list(seen.values())[:limit]
        except DRIVER_ERRORS:
            _log.warning("recall multi-token atom search failed for token %r", token, exc_info=True)
            continue
    return list(seen.values())[:limit]


def _multi_token_raw(memory: Memory, tokens: tuple[str, ...] | Sequence[str], *, limit: int) -> list[RawEvent]:
    """Same as :func:`_multi_token_atoms` for raw events."""
    seen: dict[str, RawEvent] = {}
    for token in tokens:
        if not token.strip():
            continue
        try:
            for event in memory.search_raw(token, limit=limit * 2):
                if event.id not in seen:
                    seen[event.id] = event
                if len(seen) >= limit:
                    return list(seen.values())[:limit]
        except DRIVER_ERRORS:
            _log.warning("recall multi-token raw search failed for token %r", token, exc_info=True)
            continue
    return list(seen.values())[:limit]


__all__ = [
    "DEFAULT_RECALL_LIMIT",
    "RecallLayer",
    "RecallResult",
    "RecallSnippet",
    "recall_for_prompt",
    "recall_multi_source",
]


DEFAULT_RECALL_LIMIT = 5
"""Default snippet count for the ``recall_for_prompt`` entry point —
exposed as a constant so dogfood scripts can reference it."""


# ---------------------------------------------------------------------------
# recall_for_prompt — full recall pipeline (router + multi-source + rerank +
#   diversify + suppress + budget + thread-state side-effects + cache + timeout)
# ---------------------------------------------------------------------------


RawPolicy = Literal["fallback", "never", "always"]
"""How raw transcript participates in ``recall_for_prompt``.

``fallback`` (default, auto-inject): keep raw only when no durable
(atom / page / episode) candidate exists. ``never`` drops raw always.
``always`` keeps raw mixed in — used by ``memory_search`` when the
runtime config asks for it. The eval baseline ``recall_multi_source``
does not use this flag and still tops up to ``limit``.
"""

_DURABLE_LAYERS = frozenset({"atom", "page_headline", "episode"})


def recall_for_prompt(
    memory: Memory,
    query: str,
    *,
    thread_id: str | None = None,
    session_id: str | None = None,
    limit: int = DEFAULT_RECALL_LIMIT,
    weights: tuple[float, float, float, float, float] | None = None,
    per_entity_cap: int = 3,
    suppress_threshold: float = 0.85,
    total_budget_tokens: int = 1500,
    total_budget_ms: int = 200,
    cache: object | None = None,
    now: datetime | None = None,
    raw_policy: str = "fallback",
    manual_context: dict[str, str] | None = None,
) -> RecallResult:
    """Full recall pipeline.

    Stages:

    1. cache lookup (if ``cache`` provided and ``thread_id`` set)
    2. parse query → entity / time / co-reference hints
    3. route → pick sources, resolve co-reference from active stack
    4. push query mentions to active stack (D41a-C)
    5. gather candidates from each source under per-source timeouts
       (D43-A clamped to remaining global budget)
    5b. apply ``raw_policy`` and drop raw from the current session
        (event ``session_id`` / ``thread_id`` intersecting the current
        session scope) so auto-inject does not echo this conversation
    6. rerank with 5-factor scoring (D38-A)
    7. diversify: ≤ ``per_entity_cap`` per entity
    8. suppress near-duplicates via Jaccard (D44-A rule path)
    9. budget enforcement: token-count via static char proxy (D45-A)
    10. push recall hits to active stack (D41a-A)
    11. render markdown block + cache the result

    Returns a :class:`RecallResult` whose ``snippets`` list is bounded
    by ``limit`` AND the token budget. Empty query → empty result, no
    side effects, no cache pollution.
    """
    if not query or not query.strip():
        return RecallResult(snippets=[], rendered="")

    try:
        return _recall_for_prompt_impl(
            memory,
            query,
            thread_id=thread_id,
            session_id=session_id,
            limit=limit,
            weights=weights,
            per_entity_cap=per_entity_cap,
            suppress_threshold=suppress_threshold,
            total_budget_tokens=total_budget_tokens,
            total_budget_ms=total_budget_ms,
            cache=cache,
            now=now,
            raw_policy=raw_policy,
            manual_context=manual_context,
        )
    except DRIVER_ERRORS:
        _log.warning("recall_for_prompt failed; degrading to empty recall", exc_info=True)
        return RecallResult(snippets=[], rendered="")


def _recall_for_prompt_impl(
    memory: Memory,
    query: str,
    *,
    thread_id: str | None,
    session_id: str | None,
    limit: int,
    weights: tuple[float, float, float, float, float] | None,
    per_entity_cap: int,
    suppress_threshold: float,
    total_budget_tokens: int,
    total_budget_ms: int,
    cache: object | None,
    now: datetime | None,
    raw_policy: str,
    manual_context: dict[str, str] | None,
) -> RecallResult:
    from datetime import UTC

    from octop_memory.pipeline.recall.budget import (
        DEFAULT_TOTAL_TOKENS,
        estimate_tokens,
        make_budget_state,
    )
    from octop_memory.pipeline.recall.cache import RecallCache
    from octop_memory.pipeline.recall.diversify import diversify
    from octop_memory.pipeline.recall.multi_source import gather_candidates
    from octop_memory.pipeline.recall.parser import parse_query
    from octop_memory.pipeline.recall.rerank import DEFAULT_WEIGHTS, rerank
    from octop_memory.pipeline.recall.router import route
    from octop_memory.pipeline.recall.suppress import suppress_duplicates
    from octop_memory.pipeline.recall.thread_state import push_query_mentions, push_recall_hits
    from octop_memory.pipeline.recall.timeout import Stopwatch

    pin = now or datetime.now(UTC)

    # 1. Cache lookup --------------------------------------------------
    typed_cache: RecallCache | None = cache if isinstance(cache, RecallCache) else None
    manual_policy = memory.get_meta(MANUAL_DOCUMENTS_RECALL_KEY)
    cache_thread = thread_id
    if thread_id is not None and (manual_policy or manual_context):
        cache_revision = (manual_policy or "") + json.dumps(manual_context, sort_keys=True)
        suffix = hashlib.sha256(cache_revision.encode()).hexdigest()
        cache_thread = f"{thread_id}:manual:{suffix}"
    if typed_cache is not None and cache_thread is not None:
        hit = typed_cache.get(thread_id=cache_thread, query=query)
        if hit is not None:
            return hit

    sw = Stopwatch(total_budget_ms=total_budget_ms)

    # 2-3. Parse + route -----------------------------------------------
    parsed = parse_query(query, now=pin)
    decision = route(memory, parsed, thread_id=thread_id)

    if not decision.sources:
        return RecallResult(snippets=[], rendered="")

    # 4. Push query mentions -------------------------------------------
    if thread_id is not None and decision.resolved_entity_ids:
        push_query_mentions(
            memory,
            thread_id,
            entity_ids=decision.resolved_entity_ids,
            when=pin,
        )

    # 5. Gather --------------------------------------------------------
    # Pull a wider candidate pool than the final limit so rerank /
    # diversify / suppress have headroom. 4x is generous but cheap
    # (single SQLite call returns rows in ms).
    candidates = gather_candidates(
        memory,
        parsed,
        sources=decision.sources,
        per_source_limit=max(limit * 4, 10),
        sw=sw,
        entity_anchor_ids=decision.resolved_entity_ids,
        manual_context=manual_context,
    )
    candidates = _filter_prompt_raw(
        candidates,
        thread_id=thread_id,
        session_id=session_id,
        raw_policy=raw_policy,
    )
    if not candidates:
        return RecallResult(snippets=[], rendered="")

    # 6. Rerank --------------------------------------------------------
    use_weights = weights or DEFAULT_WEIGHTS
    ranked = rerank(candidates, weights=use_weights, now=pin)

    # 7. Diversify -----------------------------------------------------
    diversified = diversify(ranked, cap=per_entity_cap, limit=None)

    # 8. Suppress ------------------------------------------------------
    suppressed = suppress_duplicates(diversified, threshold=suppress_threshold)

    # 9. Budget enforcement -------------------------------------------
    budget = make_budget_state(total_tokens=total_budget_tokens or DEFAULT_TOTAL_TOKENS)
    accepted: list[RecallSnippet] = []
    hit_entity_ids: list[str] = []
    for ranked_snippet in suppressed.kept:
        if len(accepted) >= limit:
            break
        c = ranked_snippet.candidate
        text = c.text.strip()
        if not text:
            continue
        bucket: str
        if c.layer == "atom":
            bucket = "atom"
        elif c.layer == "page_headline":
            bucket = "page_headline"
        else:
            bucket = "raw"
        tokens_needed = estimate_tokens(text)
        if not budget.try_charge(bucket, tokens_needed):  # type: ignore[arg-type]
            continue
        accepted.append(
            RecallSnippet(
                source_id=c.source_id,
                timestamp_iso=c.occurred_at.isoformat(),
                role_hint=_role_for_layer(c.layer, importance=c.importance),
                text=text,
                layer="atom" if c.layer in ("atom", "page_headline") else "raw",
            )
        )
        if c.entity_id:
            hit_entity_ids.append(c.entity_id)

    # 10. Push recall hits --------------------------------------------
    if thread_id is not None and hit_entity_ids:
        push_recall_hits(memory, thread_id, entity_ids=hit_entity_ids, when=pin)

    # 11. Render + cache ----------------------------------------------
    if not accepted:
        return RecallResult(snippets=[], rendered="")

    result = RecallResult(snippets=accepted, rendered=_render(accepted, query))
    if typed_cache is not None and cache_thread is not None:
        typed_cache.set(thread_id=cache_thread, query=query, value=result)
    return result


def _role_for_layer(layer: str, *, importance: str) -> str:
    """Render ``role_hint`` for one recall layer.

    Render ``role_hint`` so the existing recall renderer keeps its
    layer prefix. Atoms use ``atom:<importance>``; the reserved
    ``page_headline`` layer uses the same rendering role if a caller
    supplies one. Events fall back to ``raw``."""
    if layer in ("atom", "page_headline"):
        return f"atom:{importance}"
    return "raw"


def _filter_prompt_raw(
    candidates: list[RerankCandidate],
    *,
    thread_id: str | None,
    session_id: str | None,
    raw_policy: str,
) -> list[RerankCandidate]:
    """Tighten raw for prompt inject: last-resort only, never this session.

    ``fallback`` (default) drops every raw candidate once any durable
    atom / page / episode hit exists — do not top up to ``limit``.
    ``never`` drops raw always. ``always`` keeps the mix.

    Regardless of policy, raw whose ``session_id`` or ``thread_id``
    intersects the current session scope is dropped. Scope keys are
    ``{session_id, thread_id}``; when ``session_id`` is omitted it
    falls back to ``thread_id`` (same convention as capture).
    """
    policy = raw_policy if raw_policy in {"fallback", "never", "always"} else "fallback"
    drop_raw = policy == "never" or (policy == "fallback" and any(c.layer in _DURABLE_LAYERS for c in candidates))
    kept = [c for c in candidates if c.layer != "raw"] if drop_raw else list(candidates)

    scope = _session_scope_keys(thread_id=thread_id, session_id=session_id)
    if not scope:
        return kept
    return [c for c in kept if not _raw_from_current_session(c, scope)]


def _session_scope_keys(*, thread_id: str | None, session_id: str | None) -> frozenset[str]:
    sid = session_id or thread_id
    return frozenset(key for key in (thread_id, sid) if key)


def _raw_from_current_session(candidate: RerankCandidate, scope: frozenset[str]) -> bool:
    if candidate.layer != "raw" or not scope:
        return False
    payload = candidate.raw_payload
    if not isinstance(payload, RawEvent):
        return False
    event_keys = {key for key in (payload.thread_id, payload.session_id) if key}
    return bool(event_keys & scope)
