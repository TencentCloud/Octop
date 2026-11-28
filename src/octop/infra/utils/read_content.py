"""Normalize backend file-read payloads for display and persistence."""

from __future__ import annotations

from typing import Any

# deepagents.backends.utils.EMPTY_CONTENT_WARNING — shown to LLM tools, not
# humans. Hard-coded here so an internal deepagents symbol move cannot break
# startup.
_EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"


def coerce_read_content(content: Any) -> str:
    """Normalize a backend read payload (``None`` / line list / sentinel) to str."""
    if content is None:
        return ""
    if isinstance(content, list):
        content = "\n".join(str(line) for line in content)
    text = str(content)
    if text == _EMPTY_CONTENT_WARNING:
        return ""
    return text


__all__ = ["coerce_read_content"]
