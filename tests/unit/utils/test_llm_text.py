"""Tests for silent-output marker detection in llm_text helpers."""

from __future__ import annotations

import pytest

from octop.infra.utils.llm_text import SILENT_REPLY_MARKERS, is_silent_reply


@pytest.mark.parametrize(
    "text",
    [
        "NO_REPLY",
        "SKIP",
        "好的 NO_REPLY",
        "好的 NO_REPLY。",
        "好的。NO_REPLY",  # marker glued to sentence punctuation
        "no_reply",  # loose: case-insensitive
        "skip",
        "Skip",
        "SKIP!",
        "内容\n\nSKIP",
        "NO_REPLY  ",
    ],
)
def test_is_silent_reply_matches_trailing_marker(text: str) -> None:
    assert is_silent_reply(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "NO_REPLY 是一个标记",  # marker not at the end
        "请以 NO_REPLY 结尾",  # marker mid-sentence
        "processor",
        "SKIPPER",  # marker must be a standalone word
        "NO_REPLYX",
        "好的NO_REPLY",  # no separator before the marker
        "今天天气不错",
    ],
)
def test_is_silent_reply_ignores_non_trailing_marker(text: str) -> None:
    assert is_silent_reply(text) is False


def test_markers_constant_matches_regex() -> None:
    assert SILENT_REPLY_MARKERS == ("NO_REPLY", "SKIP")
