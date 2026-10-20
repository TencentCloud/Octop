"""Split outbound WeChat text into client-sized pieces."""

from __future__ import annotations

# Community iLink clients fail or truncate past about 2000 Unicode characters.
WEIXIN_TEXT_LIMIT = 2000


def split_weixin_text(text: str, limit: int = WEIXIN_TEXT_LIMIT) -> list[str]:
    """Split *text* on paragraph, line, then space boundaries."""
    remaining = text.strip()
    if not remaining:
        return []
    if len(remaining) <= limit:
        return [remaining]

    parts: list[str] = []
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        window = remaining[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = limit
        piece = remaining[:cut].strip()
        remaining = remaining[cut:].strip()
        if piece:
            parts.append(piece)
    return parts
