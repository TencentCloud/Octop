"""tests/unit/utils/test_frontmatter.py"""

from __future__ import annotations

import pytest

from octop.infra.utils.frontmatter import is_agent_file, parse_frontmatter


def test_frontmatter_at_first_line() -> None:
    meta, body = parse_frontmatter("---\nname: foo\n---\nbody")
    assert meta == {"name": "foo"}
    assert body == "body"
    assert is_agent_file("---\nname: foo\n---\nbody")


def test_leading_multiline_html_comment_is_skipped() -> None:
    text = "<!-- agent-params\n     more -->\n---\nname: foo\n---\nbody"
    meta, body = parse_frontmatter(text)
    assert meta == {"name": "foo"}
    assert body == "body"
    assert is_agent_file(text)


def test_leading_one_line_html_comment_is_skipped() -> None:
    """The documented invariant: leading HTML comments are skipped before the
    first ``---`` fence, including a comment that closes on its own line."""
    text = "<!-- agent-params -->\n---\nname: foo\n---\nbody"
    meta, body = parse_frontmatter(text)
    assert meta == {"name": "foo"}
    assert body == "body"
    assert is_agent_file(text)


def test_leading_blank_lines_are_skipped() -> None:
    text = "\n\n---\nname: foo\n---\nbody"
    meta, body = parse_frontmatter(text)
    assert meta == {"name": "foo"}
    assert body == "body"


def test_no_frontmatter_returns_the_whole_text() -> None:
    text = "# Title\n\nParagraph"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == text
    assert not is_agent_file(text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("suffix", ["extra", "-", " # comment", ":", "---"])
def test_closing_fence_must_fill_the_line(newline: str, suffix: str) -> None:
    text = newline.join(["---", "name: foo", f"---{suffix}", "body"])

    assert parse_frontmatter(text) == ({}, text)
    assert not is_agent_file(text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("trailing_space", ["", " ", "\t", " \t "])
def test_complete_fence_preserves_body(newline: str, trailing_space: str) -> None:
    expected_body = f"  # Heading{newline}{newline}  indented body{newline}"
    text = newline.join(["---", "name: foo", f"---{trailing_space}", expected_body])

    assert parse_frontmatter(text) == ({"name": "foo"}, expected_body)
    assert is_agent_file(text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_fence_like_yaml_key_does_not_truncate_metadata(newline: str) -> None:
    text = newline.join(
        [
            "---",
            "name: foo",
            "---description: details",
            "enabled: true",
            "---",
            "body",
        ]
    )

    assert parse_frontmatter(text) == (
        {"name": "foo", "---description": "details", "enabled": True},
        "body",
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_indented_fence_in_yaml_literal_is_content(newline: str) -> None:
    text = newline.join(["---", "name: foo", "description: |", "  ---", "  details", "---", "body"])

    assert parse_frontmatter(text) == (
        {"name": "foo", "description": "---\ndetails\n"},
        "body",
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_comment_prefix_and_whitespace_fences(newline: str) -> None:
    text = newline.join(["<!-- configuration -->", "", "--- \t", "name: foo", "---\t", "", "body"])

    assert parse_frontmatter(text) == ({"name": "foo"}, "body")
    assert is_agent_file(text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_empty_frontmatter_and_empty_body(newline: str) -> None:
    text = newline.join(["---", "--- \t"])

    assert parse_frontmatter(text) == ({}, "")
    assert is_agent_file(text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_invalid_yaml_keeps_original_text(newline: str) -> None:
    text = newline.join(["---", "name: [unfinished", "--- \t", "body"])

    assert parse_frontmatter(text) == ({}, text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_non_mapping_frontmatter_keeps_original_text(newline: str) -> None:
    text = newline.join(["---", "- item", "--- \t", "body"])

    assert parse_frontmatter(text) == ({}, text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_blank_body_lines_keep_existing_trimming_behavior(newline: str) -> None:
    text = newline.join(["---", "name: foo", "---", "", "", "body", "", "tail"])

    assert parse_frontmatter(text) == ({"name": "foo"}, f"body{newline}{newline}tail")


def test_fence_at_end_of_file() -> None:
    text = "---\nname: foo\n---"

    assert parse_frontmatter(text) == ({"name": "foo"}, "")
    assert is_agent_file(text)


def test_missing_closing_fence_keeps_original_text() -> None:
    text = "---\nname: foo\n"

    assert parse_frontmatter(text) == ({}, text)
    assert not is_agent_file(text)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    ("indicator", "expected"),
    [("|", "details\n"), ("|-", "details"), ("|+", "details\n\n")],
)
def test_yaml_literal_chomping_preserves_metadata_newlines(
    newline: str, indicator: str, expected: str
) -> None:
    text = newline.join(["---", f"description: {indicator}", "  details", "", "---", "body"])

    assert parse_frontmatter(text) == ({"description": expected}, "body")


@pytest.mark.parametrize("opening", [" ---", "\t---", "  --- \t"])
def test_opening_fence_whitespace_does_not_become_yaml(opening: str) -> None:
    text = f"{opening}\nname: foo\n---\nbody"

    assert parse_frontmatter(text) == ({"name": "foo"}, "body")
    assert is_agent_file(text)
