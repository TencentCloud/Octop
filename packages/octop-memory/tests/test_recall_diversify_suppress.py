"""Tests for the diversifier + suppressor (M4.6 + D44-A)."""

from __future__ import annotations

from datetime import UTC, datetime

from octop_memory.pipeline.recall.diversify import diversify
from octop_memory.pipeline.recall.rerank import RankedSnippet, RerankCandidate
from octop_memory.pipeline.recall.suppress import jaccard, suppress_duplicates

_NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)


def _ranked(
    *,
    sid: str,
    score: float,
    entity_id: str | None,
    text: str = "x",
) -> RankedSnippet:
    return RankedSnippet(
        candidate=RerankCandidate(
            source_id=sid,
            layer="atom",
            text=text,
            occurred_at=_NOW,
            importance="medium",
            confidence="medium",
            rank_index=0,
            entity_id=entity_id,
        ),
        score=score,
        factors={},
    )


class TestDiversify:
    def test_per_entity_cap(self) -> None:
        ranked = [_ranked(sid=f"a{i}", score=10 - i, entity_id="E1") for i in range(5)] + [
            _ranked(sid="b1", score=4, entity_id="E2")
        ]
        out = diversify(ranked, cap=3)
        e1 = [s for s in out if s.candidate.entity_id == "E1"]
        assert len(e1) == 3
        assert any(s.candidate.entity_id == "E2" for s in out)

    def test_entityless_snippets_pass_through(self) -> None:
        ranked = [_ranked(sid=f"r{i}", score=10 - i, entity_id=None) for i in range(5)]
        out = diversify(ranked, cap=2)
        # entity_id None means raw — never capped
        assert len(out) == 5

    def test_limit_respected(self) -> None:
        ranked = [_ranked(sid=f"a{i}", score=10 - i, entity_id=f"E{i}") for i in range(10)]
        out = diversify(ranked, cap=3, limit=4)
        assert len(out) == 4

    def test_preserves_order(self) -> None:
        ranked = [
            _ranked(sid="a1", score=10, entity_id="E1"),
            _ranked(sid="b1", score=9, entity_id="E2"),
            _ranked(sid="a2", score=8, entity_id="E1"),
        ]
        out = diversify(ranked, cap=3)
        assert [s.candidate.source_id for s in out] == ["a1", "b1", "a2"]


class TestJaccard:
    def test_identical(self) -> None:
        assert jaccard("hello world", "hello world") == 1.0

    def test_disjoint(self) -> None:
        assert jaccard("foo bar", "baz qux") == 0.0

    def test_partial_overlap(self) -> None:
        # tokens: {hello, world} vs {hello, friend}; inter=1, union=3 → 0.333
        s = jaccard("hello world", "hello friend")
        assert 0.30 < s < 0.40

    def test_empty(self) -> None:
        assert jaccard("", "anything") == 0.0
        assert jaccard("anything", "") == 0.0
        assert jaccard("", "") == 0.0

    def test_chinese_chars(self) -> None:
        # CJK runs explode into char tokens; a 2-char string vs a 4-char string.
        # Intersection has 2 chars; union has 4 chars, so the score is 0.5.
        s = jaccard("你好", "你好世界")
        assert abs(s - 0.5) < 1e-6


class TestSuppressDuplicates:
    def test_keeps_unique(self) -> None:
        ranked = [
            _ranked(sid="a", score=10, entity_id="E1", text="hello world"),
            _ranked(sid="b", score=9, entity_id="E1", text="totally different"),
        ]
        result = suppress_duplicates(ranked)
        assert len(result.kept) == 2
        assert not result.dropped

    def test_drops_near_duplicate(self) -> None:
        ranked = [
            _ranked(sid="a", score=10, entity_id="E1", text="hello world friend"),
            _ranked(sid="b", score=9, entity_id="E1", text="hello world friend"),
        ]
        result = suppress_duplicates(ranked, threshold=0.85)
        assert len(result.kept) == 1
        assert result.kept[0].candidate.source_id == "a"
        assert len(result.dropped) == 1

    def test_threshold_respected(self) -> None:
        # Token overlap = 1/3 → below high threshold, both kept
        ranked = [
            _ranked(sid="a", score=10, entity_id="E1", text="alpha beta gamma"),
            _ranked(sid="b", score=9, entity_id="E1", text="alpha delta epsilon"),
        ]
        result = suppress_duplicates(ranked, threshold=0.85)
        assert len(result.kept) == 2
