"""YAML frontmatter helpers for markdown workspace files."""

from __future__ import annotations

import re
from typing import Any

import yaml

_CLOSING_FENCE_RE = re.compile(r"(?m)^---[ \t]*\r?$")


def _find_frontmatter(text: str) -> tuple[int, int, int] | None:
    """Locate the YAML frontmatter block (``---`` ... ``---``) in *text*.

    The frontmatter does not have to start at the first line; leading HTML
    comments or empty lines are skipped. Returns the YAML content start,
    content end, and body start, or ``None`` when no valid block exists.
    Only an entire unindented fence line closes the block; a YAML key
    starting with ``---`` or an indented literal is still metadata.
    """
    # Fast path: frontmatter at very beginning
    if text.startswith("---\n") or text.startswith("---\r\n"):
        start = 0
    else:
        # Scan for the first ``^---\s*$`` line (ignoring leading whitespace-only
        # lines and HTML comment blocks).
        idx = 0
        while idx < len(text):
            nxt = text.find("\n", idx)
            if nxt == -1:
                nxt = len(text)
            line = text[idx:nxt].strip()
            if line == "---":
                start = idx
                break
            # Skip HTML comment blocks: <!-- ... -->
            if line.startswith("<!--"):
                # Find the closing -->. Search from the line start: a one-line
                # comment closes on its own line, which the earlier search
                # (starting after the newline) missed.
                close = text.find("-->", idx)
                if close == -1:
                    return None
                idx = close + 3
                if idx < len(text) and text[idx] == "\n":
                    idx += 1
                continue
            # Skip empty/whitespace lines
            if not line:
                idx = nxt + 1
                continue
            # Any other non-frontmatter, non-comment content means no
            # frontmatter block exists.
            return None
        else:
            return None

    # Consume the complete opening line, including whitespace and CRLF.
    content_start = text.find("\n", start)
    if content_start == -1:
        return None
    content_start += 1
    closing = _CLOSING_FENCE_RE.search(text, content_start)
    if closing is None:
        return None
    return content_start, closing.start(), closing.end()


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split markdown with optional ``---`` YAML frontmatter.

    Returns ``(metadata_dict, body)``. Malformed frontmatter is treated as
    no-frontmatter (the file is its own body).

    The frontmatter block may be preceded by HTML comments or empty lines;
    the first ``---`` ... ``---`` fence anywhere in the file is used.
    """
    positions = _find_frontmatter(text)
    if positions is None:
        return {}, text
    content_start, content_end, body_start = positions
    raw = text[content_start:content_end]
    body = text[body_start:].lstrip("\r\n")
    try:
        meta = yaml.safe_load(raw) or {}
        if not isinstance(meta, dict):
            return {}, text
        return meta, body
    except yaml.YAMLError:
        return {}, text


def is_agent_file(text: str) -> bool:
    """True when the file contains a YAML frontmatter fence.

    Leading HTML comments and empty lines are tolerated; the first
    ``---\\n`` fence in the file is recognized as the frontmatter start.
    """
    return _find_frontmatter(text) is not None
