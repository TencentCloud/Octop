"""tests/unit/utils/test_frontmatter.py"""

from __future__ import annotations

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


def test_bom_prefixed_frontmatter_is_parsed() -> None:
    """A BOM is an encoding artifact: the fence after it still opens frontmatter.

    Windows editors (Notepad, and the Windows PowerShell 5.1
    ``Set-Content -Encoding UTF8`` switch) prepend one to files they save.
    """
    text = "\ufeff---\nname: foo\ndescription: bar\n---\nbody"
    meta, body = parse_frontmatter(text)
    assert meta == {"name": "foo", "description": "bar"}
    assert body == "body"
    assert "\ufeff" not in body
    assert is_agent_file(text)


def test_plain_frontmatter_is_unaffected_by_bom_handling() -> None:
    meta, body = parse_frontmatter("---\nname: foo\n---\nbody")
    assert meta == {"name": "foo"}
    assert body == "body"


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
