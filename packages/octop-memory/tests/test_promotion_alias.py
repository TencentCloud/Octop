"""Tests for ``promotion.alias.normalize_alias``."""

from __future__ import annotations

from octop_memory.domain.alias import normalize_alias


def test_empty_string_returns_empty() -> None:
    assert normalize_alias("") == ""


def test_lowercases_ascii() -> None:
    assert normalize_alias("OpenClaw") == "openclaw"


def test_collapses_whitespace() -> None:
    assert normalize_alias("  Project   X  ") == "project x"


def test_nfkc_folds_fullwidth_to_halfwidth() -> None:
    # Fullwidth Latin letters fold to halfwidth, then casefold to lowercase.
    fullwidth = "ＰＲＯＪＥＣＴ"  # noqa: RUF001
    assert normalize_alias(fullwidth) == "project"


def test_keeps_punctuation_intact() -> None:
    # GPT-4 vs GPT 4 must stay different (punctuation preserved).
    assert normalize_alias("GPT-4") == "gpt-4"
    assert normalize_alias("GPT 4") == "gpt 4"
    assert normalize_alias("GPT-4") != normalize_alias("GPT 4")


def test_chinese_input_passes_through_lowercased_collapsed() -> None:
    # Casefold has no effect on Chinese; whitespace is still collapsed.
    assert normalize_alias("  陈立  ") == "陈立"
    assert normalize_alias("Octop  Memory") == "octop memory"


def test_idempotent() -> None:
    once = normalize_alias("  Hello  WORLD  ")
    twice = normalize_alias(once)
    assert once == twice == "hello world"
