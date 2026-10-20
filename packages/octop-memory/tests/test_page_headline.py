"""Tests for headline truncation (D32-A)."""

from __future__ import annotations

from octop_memory.pipeline.page.headline import (
    HEADLINE_MAX_CHARS,
    coerce_headline,
    truncate_headline,
)


class TestTruncate:
    def test_short_passthrough(self) -> None:
        assert truncate_headline("hello") == "hello"

    def test_empty_returns_empty(self) -> None:
        assert truncate_headline("") == ""
        assert truncate_headline("   ") == ""

    def test_collapses_whitespace_to_single_space(self) -> None:
        assert truncate_headline("hi\n\nthere") == "hi there"
        assert truncate_headline("a   b\tc") == "a b c"

    def test_at_max_length_no_ellipsis(self) -> None:
        s = "x" * HEADLINE_MAX_CHARS
        out = truncate_headline(s)
        assert out == s
        assert len(out) == HEADLINE_MAX_CHARS

    def test_over_max_gets_ellipsis(self) -> None:
        s = "x" * (HEADLINE_MAX_CHARS + 5)
        out = truncate_headline(s)
        assert len(out) == HEADLINE_MAX_CHARS
        assert out.endswith("…")

    def test_full_width_chinese_counts_as_one(self) -> None:
        s = "陈" * 35
        out = truncate_headline(s)
        # 30 chars including ellipsis
        assert len(out) == HEADLINE_MAX_CHARS
        assert out.endswith("…")

    def test_custom_max_chars(self) -> None:
        out = truncate_headline("abcdef", max_chars=4)
        assert len(out) == 4
        assert out.endswith("…")
        assert out == "abc…"

    def test_max_one_no_ellipsis_room(self) -> None:
        # Edge case: max=1 cannot fit ellipsis, just hard-truncate.
        out = truncate_headline("abc", max_chars=1)
        assert len(out) == 1
        assert out == "a"


class TestCoerceHeadline:
    def test_uses_primary_when_present(self) -> None:
        assert coerce_headline("primary line", fallback="ignored") == "primary line"

    def test_falls_back_when_primary_blank(self) -> None:
        assert coerce_headline("", fallback="back up") == "back up"
        assert coerce_headline("   ", fallback="back up") == "back up"
        assert coerce_headline(None, fallback="back up") == "back up"

    def test_truncates_either_branch(self) -> None:
        long = "a" * 40
        out = coerce_headline(long, fallback="x")
        assert len(out) == HEADLINE_MAX_CHARS
        out2 = coerce_headline("", fallback=long)
        assert len(out2) == HEADLINE_MAX_CHARS
