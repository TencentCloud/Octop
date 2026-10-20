"""MemoryService — the transport-neutral facade for in-process hosts.

In-process Python hosts (e.g. octop-harness, Hermes) talk to memory through
this facade instead of building JSON-RPC envelopes for the bridge adapter.
It exposes clean, typed methods for the host lifecycle:

- **read**:  :meth:`recall` (prompt-injectable text), :meth:`search` / :meth:`get` (tools)
- **write**: :meth:`save` (explicit memory), :meth:`capture_turn` (L0 raw events),
  :meth:`extract` (L0 → L2/L3 distill)

Architecture — one runtime, two adapters
----------------------------------------
The host-neutral operations (capture policy, extraction orchestration,
multi-source search, path projection) live in
:class:`octop_memory.application.runtime.MemoryRuntime`. ``MemoryService`` is
the in-process adapter over that runtime; ``adapters.bridge.Bridge`` is the
JSON-RPC adapter used by subprocess hosts.

The model is injected as an :class:`~octop_memory.ports.llm.LLMClient`; without one,
``extract`` degrades to ``failure_reason`` (L0 capture + FTS recall still work).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from octop_memory.application.config import MemoryRuntimeConfig
from octop_memory.application.runtime import MemoryRuntime
from octop_memory.core import Memory
from octop_memory.pipeline.recall import DEFAULT_RECALL_LIMIT, RecallResult, recall_for_prompt
from octop_memory.ports.llm import LLMClient
from octop_memory.types import MemoryNode

logger = logging.getLogger("octop_memory")

_DEFAULT_HOST = "host"


class MemoryService:
    """Clean, typed, transport-neutral entry point to a :class:`Memory`.

    Args:
        memory: backing :class:`Memory` instance.
        llm: optional :class:`LLMClient` for extraction / promotion / page
            regeneration. ``None`` → distillation degrades gracefully.
        config: optional :class:`MemoryRuntimeConfig` (or dict) for capture / recall /
            privacy / extraction policy. Defaults are the balanced profile.
        host_files: optional host Markdown index for file-shaped ``get``.
        host: the ``RawEvent.host`` tag stamped on captured events
            (e.g. ``"octop-harness"`` / ``"hermes"``).
        manual_documents_provider: optional backend-aware reader of USER.md and
            MEMORY.md, used after saves/promotions, never per prompt turn.
    """

    def __init__(
        self,
        memory: Memory,
        *,
        llm: LLMClient | None = None,
        config: MemoryRuntimeConfig | dict[str, Any] | None = None,
        host_files: Any | None = None,
        host: str = _DEFAULT_HOST,
        manual_documents_provider: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._memory = memory
        self._host = host
        self._runtime = MemoryRuntime(
            memory,
            host_files=host_files,
            config=config,
            llm=llm,
            manual_documents_provider=manual_documents_provider,
        )

    @property
    def memory(self) -> Memory:
        """The backing :class:`Memory` instance."""
        return self._memory

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        *,
        thread_id: str | None = None,
        session_id: str | None = None,
        limit: int = DEFAULT_RECALL_LIMIT,
        manual_context: dict[str, str] | None = None,
    ) -> RecallResult:
        """Recall relevant memories as prompt-injectable text.

        Returns a :class:`RecallResult`; use ``.rendered`` for a ready-to-inject
        markdown block or ``.snippets`` to format your own. No model required.
        ``session_id`` (falling back to ``thread_id``) excludes raw from
        the current conversation so auto-inject does not echo this turn.
        ``manual_context`` is the actual session document snapshot; duplicates
        are suppressed only against that supplied context.
        """
        return recall_for_prompt(
            self._memory,
            query,
            thread_id=thread_id,
            session_id=session_id,
            limit=limit,
            manual_context=manual_context,
        )

    def reconcile_manual_documents(
        self, documents: dict[str, str], *, is_current: Callable[[], bool] | None = None
    ) -> dict[str, Any]:
        """Compare user-owned documents with atoms; quarantine conflicts for review.

        The caller supplies current file contents, never a stale chat snapshot.
        ``is_current`` can cancel applying a plan if files changed during analysis.
        Partial/unavailable semantic checks are explicit in the result.
        """
        return self._runtime.reconcile_manual_documents({"documents": documents}, is_current=is_current)

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        corpus: str = "all",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Multi-source search for the ``memory_search`` tool.

        Returns the documented hit payload::

            {"hits": [{"path", "score", "snippet", "layer", "role_hint",
                       "occurred_at", "source_id"}, ...],
             "total": int, "empty_reason": str | None}
        """
        return self._runtime.memory_search(
            {"query": query, "maxResults": max_results, "corpus": corpus, "thread_id": thread_id}
        )

    def get(self, path: str, *, start: int | None = None, lines: int | None = None) -> dict[str, Any]:
        """Resolve a virtual memory path to its source excerpt.

        Resolve a virtual path (``atom/<id>.md`` / ``page/<entity>.md`` /
        ``raw/<date>/<id>.md``) to its source excerpt for the ``memory_get`` tool.
        """
        params: dict[str, Any] = {"path": path}
        if start is not None:
            params["from"] = start
        if lines is not None:
            params["lines"] = lines
        return self._runtime.memory_get(params)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        content: str,
        *,
        topic: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryNode:
        """Explicitly save a durable memory.

        This is the in-process equivalent of a host exposing a
        ``memory_save`` tool. It uses :meth:`Memory.store`, so manual saves
        enter the canonical atom/tree path instead of being kept only as raw
        transcript events.
        """
        node = self._memory.store(content, topic=topic, metadata=metadata)
        review = self._runtime.review_new_memory()
        if review is not None:
            atom = self._memory.get_atom(node.atom_id) if node.atom_id else None
            node = replace(
                node,
                metadata={
                    **node.metadata,
                    "manual_document_review": review,
                    "manual_document_conflict": bool(atom and atom.deprecated_at),
                },
            )
        return node

    def capture_turn(
        self,
        *,
        user: str | None = None,
        assistant: str | None = None,
        session_id: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Capture one conversation turn as L0 raw events.

        ``user`` / ``assistant`` are the message *contents*; ``user_id`` is the
        user identity. Privacy / role / min-length / memory-echo filters are
        applied by the underlying capture policy. Non-blocking discipline (run
        in a background thread) is the caller's responsibility.
        """
        events: list[dict[str, Any]] = []
        if user:
            events.append({"event_type": "user_message", "content": user})
        if assistant:
            events.append({"event_type": "assistant_message", "content": assistant})
        return self._runtime.capture(
            {
                "session_id": session_id,
                "thread_id": thread_id,
                "user": user_id,
                "host": self._host,
                "events": events,
            }
        )

    def extract(
        self,
        session_id: str,
        *,
        incremental: bool = True,
        promote: bool = True,
        regen_pages: bool = True,
    ) -> dict[str, Any]:
        """Distill a session's raw events: L0 → L1 → L2 → L3 in one call.

        Requires an injected ``llm``; without one the result carries a
        ``failure_reason`` instead of raising. Run off the conversation hot path.
        """
        logger.info(
            "memory.trigger extract start host=%s session=%s incremental=%s promote=%s regen_pages=%s",
            self._host,
            session_id,
            incremental,
            promote,
            regen_pages,
        )
        result = self._runtime.extract(
            {
                "session_id": session_id,
                "incremental": incremental,
                "promote": promote,
                "regen_pages": regen_pages,
            }
        )
        logger.info(
            "memory.trigger extract done host=%s session=%s result=%s",
            self._host,
            session_id,
            {k: result.get(k) for k in ("candidates", "promoted", "failure_reason") if k in result}
            if isinstance(result, dict)
            else result,
        )
        return result

    # ------------------------------------------------------------------
    # M5 — Diary digest (daily / weekly / monthly)
    # ------------------------------------------------------------------

    def generate_digest(
        self,
        *,
        period_kind: str = "daily",
        when: Any | None = None,
        period_key: str | None = None,
        output_dir: Any | None = None,
    ) -> dict[str, Any]:
        """Generate (or regenerate) one Episode digest.

        ``period_kind`` is ``"daily"`` (default), ``"weekly"``, or
        ``"monthly"``. Daily reads episodes in the day; weekly/monthly
        roll up the daily digests already generated within the period
        (falling back to episodes if no daily digests exist yet).

        Result is persisted both as a SQLite row and (if ``output_dir``
        is given) as a markdown file under ``<output_dir>/`` (daily
        files are placed in the ``daily/`` subfolder so the top-level
        directory stays scannable).

        Returns a JSON-friendly summary; the raw ``DigestRecord`` is
        always available via ``memory.get_digest``.
        """
        from pathlib import Path as _Path

        from octop_memory.pipeline.episode.digest import generate_digest as _generate

        if period_kind not in ("daily", "weekly", "monthly"):
            raise ValueError(f"period_kind must be 'daily', 'weekly', or 'monthly'; got {period_kind!r}")

        out_dir = _Path(output_dir) if output_dir is not None else None
        result = _generate(
            self._memory,
            period_kind=period_kind,  # type: ignore[arg-type]
            when=when,
            period_key=period_key,
            llm=self._runtime.llm if self._runtime.llm_configured else None,
            output_dir=out_dir,
        )
        return {
            "period_kind": result.digest.period_kind,
            "period_key": result.digest.period_key,
            "episode_count": result.episode_count,
            "used_llm": result.used_llm,
            "file_path": str(result.file_path) if result.file_path else None,
            "markdown_preview": result.digest.markdown[:280],
        }


__all__ = ["MemoryService"]
