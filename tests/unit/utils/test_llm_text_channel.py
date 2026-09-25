"""Tests for channel-facing thinking tag formatting."""

from __future__ import annotations

from octop.infra.utils.llm_text import prepare_channel_text, strip_thinking


def test_prepare_channel_text_strips_when_hidden() -> None:
    raw = "<think>secret</think>\n可见回复"
    assert prepare_channel_text(raw, show_thinking=False) == "可见回复"
    assert strip_thinking(raw) == "可见回复"


def test_prepare_channel_text_formats_when_shown() -> None:
    raw = "<think>secret</think>\n可见回复"
    assert prepare_channel_text(raw, show_thinking=True) == ("💭 Thinking: secret\n\n可见回复")


def test_prepare_channel_text_handles_thinking_alias() -> None:
    raw = "<thinking>plan</thinking>答案"
    assert prepare_channel_text(raw, show_thinking=False) == "答案"


def test_prepare_channel_text_drops_empty_when_only_thinking() -> None:
    assert prepare_channel_text("<think>only</think>", show_thinking=False) == ""
