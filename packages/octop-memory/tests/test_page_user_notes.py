"""Tests for ``## My Notes`` user-section preservation (D34-A)."""

from __future__ import annotations

from octop_memory.pipeline.page.user_notes import (
    detect_dropped_notes,
    extract_user_notes,
    has_user_notes,
    merge_user_notes,
)


class TestExtract:
    def test_no_notes(self) -> None:
        body, notes = extract_user_notes("just a paragraph")
        assert body == "just a paragraph"
        assert notes == ""

    def test_empty(self) -> None:
        assert extract_user_notes("") == ("", "")

    def test_simple_block(self) -> None:
        md = "## Summary\nfoo\n\n## My Notes\nbar baz"
        body, notes = extract_user_notes(md)
        assert body == "## Summary\nfoo"
        assert notes == "## My Notes\nbar baz"

    def test_notes_runs_to_eof_through_other_h2(self) -> None:
        # Once notes section starts, anything until EOF belongs to the user
        # — even what looks like another ## heading.
        md = "intro\n\n## My Notes\nline1\n\n## not really a new section\nline2"
        body, notes = extract_user_notes(md)
        assert body == "intro"
        assert "## not really a new section" in notes
        assert "line2" in notes

    def test_case_sensitive(self) -> None:
        # Lower-case "my notes" does NOT match (contract is exact heading text).
        md = "## my notes\nstuff"
        body, notes = extract_user_notes(md)
        assert body == "## my notes\nstuff"
        assert notes == ""

    def test_extra_spaces_in_heading_match(self) -> None:
        # Multiple spaces between ## and "My Notes" still count as the heading.
        md = "## My Notes  \nuser"
        _body, notes = extract_user_notes(md)
        assert "## My Notes" in notes
        assert "user" in notes


class TestHasUserNotes:
    def test_present(self) -> None:
        assert has_user_notes("body\n## My Notes\nx") is True

    def test_absent(self) -> None:
        assert has_user_notes("just summary") is False

    def test_empty(self) -> None:
        assert has_user_notes("") is False
        assert has_user_notes(None) is False  # type: ignore[arg-type]


class TestMerge:
    def test_no_existing_notes_returns_body(self) -> None:
        out = merge_user_notes("rendered body", "")
        assert out == "rendered body"

    def test_appends_notes_to_clean_body(self) -> None:
        out = merge_user_notes("rendered", "## My Notes\nuser stuff")
        assert "rendered" in out
        assert "## My Notes" in out
        assert "user stuff" in out
        assert out.endswith("user stuff")

    def test_drops_llm_emitted_notes_section(self) -> None:
        # LLM accidentally wrote a notes section — we MUST drop it before
        # splicing the user's saved one back in.
        llm_body = "rendered\n\n## My Notes\nLLM hallucinated text\n"
        preserved = "## My Notes\nuser's actual notes"
        out = merge_user_notes(llm_body, preserved)
        assert "LLM hallucinated text" not in out
        assert "user's actual notes" in out

    def test_empty_body_with_notes(self) -> None:
        out = merge_user_notes("", "## My Notes\njust notes")
        assert out == "## My Notes\njust notes"

    def test_strips_trailing_whitespace(self) -> None:
        out = merge_user_notes("body\n\n", "## My Notes\nx\n\n")
        assert not out.endswith("\n")


class TestDetectDropped:
    def test_dropped_returns_true(self) -> None:
        before = "intro\n## My Notes\nuser"
        after = "intro"
        assert detect_dropped_notes(before=before, after=after) is True

    def test_preserved_returns_false(self) -> None:
        before = "intro\n## My Notes\nuser"
        after = "newer intro\n## My Notes\nuser"
        assert detect_dropped_notes(before=before, after=after) is False

    def test_neither_has_notes(self) -> None:
        assert detect_dropped_notes(before="a", after="b") is False
