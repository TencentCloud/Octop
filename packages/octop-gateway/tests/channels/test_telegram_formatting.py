"""Content and parsing invariants for Telegram HTML message chunks."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from octop_gateway.channels.telegram.format_html import markdown_to_telegram_html, split_telegram_html


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _assert_chunks(html: str, expected: str, limit: int = 4000) -> list[tuple[str, str]]:
    chunks = split_telegram_html(html, limit)
    assert "".join(plain for _, plain in chunks) == expected
    for fragment, plain in chunks:
        assert plain
        assert _units(fragment) <= limit
        assert _units(plain) <= limit
        root = ET.fromstring(f"<root>{fragment}</root>")
        assert "".join(root.itertext()) == plain
    return chunks


def test_short_message_has_exact_html_and_readable_fallback() -> None:
    html = markdown_to_telegram_html("**Bold** and `x < 2` [site](https://example.com)")
    assert split_telegram_html(html) == [
        ('<b>Bold</b> and <code>x &lt; 2</code> <a href="https://example.com">site</a>', "Bold and x < 2 site")
    ]


@pytest.mark.parametrize("wrapper", ["<b><i>{}</i></b>", '<pre><code class="language-python">{}</code></pre>'])
def test_long_nested_formatting_reopens_balanced_tags(wrapper: str) -> None:
    content = "print(&lt;x&gt;)\n" * 1100
    chunks = _assert_chunks(wrapper.format(content), "print(<x>)\n" * 1100)
    assert len(chunks) > 1
    start, end = wrapper.split("{}")
    assert all(html.startswith(start) and html.endswith(end) for html, _ in chunks)


def test_entities_and_astral_emoji_survive_boundaries() -> None:
    expected = "a" * 3988 + "😀<&>🧑🏽‍💻" * 1100
    html = markdown_to_telegram_html(expected)
    _assert_chunks(html, expected)


def test_newlines_spaces_and_literal_markup_are_preserved() -> None:
    expected = "  <b>literal</b> &amp;\n\n" * 500 + "tail  "
    _assert_chunks(markdown_to_telegram_html(expected), expected)


def test_numeric_and_named_entities_decode_once() -> None:
    chunks = _assert_chunks("<b>&#128512;&#x1F600;&quot;&amp;lt;</b>" * 30, '😀😀"&lt;' * 30, 64)
    assert len(chunks) > 1


def test_long_link_attribute_degrades_to_text_without_markup() -> None:
    html = '<a href="https://example.com/' + "x" * 4500 + '">' + "label " * 1000 + "</a>"
    chunks = _assert_chunks(html, "label " * 1000)
    assert all("<a " not in fragment for fragment, _ in chunks)


def test_link_attributes_escape_quotes_and_ampersands() -> None:
    html = markdown_to_telegram_html('[label](https://example.com/?a=1&b="quoted")')
    root = ET.fromstring(f"<root>{html}</root>")
    assert root[0].attrib == {"href": 'https://example.com/?a=1&b="quoted"'}
    _assert_chunks(html, "label")


def test_small_limit_degrades_deep_wrappers_and_keeps_entities() -> None:
    _assert_chunks("<b><i><u>&lt;😀&amp;</u></i></b>", "<😀&", 12)


@pytest.mark.parametrize(
    "wrapper",
    [
        "<code>{}</code>",
        "<blockquote>{}</blockquote>",
        "<tg-spoiler>{}</tg-spoiler>",
        '<a href="https://example.com">{}</a>',
    ],
)
def test_other_supported_wrappers_keep_content(wrapper: str) -> None:
    chunks = _assert_chunks(wrapper.format("x &amp; y\n" * 1500), "x & y\n" * 1500)
    start, end = wrapper.split("{}")
    assert all(html.startswith(start) and html.endswith(end) for html, _ in chunks)


def test_exact_utf16_boundary_and_emoji_never_exceed_limit() -> None:
    assert split_telegram_html("a" * 4000) == [("a" * 4000, "a" * 4000)]
    assert split_telegram_html("😀" * 2001) == [("😀" * 2000, "😀" * 2000), ("😀", "😀")]
    assert split_telegram_html("&lt;" * 1001) == [("&lt;" * 1000, "<" * 1000), ("&lt;", "<")]


@pytest.mark.parametrize("html", ["<b>unclosed", "<b><i>crossed</b></i>", "text</b>"])
def test_unbalanced_input_is_rejected(html: str) -> None:
    with pytest.raises(ValueError, match="balanced"):
        split_telegram_html(html)


@pytest.mark.parametrize("text", ["**bold _crossed** italic_", "**bold\n> quoted**", "\\x00PH0\\x00 `code`"])
def test_formatter_output_is_always_balanced(text: str) -> None:
    html = markdown_to_telegram_html(text)
    chunks = split_telegram_html(html)
    for fragment, _ in chunks:
        ET.fromstring(f"<root>{fragment}</root>")


def test_empty_input_and_empty_tags_produce_no_messages() -> None:
    assert split_telegram_html("") == []
    assert split_telegram_html("<b></b>") == []


@pytest.mark.parametrize("limit", [0, 4, 4001])
def test_invalid_limit_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        split_telegram_html("text", limit)
