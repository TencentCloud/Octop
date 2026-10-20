"""Tests for ThinkSplitter — the streaming-friendly <think> tag splitter."""

from __future__ import annotations

from octop_harness.protocols.think_splitter import ThinkSplitter


def test_single_chunk_with_think_block() -> None:
    s = ThinkSplitter()
    final, think = s.feed("Hello <think>my reasoning</think> the answer is 42.")
    assert final == "Hello  the answer is 42."
    assert think == "my reasoning"


def test_thinking_long_form() -> None:
    s = ThinkSplitter()
    final, think = s.feed("text <thinking>think</thinking> more")
    assert final == "text  more"
    assert think == "think"


def test_tag_split_across_chunks() -> None:
    """The most important case: tag boundaries crossing chunk boundaries."""
    s = ThinkSplitter()
    chunks = ["Hello <th", "ink>reason", "ing here</thi", "nking> done."]
    final_acc = ""
    think_acc = ""
    for c in chunks:
        f, t = s.feed(c)
        final_acc += f
        think_acc += t
    final_acc += s.drain()
    assert final_acc == "Hello  done."
    assert think_acc == "reasoning here"


def test_per_character_streaming() -> None:
    """Worst-case: each chunk is a single character."""
    s = ThinkSplitter()
    final_acc = ""
    think_acc = ""
    for ch in "hi <think>plan</think>!":
        f, t = s.feed(ch)
        final_acc += f
        think_acc += t
    final_acc += s.drain()
    assert final_acc == "hi !"
    assert think_acc == "plan"


def test_no_tags() -> None:
    s = ThinkSplitter()
    final, think = s.feed("just plain text without any tags")
    assert final == "just plain text without any tags"
    assert think == ""


def test_non_recognized_tag_passes_through() -> None:
    """``<list>`` is not a think tag — it should land in final text."""
    s = ThinkSplitter()
    final, think = s.feed("python uses <list> syntax")
    final += s.drain()
    assert final == "python uses <list> syntax"
    assert think == ""


def test_case_insensitive_tags() -> None:
    s = ThinkSplitter()
    final, think = s.feed("<THINK>upper</THINK> ok")
    assert final == " ok"
    assert think == "upper"


def test_empty_feed() -> None:
    s = ThinkSplitter()
    final, think = s.feed("")
    assert final == ""
    assert think == ""


def test_multiple_think_blocks() -> None:
    s = ThinkSplitter()
    final, think = s.feed("a<think>1</think>b<think>2</think>c")
    assert final == "abc"
    assert think == "12"


def test_unclosed_think_at_end_drains() -> None:
    """If the model never closes the tag, drain returns the buffered text
    so the caller can decide what to do with it (typically: show as
    final text since the model misbehaved)."""
    s = ThinkSplitter()
    final, think = s.feed("hi <think>partial...")
    # While inside an open think block, the contents stream to the
    # thinking lane.
    assert final == "hi "
    assert think == "partial..."
    # No more closing tag arrives — drain returns whatever buffered
    # bytes are left (none here, since safe-emit released them).
    assert s.drain() == ""


def test_partial_tag_held_back_until_disambiguated() -> None:
    """A trailing ``<th`` mustn't be emitted to final until we know
    whether it grows into ``<think>`` or e.g. ``<thread>``."""
    s = ThinkSplitter()
    final, _ = s.feed("hello <th")
    assert final == "hello "  # <th is held back
    # Now make it clear it's NOT a think tag — flush.
    final, _ = s.feed("read>safe")
    assert final == "<thread>safe"


def test_splitter_can_be_reused_after_drain() -> None:
    s = ThinkSplitter()
    s.feed("first <think>plan</think> reply")
    s.drain()

    final, think = s.feed("second <think>plan2</think> reply")
    assert final == "second  reply"
    assert think == "plan2"


def test_text_with_lone_lt_sign() -> None:
    """A naked ``<`` not followed by a recognized tag prefix should
    eventually land in final text (after the safe-emit window allows)."""
    s = ThinkSplitter()
    final, _ = s.feed("if a < b then")
    final += s.drain()
    assert final == "if a < b then"
