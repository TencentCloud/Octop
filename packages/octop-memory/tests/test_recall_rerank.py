"""Tests for the 5-factor reranker (M4.5, D38-A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from octop_memory.pipeline.recall.rerank import (
    DEFAULT_WEIGHTS,
    RerankCandidate,
    rerank,
    score_candidate,
)

_NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)


def _make(
    *,
    sid: str = "s1",
    layer: str = "atom",
    importance: str = "medium",
    confidence: str = "medium",
    occurred: datetime | None = None,
    rank_index: int = 0,
    entity_id: str | None = None,
) -> RerankCandidate:
    return RerankCandidate(
        source_id=sid,
        layer=layer,  # type: ignore[arg-type]
        text="x",
        occurred_at=occurred or _NOW,
        importance=importance,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        rank_index=rank_index,
        entity_id=entity_id,
    )


class TestScoreCandidate:
    def test_top_rank_high_importance_recent_atom_scores_near_1(self) -> None:
        c = _make(importance="high", confidence="high", rank_index=0)
        ranked = score_candidate(c, now=_NOW)
        # bm25=1.0 imp=1.0 conf=1.0 recency≈1.0 layer=1.0 → 1.0
        assert ranked.score > 0.95
        assert ranked.factors["bm25"] == 1.0
        assert ranked.factors["recency"] == 1.0

    def test_old_atom_lower_recency(self) -> None:
        old = _NOW - timedelta(days=60)
        ranked = score_candidate(_make(occurred=old, importance="high"), now=_NOW)
        # 60 days ≈ 2 half-lives → recency factor ≈ 0.25
        assert 0.20 < ranked.factors["recency"] < 0.30

    def test_layer_prior_atom_beats_raw(self) -> None:
        atom = score_candidate(_make(layer="atom"), now=_NOW)
        raw = score_candidate(_make(layer="raw", sid="s2"), now=_NOW)
        assert atom.factors["layer_prior"] > raw.factors["layer_prior"]

    def test_importance_low_low_lowest_score(self) -> None:
        s = score_candidate(_make(importance="low", confidence="low"), now=_NOW)
        # With default weights (0.4, 0.2, 0.15, 0.15, 0.1) and
        # bm25=1, recency=1, layer=1, importance=0.3, confidence=0.4
        # → 0.4 + 0.06 + 0.06 + 0.15 + 0.1 = 0.77
        # The relevant property: low/low scores LESS than high/high.
        high_high = score_candidate(_make(importance="high", confidence="high"), now=_NOW)
        assert s.score < high_high.score


class TestRerankSort:
    def test_sorts_descending(self) -> None:
        cands = [
            _make(sid="late", rank_index=2, importance="low"),
            _make(sid="best", rank_index=0, importance="high"),
            _make(sid="middle", rank_index=1, importance="medium"),
        ]
        ranked = rerank(cands, now=_NOW)
        assert ranked[0].candidate.source_id == "best"
        assert ranked[-1].candidate.source_id == "late"

    def test_stable_tiebreak_by_source_id(self) -> None:
        # Two completely identical candidates differ only by source_id.
        cands = [_make(sid="b"), _make(sid="a")]
        ranked = rerank(cands, now=_NOW)
        # tie on score → ascending source_id
        assert [r.candidate.source_id for r in ranked] == ["a", "b"]

    def test_custom_weights(self) -> None:
        # If we crank layer_prior weight to 1.0, layer alone decides order.
        weights = (0.0, 0.0, 0.0, 0.0, 1.0)
        cands = [_make(sid="raw", layer="raw"), _make(sid="atom", layer="atom")]
        ranked = rerank(cands, weights=weights, now=_NOW)
        assert ranked[0].candidate.source_id == "atom"

    def test_default_weights_sum_to_one(self) -> None:
        assert abs(sum(DEFAULT_WEIGHTS) - 1.0) < 1e-9
