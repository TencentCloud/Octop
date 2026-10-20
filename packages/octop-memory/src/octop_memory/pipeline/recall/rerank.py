"""Reranker — 5 factor linear combination (D38-A).

Each candidate snippet (atom / raw event, plus the reserved
``page_headline`` type) is scored on five orthogonal factors,
normalized to ``[0, 1]``:

1. **bm25** — FTS rank position decay. SQLite returns FTS rows ordered
   by relevance; we approximate BM25 as ``1.0 / (1.0 + rank_index)``
   so the top hit scores ~1.0 and decays fast.
2. **importance** — atom importance level mapped onto ``[0.3, 1.0]``.
3. **confidence** — atom confidence level mapped onto ``[0.4, 1.0]``.
4. **recency** — exponential decay on ``occurred_at`` with 30-day half-life.
   Older atoms shrink toward 0; brand-new ones score ~1.0.
5. **layer_prior** — fixed source-quality prior. Current gather sources
   use atom = 1.0 and raw = 0.5. ``page_headline`` = 0.8 is
   reserved for a future page gather source.

Final score = dot product with weights. Defaults are
``(0.4, 0.2, 0.15, 0.15, 0.1)`` — anchored in design doc §9 and
overridable via CLI / config / programmatic argument. The eval harness
runs grid search over these to pick a per-namespace optimum.

Output is a stable, descending sort. Ties broken by source_id to
guarantee deterministic test output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from octop_memory.types import AtomCard, ConfidenceLevel, ImportanceLevel, RawEvent

# ---------------------------------------------------------------------------
# Default factor weights (D38-A)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: tuple[float, float, float, float, float] = (0.40, 0.20, 0.15, 0.15, 0.10)
"""(bm25, importance, confidence, recency, layer_prior). MUST sum to 1.0
in production but we don't enforce that — the eval harness sometimes
explores non-normalised weights to study factor interaction."""


_IMPORTANCE_MAP: dict[ImportanceLevel, float] = {"low": 0.30, "medium": 0.60, "high": 1.00}
_CONFIDENCE_MAP: dict[ConfidenceLevel, float] = {"low": 0.40, "medium": 0.70, "high": 1.00}


_LAYER_PRIORS: dict[str, float] = {
    "atom": 1.00,
    "page_headline": 0.80,
    "episode": 0.65,
    "raw": 0.50,
}


HALF_LIFE_DAYS = 30.0
"""Recency half-life. Atoms older than ~30 days score < 0.5. Adjusted
deliberately to give recent context a strong but not overwhelming bias."""

INTENSITY_HIGH = 4
"""Episode intensity threshold for 'high' importance."""
INTENSITY_MEDIUM = 3
"""Episode intensity threshold for 'medium' importance."""


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RerankCandidate:
    """A snippet bundle waiting to be reranked.

    A pre-rerank snippet bundle. ``layer`` drives both layer_prior
    and downstream rendering. ``occurred_at`` defaults to ``created_at``
    when the underlying object is a raw event with no semantic timestamp."""

    source_id: str
    layer: Literal["atom", "page_headline", "raw", "episode"]
    text: str
    occurred_at: datetime
    importance: ImportanceLevel = "medium"
    confidence: ConfidenceLevel = "medium"
    rank_index: int = 0
    """0-based position in the source FTS result list. Lower = better."""
    entity_id: str | None = None
    """Set for atom / page candidates so the diversifier can group them."""

    raw_payload: object | None = None
    """Optional handle back to the original ``AtomCard`` / ``RawEvent`` /
    ``EntityPage``. Used by renderers; never inspected here."""


@dataclass
class RankedSnippet:
    """A scored snippet with its factor breakdown for explainability."""

    candidate: RerankCandidate
    score: float
    factors: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Factor helpers
# ---------------------------------------------------------------------------


def _bm25_factor(rank_index: int) -> float:
    """``1.0`` at rank 0, ``0.5`` at rank 1, ``0.33`` at rank 2..."""
    rank_index = max(rank_index, 0)
    return 1.0 / (1.0 + rank_index)


def _importance_factor(level: ImportanceLevel) -> float:
    return _IMPORTANCE_MAP.get(level, 0.60)


def _confidence_factor(level: ConfidenceLevel) -> float:
    return _CONFIDENCE_MAP.get(level, 0.70)


def _recency_factor(occurred_at: datetime, *, now: datetime) -> float:
    """Exponential decay with 30-day half-life.

    ``score = 2 ** (-Δdays / half_life)``. Future timestamps clamp to
    ``1.0`` (treat as "just now"); negative deltas should be impossible
    in production but we don't crash on them.
    """
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    delta = (now - occurred_at).total_seconds()
    if delta <= 0:
        return 1.0
    days = delta / 86400.0
    return math.pow(2.0, -days / HALF_LIFE_DAYS)


def _layer_prior(layer: str) -> float:
    return _LAYER_PRIORS.get(layer, 0.50)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_candidate(
    candidate: RerankCandidate,
    *,
    weights: tuple[float, float, float, float, float] = DEFAULT_WEIGHTS,
    now: datetime | None = None,
) -> RankedSnippet:
    """Score a single candidate. Returns ranked snippet with factor map."""
    cur = now or datetime.now(UTC)
    f1 = _bm25_factor(candidate.rank_index)
    f2 = _importance_factor(candidate.importance)
    f3 = _confidence_factor(candidate.confidence)
    f4 = _recency_factor(candidate.occurred_at, now=cur)
    f5 = _layer_prior(candidate.layer)
    w1, w2, w3, w4, w5 = weights
    score = w1 * f1 + w2 * f2 + w3 * f3 + w4 * f4 + w5 * f5
    return RankedSnippet(
        candidate=candidate,
        score=score,
        factors={
            "bm25": f1,
            "importance": f2,
            "confidence": f3,
            "recency": f4,
            "layer_prior": f5,
        },
    )


def rerank(
    candidates: list[RerankCandidate],
    *,
    weights: tuple[float, float, float, float, float] = DEFAULT_WEIGHTS,
    now: datetime | None = None,
) -> list[RankedSnippet]:
    """Score every candidate and return them sorted by score DESC.

    Stable on ties: secondary key is ``source_id`` ASC for determinism.
    """
    cur = now or datetime.now(UTC)
    scored = [score_candidate(c, weights=weights, now=cur) for c in candidates]
    scored.sort(key=lambda s: (-s.score, s.candidate.source_id))
    return scored


# ---------------------------------------------------------------------------
# Adapters from existing M2 / M3 types into RerankCandidate
# ---------------------------------------------------------------------------


def from_atom(atom: AtomCard, *, rank_index: int = 0) -> RerankCandidate:
    return RerankCandidate(
        source_id=atom.id,
        layer="atom",
        text=atom.assertion,
        occurred_at=atom.occurred_at,
        importance=atom.importance,
        confidence=atom.confidence,
        rank_index=rank_index,
        entity_id=atom.entity_id,
        raw_payload=atom,
    )


def from_raw(event: RawEvent, *, rank_index: int = 0) -> RerankCandidate:
    return RerankCandidate(
        source_id=event.id,
        layer="raw",
        text=event.content,
        occurred_at=event.timestamp,
        importance="medium",
        confidence="medium",
        rank_index=rank_index,
        entity_id=None,
        raw_payload=event,
    )


def from_page_headline(page: object, *, rank_index: int = 0) -> RerankCandidate:
    """Build a RerankCandidate from an EntityPage headline.

    The ``page`` argument is typed as ``object`` to avoid a circular
    import at module level; callers pass an ``EntityPage`` instance.
    The layer prior for ``page_headline`` is 0.80 — higher than raw
    (0.50) but lower than atom (1.00), reflecting that headlines are
    pre-digested summaries rather than primary facts.
    """
    from octop_memory.types import EntityPage  # lazy to avoid circular import

    assert isinstance(page, EntityPage)
    return RerankCandidate(
        source_id=page.id,
        layer="page_headline",
        text=page.headline,
        occurred_at=page.updated_at,
        importance="high",  # headlines are always high-importance by design
        confidence="high",
        rank_index=rank_index,
        entity_id=page.entity_id,
        raw_payload=page,
    )


def from_episode(episode: object, *, rank_index: int = 0) -> RerankCandidate:
    """Build a RerankCandidate from an Episode (M5 diary entry).

    Layer prior for ``episode`` is 0.65 — higher than raw (0.50, just
    transcript) but lower than atom (1.00, structured fact). Episodes
    carry curated summaries with emotion tagging, but they are not the
    canonical fact source for entity-level recall.

    Importance maps from emotional intensity: 1-2 → "low", 3 → "medium",
    4-5 → "high". This lets the reranker bubble up emotionally
    significant episodes ("fought with my spouse") above the
    daily-routine ones ("worked overtime today").
    """
    from octop_memory.types import Episode  # lazy to avoid circular import

    assert isinstance(episode, Episode)
    if episode.intensity >= INTENSITY_HIGH:
        importance: ImportanceLevel = "high"
    elif episode.intensity >= INTENSITY_MEDIUM:
        importance = "medium"
    else:
        importance = "low"
    return RerankCandidate(
        source_id=episode.id,
        layer="episode",
        text=episode.summary,
        occurred_at=episode.occurred_at,
        importance=importance,
        confidence="medium",
        rank_index=rank_index,
        entity_id=None,  # episodes intentionally don't link to entities
        raw_payload=episode,
    )


__all__ = [
    "DEFAULT_WEIGHTS",
    "HALF_LIFE_DAYS",
    "RankedSnippet",
    "RerankCandidate",
    "from_atom",
    "from_episode",
    "from_page_headline",
    "from_raw",
    "rerank",
    "score_candidate",
]
