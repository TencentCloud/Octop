"""LLM tool functions for the memory system.

These are registered as agent tools at construction time. They use
``langchain_core.tools.tool`` to produce ``StructuredTool`` instances.

The agent exposes service-backed tools:

* ``memory_search(query, max_results)`` routes through the
  :class:`MemoryService` ranker (atom + page + raw).
* ``memory_get(path, start, lines)`` resolves a virtual path returned by
  ``memory_search``.
* ``memory_save(content, topic)`` explicitly persists a fact through
  :meth:`MemoryService.save`.

``MEMORY.md`` is user-maintained strong memory, loaded in full into chat
context. Remember requests use ``memory_save`` and never edit that file.
Background distillation continues to extract facts from captured conversation.

Each tool wraps the underlying service call in a broad ``except`` so that
storage / DB faults degrade into a human-readable string instead of
crashing the agent turn or leaking a stack trace into the conversation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool, tool

if TYPE_CHECKING:
    from octop_memory import MemoryService

logger = logging.getLogger(__name__)


def build_memory_tools(service: MemoryService) -> list[StructuredTool]:
    """Build :class:`MemoryService`-backed LLM tools.

    Exposes recall and explicit persistence tools:

    * ``memory_search(query, max_results)`` — ranked hits across
      atom / entity_page / raw. Each hit carries a virtual ``path`` you
      can pass to ``memory_get``.
    * ``memory_get(path, start, lines)`` — resolve a virtual path to its
      source markdown excerpt.

    * ``memory_save(content, topic)`` — persist canonical memory through the
      service, independently of the user-maintained ``MEMORY.md``.

    Args:
        service: A :class:`MemoryService` to bind the tools to.
    """

    @tool
    def memory_search(query: str, max_results: int = 5) -> str:
        """Search the agent's memory across atoms, entity pages, raw events.

        Use this when the user references something that happened in a
        previous turn or session, or asks about a fact / preference /
        decision they expect the agent to remember.

        Args:
            query: Natural-language search query.
            max_results: Cap on returned hits (default 5, max ~20).
        """
        try:
            result = service.search(query, max_results=max_results)
        except Exception as exc:  # pragma: no cover - storage / ranker / model fault; pylint: disable=broad-except
            logger.warning("memory_search failed: %s", exc, exc_info=True)
            return f"memory_search failed: {exc.__class__.__name__}"
        hits = result.get("hits", []) if isinstance(result, dict) else []
        if not hits:
            empty_reason = result.get("empty_reason") if isinstance(result, dict) else None
            return f"No matching memory entries. ({empty_reason or 'empty'})"
        lines: list[str] = []
        for h in hits:
            path = h.get("path", "?")
            layer = h.get("layer") or "?"
            snippet = (h.get("snippet") or "").strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            lines.append(f"- [{layer}] {path}\n  {snippet}")
        return "Memory hits:\n" + "\n".join(lines)

    @tool
    def memory_get(path: str, start: int | None = None, lines: int | None = None) -> str:
        """Resolve a virtual memory path to its source text.

        Pass a path returned by ``memory_search`` (e.g.
        ``atom/<id>.md`` / ``page/<entity>.md`` / ``raw/<date>/<id>.md``)
        to read the underlying markdown.

        Args:
            path: The virtual path string from a ``memory_search`` hit.
            start: Optional 1-based line number to start at.
            lines: Optional number of lines to return.
        """
        try:
            result = service.get(path, start=start, lines=lines)
        except Exception as exc:  # pragma: no cover - storage / IO fault; pylint: disable=broad-except
            logger.warning("memory_get failed: %s", exc, exc_info=True)
            return f"memory_get failed: {exc.__class__.__name__}"
        if not isinstance(result, dict):
            return str(result)
        if result.get("error"):
            return f"memory_get error: {result.get('error')}"
        content = result.get("content")
        if isinstance(content, str):
            return content
        return str(result)

    @tool
    def memory_save(content: str, topic: str | None = None) -> str:
        """Save a durable fact, preference, decision, or lesson to octop-memory.

        Use when the user asks you to remember something. Store one concise
        fact per call; only confirm remembering after this tool succeeds.
        MEMORY.md and USER.md are user-maintained and must be left unchanged.

        Args:
            content: The fact to remember, preserving its scope and qualifiers.
            topic: Optional topic used to organize the memory.
        """
        if not content.strip():
            return "memory_save failed: content is empty"
        try:
            saved = service.save(content.strip(), topic=topic)
        except Exception as exc:  # pragma: no cover - fail softly at the tool boundary; pylint: disable=broad-except
            logger.warning("memory_save failed: %s", exc, exc_info=True)
            return f"memory_save failed: {exc.__class__.__name__}"
        review = saved.metadata.get("manual_document_review")
        if saved.metadata.get("manual_document_conflict"):
            return (
                "This fact conflicts with user-maintained USER.md/MEMORY.md and was moved to a review candidate. "
                "Tell the user about the conflict; do not claim it is confirmed. Manual documents take priority."
            )
        if isinstance(review, dict) and review.get("status") != "complete":
            return (
                "Memory saved to octop-memory, but manual-document review is incomplete. Tell the user it needs review."
            )
        return "Memory saved to octop-memory."

    return [memory_search, memory_get, memory_save]  # type: ignore[list-item]


__all__ = ["build_memory_tools"]
