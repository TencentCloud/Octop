"""YAML frontmatter helpers for markdown workspace files."""

from __future__ import annotations

from typing import Any

import yaml


def _find_frontmatter(text: str) -> tuple[int, int] | None:
    """Locate the YAML frontmatter block (``---`` ... ``---``) in *text*.

    The frontmatter does not have to start at the first line; leading HTML
    comments or empty lines are skipped.  Returns ``(start, end)`` where
    *start* is the index of the first ``---`` line and *end* is the index
    of the closing ``---`` line, or ``None`` when no valid block exists.
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

    # Now find the closing ---
    rest = text[start + 3 :]  # skip past the opening ---
    end_marker = rest.find("\n---")
    if end_marker == -1:
        return None
    return start, start + 3 + end_marker + 4  # +4 for "\n---"


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
    start, end = positions
    # start points to the opening ---, end points past the closing ---
    raw = text[start + 3 : end - 4]  # skip opening ---\n, exclude closing \n---
    body = text[end:].lstrip("\n")
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
