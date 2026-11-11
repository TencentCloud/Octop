"""Decide when a first user message should become an AI conversation title."""

from __future__ import annotations

# Bound the model prompt. Stored fallback titles are clipped separately to 40.
TITLE_SOURCE_MAX = 500


def clip_title_source(source: str) -> str:
    """Keep the start of a long first message for the title model."""
    text = " ".join((source or "").split())
    if len(text) <= TITLE_SOURCE_MAX:
        return text
    return text[:TITLE_SOURCE_MAX]


def should_autotitle(source: str | None, existing: str | None) -> bool:
    """True when this text should name a thread that does not have a title yet.

    Slash commands keep the existing clipped-command title. A non-empty stored
    title (including one the user typed) is left alone.
    """
    text = (source or "").strip()
    if not text or text.startswith("/"):
        return False
    return not (existing or "").strip()


def clean_generated_title(raw: str) -> str:
    """Collapse a model title to one plain line and drop wrapping quotes."""
    text = " ".join((raw or "").replace("\r", " ").replace("\n", " ").split())
    return text.strip().strip("\"'“”‘’「」").strip()
