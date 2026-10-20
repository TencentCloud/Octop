"""Tests for the recall query parser (M4.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from octop_memory.pipeline.recall.parser import parse_query

_NOW = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)


class TestEmptyAndWhitespace:
    def test_empty_returns_empty_text(self) -> None:
        p = parse_query("", now=_NOW)
        assert p.text == ""
        assert p.entity_hints == ()
        assert p.time_window is None

    def test_whitespace_only(self) -> None:
        p = parse_query("   \n\t  ", now=_NOW)
        assert p.text == ""


class TestEntityHints:
    def test_latin_word(self) -> None:
        p = parse_query("Hermes 进度", now=_NOW)
        assert "hermes" in p.entity_hints

    def test_han_run(self) -> None:
        p = parse_query("陈立呢", now=_NOW)
        assert "陈立呢" in p.entity_hints

    def test_dedup_and_normalise(self) -> None:
        p = parse_query("Hermes hermes HERMES", now=_NOW)
        assert p.entity_hints == ("hermes",)


class TestTimeWindow:
    def test_yesterday(self) -> None:
        p = parse_query("yesterday's deploy", now=_NOW)
        assert p.time_window is not None
        assert p.time_window.label == "yesterday"
        # yesterday = [today_start - 1d, today_start)
        today_start = datetime(2026, 6, 3, tzinfo=UTC)
        assert p.time_window.start == today_start - timedelta(days=1)
        assert p.time_window.end == today_start

    def test_chinese_yesterday(self) -> None:
        p = parse_query("昨天发了什么", now=_NOW)
        assert p.time_window is not None
        assert p.time_window.label == "yesterday"

    def test_last_week_chinese(self) -> None:
        p = parse_query("上周的事", now=_NOW)
        assert p.time_window is not None
        assert p.time_window.label == "last_week"

    def test_iso_date(self) -> None:
        p = parse_query("look at 2026-05-30 logs", now=_NOW)
        assert p.time_window is not None
        assert p.time_window.label == "day:2026-05-30"
        assert p.time_window.start == datetime(2026, 5, 30, tzinfo=UTC)
        assert p.time_window.end == datetime(2026, 5, 31, tzinfo=UTC)

    def test_no_time(self) -> None:
        p = parse_query("Hermes 进度", now=_NOW)
        assert p.time_window is None

    def test_first_match_wins(self) -> None:
        # "yesterday's last week" — yesterday wins (more specific and earlier).
        p = parse_query("yesterday's last week meeting", now=_NOW)
        assert p.time_window is not None
        assert p.time_window.label == "yesterday"


class TestCoreference:
    def test_chinese_pronoun(self) -> None:
        assert parse_query("那个项目最近怎么样", now=_NOW).has_coreference is True

    def test_english(self) -> None:
        assert parse_query("how's that one?", now=_NOW).has_coreference is True

    def test_no_coref(self) -> None:
        assert parse_query("Hermes 怎么样", now=_NOW).has_coreference is False


class TestRawTokens:
    def test_includes_full_run_and_ngrams(self) -> None:
        p = parse_query("那个项目最近", now=_NOW)
        # full run + bigrams + trigrams + 4-grams
        assert "那个项目最近" in p.raw_tokens
        assert "那个" in p.raw_tokens
        assert "项目" in p.raw_tokens
        assert "最近" in p.raw_tokens

    def test_latin_word_passthrough(self) -> None:
        p = parse_query("Hermes 项目", now=_NOW)
        assert "hermes" in p.raw_tokens
