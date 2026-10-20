"""Streaming-friendly splitter for ``<think>...</think>`` blocks."""

from __future__ import annotations

import re

_OPEN_TAG_RE = re.compile(r"<thinking>|<think>", re.IGNORECASE)
_CLOSE_TAG_RE = re.compile(r"</thinking>|</think>", re.IGNORECASE)
_MAX_TAG_LEN = len("</thinking>")


class ThinkSplitter:
    """Stateful splitter for streaming text with ``<think>`` blocks."""

    def __init__(self) -> None:
        self._in_think: bool = False
        self._buffer: str = ""

    @property
    def in_think(self) -> bool:
        """Whether the parser is currently inside a think block."""
        return self._in_think

    def feed(self, text: str) -> tuple[str, str]:
        """Consume an incremental text delta."""
        if not text:
            return "", ""

        self._buffer += text
        final_parts: list[str] = []
        thinking_parts: list[str] = []

        while self._buffer:
            if self._in_think:
                close_match = _CLOSE_TAG_RE.search(self._buffer)
                if close_match:
                    thinking_parts.append(self._buffer[: close_match.start()])
                    self._buffer = self._buffer[close_match.end() :]
                    self._in_think = False
                    continue
                safe = self._safe_emit_window()
                if safe > 0:
                    thinking_parts.append(self._buffer[:safe])
                    self._buffer = self._buffer[safe:]
                break
            else:
                open_match = _OPEN_TAG_RE.search(self._buffer)
                if open_match:
                    final_parts.append(self._buffer[: open_match.start()])
                    self._buffer = self._buffer[open_match.end() :]
                    self._in_think = True
                    continue
                safe = self._safe_emit_window()
                if safe > 0:
                    final_parts.append(self._buffer[:safe])
                    self._buffer = self._buffer[safe:]
                break

        return "".join(final_parts), "".join(thinking_parts)

    def drain(self) -> str:
        """Flush trailing buffered text at end-of-stream."""
        leftover = self._buffer
        self._buffer = ""
        self._in_think = False
        return leftover

    def _safe_emit_window(self) -> int:
        """Number of leading bytes safe to emit without ambiguating a tag."""
        if "<" not in self._buffer:
            return len(self._buffer)
        last_lt = self._buffer.rfind("<")
        tail = self._buffer[last_lt:]
        if _could_be_tag_prefix(tail):
            return last_lt
        return len(self._buffer)


def _could_be_tag_prefix(s: str) -> bool:
    """True if ``s`` (starting with ``<``) could grow into a recognized tag."""
    if len(s) > _MAX_TAG_LEN:
        return False
    lower = s.lower()
    candidates = ("<think>", "</think>", "<thinking>", "</thinking>")
    return any(c.startswith(lower) for c in candidates)


__all__ = ["ThinkSplitter"]
