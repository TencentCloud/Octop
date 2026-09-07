"""tests/unit/agents/test_title_gen.py"""

from __future__ import annotations

from octop.infra.agents.title_gen import (
    _TITLE_MAX_CHARS,
    _TITLE_PROMPT,
    _fallback_title,
    _sanitize_title,
)


def test_sanitize_strips_wrapping_quotes_and_periods():
    assert _sanitize_title('"Fix the redirect".') == "Fix the redirect"
    assert _sanitize_title("Fix the redirect.") == "Fix the redirect"
    assert _sanitize_title('"Fix the redirect."') == "Fix the redirect"


def test_sanitize_takes_first_non_empty_line():
    assert _sanitize_title('\n\n  "调研苹果重茬病土壤微生物"  ') == "调研苹果重茬病土壤微生物"


def test_sanitize_empty_or_whitespace():
    assert _sanitize_title("   ") is None
    assert _sanitize_title("") is None


def test_sanitize_caps_length():
    long = "x" * 200
    assert len(_sanitize_title(long)) == _TITLE_MAX_CHARS


def test_fallback_uses_first_line():
    assert _fallback_title("第一行内容\n第二行") == "第一行内容"
    assert len(_fallback_title("y" * 200)) == _TITLE_MAX_CHARS


def test_prompt_contains_instruction():
    assert "User message:" in _TITLE_PROMPT
    assert "At most 6 words" in _TITLE_PROMPT
