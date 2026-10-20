"""Tests for the budget allocator (M4.7, D45-A)."""

from __future__ import annotations

import pytest

from octop_memory.pipeline.recall.budget import (
    DEFAULT_TOTAL_TOKENS,
    estimate_tokens,
    make_budget_state,
)


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") > 0  # whitespace counts; we don't trim

    def test_ascii_4_per_token(self) -> None:
        # 8 chars → 2 tokens (with ceil)
        assert estimate_tokens("abcdefgh") == 2

    def test_ascii_round_up(self) -> None:
        # 5 chars → ceil(5/4) = 2 tokens
        assert estimate_tokens("abcde") == 2

    def test_chinese_2_per_token(self) -> None:
        assert estimate_tokens("你好你好") == 2

    def test_chinese_round_up(self) -> None:
        assert estimate_tokens("你好你") == 2  # ceil(3/2)

    def test_mixed(self) -> None:
        # Mixed ASCII + CJK example: 6 ASCII (=2 tokens) + 1 space + 2 CJK (=1 token)
        # = "Hermes" 6 chars in "other" bucket + " " 1 char + 2 CJK chars
        # other = 7 chars → ceil(7/4) = 2; cjk = 2 → 1 → total 3
        assert estimate_tokens("Hermes 项目") == 3


class TestBudgetState:
    def test_default_total(self) -> None:
        state = make_budget_state()
        assert state.total_tokens == DEFAULT_TOTAL_TOKENS

    def test_charge_atom_within_cap(self) -> None:
        state = make_budget_state(total_tokens=100)
        assert state.try_charge("atom", 30)
        assert state.bucket_used["atom"] == 30
        assert state.total_used == 30

    def test_atom_cap_enforced(self) -> None:
        state = make_budget_state(total_tokens=100)
        # atom cap = 70
        assert state.try_charge("atom", 70)
        assert not state.try_charge("atom", 1)  # over cap
        assert state.bucket_used["atom"] == 70

    def test_quote_independent_bucket(self) -> None:
        state = make_budget_state(total_tokens=100)
        # atom 70 + quote 20 + headline 10 = 100 OK
        assert state.try_charge("atom", 70)
        assert state.try_charge("quote", 20)
        assert state.try_charge("page_headline", 10)
        assert state.total_used == 100
        # total full now
        assert not state.try_charge("atom", 1)

    def test_atom_and_raw_share_bucket(self) -> None:
        state = make_budget_state(total_tokens=100)
        assert state.try_charge("atom", 60)
        # raw bucket has its own cap (also 70), so 30 raw fits because
        # the *total* is ``max(atom, raw) + quote + headline`` =
        # max(60, 30) = 60. We track buckets independently.
        assert state.try_charge("raw", 30)
        # Pushing raw beyond its 70-cap fails.
        assert not state.try_charge("raw", 50)
        assert state.bucket_used["raw"] == 30

    def test_total_used_dedup_atom_raw(self) -> None:
        state = make_budget_state(total_tokens=100)
        state.try_charge("atom", 50)
        state.try_charge("raw", 30)  # raw used = 30, atom used = 50, max = 50
        # Total: max(atom, raw) + quote + headline = 50 + 0 + 0 = 50
        assert state.total_used == 50

    def test_negative_tokens_rejected(self) -> None:
        state = make_budget_state(total_tokens=100)
        with pytest.raises(ValueError):
            state.try_charge("atom", -1)

    def test_unknown_bucket_rejected(self) -> None:
        state = make_budget_state(total_tokens=100)
        with pytest.raises(ValueError):
            state.try_charge("nope", 10)  # type: ignore[arg-type]

    def test_zero_tokens_succeeds(self) -> None:
        state = make_budget_state(total_tokens=100)
        assert state.try_charge("atom", 0)
        assert state.bucket_used.get("atom", 0) == 0
