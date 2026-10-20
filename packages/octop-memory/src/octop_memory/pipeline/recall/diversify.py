"""Diversifier — cap snippets per entity (M4.6).

Stops one prolific entity from monopolising the prompt budget: if
recall hits 8 atoms about ``Hermes`` and 1 about ``OpenClaw``, we
don't want all 8 Hermes atoms before any OpenClaw context. Default
cap is **3 snippets per entity** (design doc §9 "5-factor linear + same entity ≤ 3").

The diversifier consumes a pre-sorted ``list[RankedSnippet]``
(reranker output) and returns a re-ordered subset that respects the
cap. Internally it does a single pass with a per-entity counter:

- Accept a snippet if its entity has not yet hit the cap.
- Otherwise skip it but keep iterating (later candidates from other
  entities still have a chance).
- Snippets without an entity (raw events) are never capped — they
  pass through freely.

Output preserves the original score ordering. Stable on ties.
"""

from __future__ import annotations

from collections.abc import Iterable

from octop_memory.pipeline.recall.rerank import RankedSnippet

DEFAULT_PER_ENTITY_CAP = 3
"""Max snippets per entity per recall call. Tunable per-call via the
``cap`` argument; rarely a good idea to lower below 2 because then
multi-fact entities get under-represented."""


def diversify(
    ranked: Iterable[RankedSnippet],
    *,
    cap: int = DEFAULT_PER_ENTITY_CAP,
    limit: int | None = None,
) -> list[RankedSnippet]:
    """Trim ``ranked`` so no single entity has more than ``cap`` snippets.

    Args:
        ranked: pre-sorted (DESC by score) list from the reranker.
        cap: max snippets per ``entity_id``. Snippets with
            ``entity_id is None`` (raw events) are exempt.
        limit: optional hard cap on the returned list length.

    Returns a new list; input is not mutated.
    """
    if cap < 1:
        raise ValueError(f"cap must be >= 1, got {cap}")

    counts: dict[str, int] = {}
    accepted: list[RankedSnippet] = []
    for s in ranked:
        eid = s.candidate.entity_id
        if eid is not None:
            current = counts.get(eid, 0)
            if current >= cap:
                continue
            counts[eid] = current + 1
        accepted.append(s)
        if limit is not None and len(accepted) >= limit:
            break
    return accepted


__all__ = ["DEFAULT_PER_ENTITY_CAP", "diversify"]
