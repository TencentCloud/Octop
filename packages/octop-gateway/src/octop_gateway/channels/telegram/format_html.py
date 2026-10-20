"""Convert standard Markdown to Telegram-compatible HTML."""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser


def _utf16_units(text: str) -> int:
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text)


class _HTMLRuns(HTMLParser):
    """Collect decoded text with the formatting active at each position."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = []
        self.runs: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = "".join(
            f' {name}="{escape(value, quote=True)}"' if value is not None else f" {name}" for name, value in attrs
        )
        self.stack.append((f"<{tag}{attributes}>", f"</{tag}>"))

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][1] != f"</{tag}>":
            raise ValueError("Expected balanced Telegram HTML")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        if data:
            self.runs.append((data, tuple(self.stack)))


def split_telegram_html(html: str, limit: int = 4000) -> list[tuple[str, str]]:
    """Split formatter-produced HTML into balanced HTML/plain-text pairs.

    Both serialized HTML (including reopened tags and escaped entities) and
    decoded text fit within ``limit`` UTF-16 code units. Characters and entities
    stay intact. Formatting whose wrappers cannot fit with a character is
    omitted for that character; its visible text is always retained. The input
    must be balanced Telegram HTML, as emitted by ``markdown_to_telegram_html``.
    Empty input produces no messages. Limits must be between 6 and 4000.
    """
    if not 6 <= limit <= 4000:
        raise ValueError("limit must be between 6 and 4000 UTF-16 code units")
    parser = _HTMLRuns()
    parser.feed(html)
    parser.close()
    if parser.stack:
        raise ValueError("Expected balanced Telegram HTML")

    chunks: list[tuple[str, str]] = []
    parts: list[str] = []
    plain: list[str] = []
    active: tuple[tuple[str, str], ...] = ()
    size = 0

    def flush() -> None:
        if plain:
            chunks.append(("".join(parts) + "".join(end for _, end in reversed(active)), "".join(plain)))
        parts.clear()
        plain.clear()

    for text, tags in parser.runs:
        wrapper_size = sum(_utf16_units(start + end) for start, end in tags)
        for char in text:
            encoded = escape(char, quote=False)
            char_size = _utf16_units(encoded)
            target = tags if wrapper_size + char_size <= limit else ()
            common = 0
            while common < min(len(active), len(target)) and active[common] == target[common]:
                common += 1
            transition = "".join(end for _, end in reversed(active[common:])) + "".join(
                start for start, _ in target[common:]
            )
            closing_size = sum(_utf16_units(end) for _, end in target)
            if size + _utf16_units(transition) + char_size + closing_size > limit:
                flush()
                active = ()
                size = 0
                transition = "".join(start for start, _ in target)
            parts.extend((transition, encoded))
            plain.append(char)
            size += _utf16_units(transition) + char_size
            active = target
    flush()
    return chunks


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown text to Telegram Bot API HTML subset."""
    if not text:
        return text

    original = text
    placeholders: list[str] = []

    def _ph(html_fragment: str) -> str:
        idx = len(placeholders)
        placeholders.append(html_fragment)
        return f"\x00PH{idx}\x00"

    def _code_block(m: re.Match[str]) -> str:
        lang = (m.group(1) or "").strip()
        code = _escape_html(m.group(2))
        if lang:
            return _ph(f'<pre><code class="language-{_escape_html(lang)}">{code}</code></pre>')
        return _ph(f"<pre>{code}</pre>")

    text = re.sub(r"```(\w*)\n?(.*?)```", _code_block, text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+)`", lambda m: _ph(f"<code>{_escape_html(m.group(1))}</code>"), text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: _ph(
            f'<a href="{escape(m.group(2).replace("<", "%3C").replace(">", "%3E"), quote=True)}">{_escape_html(m.group(1))}</a>'
        ),
        text,
    )

    text = _escape_html(text)
    text = re.sub(r"^[\*\-_]{3,}\s*$", "———", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}\s+(.+?)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    lines = text.split("\n")
    result_lines: list[str] = []
    quote_buf: list[str] = []

    def _flush_quote() -> None:
        if quote_buf:
            result_lines.append(f"<blockquote>{chr(10).join(quote_buf)}</blockquote>")
            quote_buf.clear()

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("&gt; "):
            quote_buf.append(stripped[5:])
        elif stripped == "&gt;":
            quote_buf.append("")
        else:
            _flush_quote()
            result_lines.append(line)
    _flush_quote()
    text = "\n".join(result_lines)

    text = re.sub(r"^(\s*)[\*\-]\s+", r"\1• ", text, flags=re.MULTILINE)
    text = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)
    text = re.sub(r"\*{3}(.+?)\*{3}", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*{2}(.+?)\*{2}", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    for idx, content in enumerate(placeholders):
        text = text.replace(f"\x00PH{idx}\x00", content)
    # Regex Markdown parsing can create crossed tags for overlapping markers.
    # Such input must still be deliverable without an exception or lost text.
    parser = _HTMLRuns()
    try:
        parser.feed(text)
        parser.close()
        if parser.stack:
            return _escape_html(original)
    except ValueError:
        return _escape_html(original)
    return text
