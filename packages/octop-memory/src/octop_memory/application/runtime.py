"""Host-neutral memory runtime shared by in-process and JSON-RPC adapters."""

from __future__ import annotations

import logging
import re
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from octop_memory.application.config import (
    DEFAULT_CAPTURE_CFG,
    DEFAULT_EXTRACTION_CFG,
    DEFAULT_PRIVACY_CFG,
    DEFAULT_RECALL_CFG,
    MemoryRuntimeConfig,
    coerce_runtime_config,
)
from octop_memory.application.host_files import HostFilesIndex
from octop_memory.application.path_projection import (
    PathRef,
    excerpt_metadata,
    parse_path,
    render_atom_md,
    render_page_md,
    render_raw_md,
    slice_lines,
)
from octop_memory.domain.retention import is_runtime_error
from octop_memory.pipeline.episode import EpisodeExtractor
from octop_memory.pipeline.extractor import CandidateExtractor
from octop_memory.pipeline.page.regenerator import regenerate_dirty
from octop_memory.pipeline.promotion import PromotionWorker
from octop_memory.pipeline.promotion.llm_hook import ModelEscalationHook
from octop_memory.pipeline.recall import recall_for_prompt
from octop_memory.pipeline.recall.cache import RecallCache
from octop_memory.ports.llm import LLMClient, NoopLLMClient, OpenAICompatClient
from octop_memory.ports.llm._protocol import LLMClientError
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS
from octop_memory.types import RawEvent

if TYPE_CHECKING:
    from octop_memory.core import Memory

logger = logging.getLogger(__name__)

_CJK_UNICODE_START = 0x4E00
"""Start of the CJK Unified Ideographs Unicode block."""
_CJK_UNICODE_END = 0x9FFF
"""End of the CJK Unified Ideographs Unicode block."""
_ISO_DATE_LEN = 10
"""Length of an ISO 8601 date string (YYYY-MM-DD)."""

_MAX_TRACKED_SESSIONS = 16
"""LRU cap for the per-session extracted-event-id sets.

The TS shell triggers ``extract`` after every agent_end, so the same
session is re-extracted many times; tracking which raw event ids each
session has already fed through the extractor makes repeat calls cheap
(``no_new_events``) instead of burning an LLM call per turn."""


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
]


# ---------------------------------------------------------------------------
# Memory runtime
# ---------------------------------------------------------------------------


class MemoryRuntime:
    """Host-neutral operations over a :class:`Memory` instance."""

    def __init__(
        self,
        memory: Memory,
        *,
        host_files: HostFilesIndex | None = None,
        config: MemoryRuntimeConfig | dict[str, Any] | None = None,
        llm: LLMClient | None = None,
        manual_documents_provider: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        """Construct a runtime.

        Args:
            memory: backing :class:`Memory` instance.
            host_files: optional :class:`HostFilesIndex` for D51-C / D52-C
                real-file paths (``MEMORY.md`` / ``memory/YYYY-MM-DD.md`` /
                ``DREAMS.md``). When ``None``, ``memory_get`` against host paths
                raises ``_HostFileUnavailableError`` and ``memory_search`` only
                consults SQLite-backed atoms / tree nodes / raw events.
            llm: optional explicit :class:`LLMClient` for tests or host
                adapters. When ``None`` the client is built from the
                ``llm`` block of ``config`` (OpenAI-compatible endpoint),
                falling back to :class:`NoopLLMClient` — ``extract`` then
                degrades to ``failure_reason`` instead of erroring.
        """
        self._memory = memory
        self._host_files = host_files
        self._config = coerce_runtime_config(config)
        self._llm = llm if llm is not None else _build_llm_client(self._config.llm)
        self._llm_configured = not isinstance(self._llm, NoopLLMClient)
        self._manual_documents_provider = manual_documents_provider
        # session_id → ids of raw events already fed to the extractor.
        # See _MAX_TRACKED_SESSIONS for why this exists.
        self._extracted_ids: OrderedDict[str, set[str]] = OrderedDict()
        # Per-runtime recall cache; only consulted when the caller
        # supplies a thread_id (cache keys are (thread_id, query)).
        self._recall_cache = RecallCache()

    @property
    def llm(self) -> LLMClient:
        """The LLM client used by extraction and page regeneration."""
        return self._llm

    @property
    def llm_configured(self) -> bool:
        """True when the runtime has a real LLM instead of ``NoopLLMClient``."""
        return self._llm_configured

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def reconcile_manual_documents(
        self, params: dict[str, Any], *, is_current: Callable[[], bool] | None = None
    ) -> dict[str, Any]:
        """Shared in-process/RPC manual-document governance operation."""
        from octop_memory.operations.retention import reconcile_manual_documents

        documents = params.get("documents")
        if not isinstance(documents, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in documents.items()
        ):
            raise ValueError("documents must map filenames to text")
        return reconcile_manual_documents(
            self._memory, documents, llm=self._llm if self._llm_configured else None, is_current=is_current
        )

    def manual_document_review_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read audit status without changing memory or calling a model."""
        from octop_memory.operations.retention import manual_document_review_status

        documents = params.get("documents")
        if documents is not None and (
            not isinstance(documents, dict) or any(not isinstance(v, str) for v in documents.values())
        ):
            raise ValueError("documents must map filenames to text")
        return manual_document_review_status(self._memory, documents)

    def review_new_memory(self) -> dict[str, Any] | None:
        """Check writes against current owner files without refreshing chat snapshots."""
        provider = self._manual_documents_provider
        if provider is None:
            return None
        try:
            documents = provider()
            if not any(body.strip() for body in documents.values()):
                return None
            return self.reconcile_manual_documents({"documents": documents}, is_current=lambda: provider() == documents)
        except REPORTABLE_ERRORS:
            logger.warning("Manual-document review after memory write is unavailable", exc_info=True)
            return {"status": "unavailable"}

    def stats(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return status data for `openclaw octopmemory status`."""
        _ = params
        return {
            "namespace": self._memory.namespace,
            "counts": self._memory.backend.count_stats(),
            "config": {
                "profile": self._config.profile,
                "mode": self._config.mode,
                "recall": self._recall_cfg(),
                "capture": self._capture_cfg(),
                "privacy": self._privacy_cfg(),
                "extraction": self._extraction_cfg(),
                # NEVER echo api_key here — stats output lands in logs.
                "llm": {
                    "configured": self._llm_configured,
                    "endpoint": self._config.llm.get("endpoint") or self._config.llm.get("base_url"),
                    "model": self._config.llm.get("model"),
                    "model_heavy": self._config.llm.get("model_heavy"),
                },
            },
            "host_files": self._host_files.stats() if self._host_files is not None else None,
        }

    def reindex(self, params: dict[str, Any]) -> dict[str, Any]:
        """Force a host-files scan for `openclaw octopmemory reindex`."""
        _ = params
        if self._host_files is None:
            raise ValueError("reindex: host_files watcher is not enabled")
        if self._host_files.root is None:
            raise ValueError("reindex: host_files root is unknown")
        report = self._host_files.scan_once(self._host_files.root)
        return {
            "scanned": report.scanned,
            "indexed": report.indexed,
            "removed": report.removed,
            "skipped_binary": report.skipped_binary,
            "host_files": self._host_files.stats(),
        }

    def memory_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run multi-source recall and return ``memory_search``-shaped hits.

        OpenClaw schema (memory-core/index.ts MemorySearchSchema), plus
        our additive ``thread_id`` extension::

            { query: string!, maxResults?: int>=1, minScore?: number,
              corpus?: "memory" | "wiki" | "all" | "sessions",
              thread_id?: string }

        ``thread_id`` enables the M4 thread features: co-reference
        resolution against the active-entity stack ("那个项目怎么样")
        and the per-thread recall cache. The TS shell passes the
        session key it received at tool-registration time.

        We project our :class:`RecallResult` snippets onto::

            { hits: [
                { path, score, snippet, layer, role_hint, occurred_at, source_id },
                ...
              ],
              total: int,
              empty_reason: str | null
            }
        """
        query = params.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("memory_search: 'query' must be a non-empty string")
        recall_cfg = self._recall_cfg()
        max_results = _coerce_positive_int(
            params.get("maxResults"),
            default=int(recall_cfg["default_max_results"]),
            name="maxResults",
        )
        # ``minScore`` is honoured in M5+; the M4 reranker scores aren't
        # directly comparable to embedding similarity scores, so we
        # accept the param and silently ignore it for now (rather than
        # error — agents will pass it through).
        _ = params.get("minScore")
        corpus = params.get("corpus") or recall_cfg["default_corpus"]
        if corpus not in {"memory", "wiki", "all", "sessions"}:
            raise ValueError(f"memory_search: unknown corpus {corpus!r}")
        thread_id = params.get("thread_id")
        if thread_id is not None and not isinstance(thread_id, str):
            raise ValueError("memory_search: 'thread_id' must be a string or null")
        thread_id = thread_id or None

        hits: list[dict[str, Any]] = []

        host_files_policy = recall_cfg["host_files_policy"]
        raw_policy = recall_cfg["raw_policy"]

        # Layer 1: SQLite-backed atom / raw recall. Skipped when
        # the agent explicitly asks for sessions/host files, or when the
        # profile forces host_files_policy="only".
        if corpus in {"all", "memory"} and host_files_policy != "only":
            result = recall_for_prompt(
                self._memory,
                query,
                thread_id=thread_id,
                limit=max_results * 3,
                cache=self._recall_cache,
                raw_policy=raw_policy,
            )
            for snip in result.snippets:
                hits.append(
                    {
                        "path": _project_snippet_path(snip),
                        "score": None,  # rerank scores not exported yet (D38 internal)
                        "snippet": snip.text,
                        "layer": snip.layer,
                        "role_hint": snip.role_hint,
                        "occurred_at": snip.timestamp_iso,
                        "source_id": snip.source_id,
                    }
                )

        # Layer 2: D51-C host-files index. Surfaces ``MEMORY.md`` /
        # ``memory/YYYY-MM-DD.md`` / ``DREAMS.md`` content the host
        # silent-turn or user wrote outside our SQLite path. We append
        # AFTER the SQLite layer so highly-ranked atoms still come
        # first; budget enforcement happens on the TS side via the
        # tool's max_results.
        if self._host_files is not None and host_files_policy != "off" and corpus in {"all", "sessions", "memory"}:
            for hit in self._host_files.search(query, limit=max_results * 3):
                hits.append(
                    {
                        "path": hit.path,
                        "score": None,
                        "snippet": hit.snippet,
                        "layer": "host_file",
                        "role_hint": "host_file",
                        "occurred_at": None,
                        "source_id": hit.path,
                    }
                )

        hits = _apply_raw_policy(hits, raw_policy)
        hits = _sort_hits_by_layer(hits, recall_cfg["layer_order"])

        # Truncate to ``max_results`` after the union — the caller asked
        # for at most N hits in total, not N per layer.
        if len(hits) > max_results:
            hits = hits[:max_results]

        return {
            "hits": hits,
            "total": len(hits),
            "empty_reason": None if hits else "no_matches",
        }

    def memory_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve a virtual path → SQLite row → markdown excerpt.

        OpenClaw schema (memory-core/index.ts MemoryGetSchema)::

            { path: string!, from?: int>=1, lines?: int>=1,
              corpus?: "memory" | "wiki" | "all" }

        Output::

            { path, excerpt, total_lines, from_line, to_line, truncated,
              continuation?: { from: int }, kind, metadata: {...} }
        """
        path = params.get("path")
        if not isinstance(path, str):
            raise ValueError("memory_get: 'path' must be a string")
        from_line = _coerce_positive_int_or_none(params.get("from"), name="from")
        lines = _coerce_positive_int_or_none(params.get("lines"), name="lines")

        ref = parse_path(path)  # raises PathError on bad shape
        body, kind_metadata = self._render_for_path(ref)

        excerpt = slice_lines(body, from_line=from_line, lines=lines)
        meta = excerpt_metadata(full_text=body, from_line=from_line, lines=lines)

        return {
            "path": path,
            "kind": ref.kind,
            "excerpt": excerpt,
            "metadata": kind_metadata,
            **meta,
        }

    def capture(self, params: dict[str, Any]) -> dict[str, Any]:
        """D52-C: TS ``agent_end`` hook → write raw events into SQLite.

        Params shape (mirrored by TS shell)::

            {
              session_id: str | null,
              thread_id: str | null,
              user: str | null,
              host: "openclaw" | "hermes" | ...,
              events: [
                { event_type: str, content: str, payload?: dict,
                  timestamp_iso?: str },
                ...
              ]
            }

        Anti-feedback rule: events whose ``content`` contains the recall
        marker (``## Memory Recall`` — what our :func:`recall.recall_for_prompt`
        injects) are silently dropped; they're our own injection coming
        back as part of the assistant transcript.
        """
        session_id = _opt_str(params, "session_id")
        thread_id = _opt_str(params, "thread_id")
        user = _opt_str(params, "user")
        host = params.get("host") or "openclaw"
        if not isinstance(host, str):
            raise ValueError("capture: 'host' must be a string")
        raw_events = params.get("events")
        if not isinstance(raw_events, list):
            raise ValueError("capture: 'events' must be an array")

        capture_cfg = self._capture_cfg()
        privacy_cfg = self._privacy_cfg()
        accepted = 0
        skipped_marker = 0
        skipped_short = 0
        skipped_role = 0
        skipped_tool_result = 0
        skipped_runtime_error = 0

        events_to_write: list[RawEvent] = []
        for raw in raw_events:
            if not isinstance(raw, dict):
                continue
            content = raw.get("content")
            if not isinstance(content, str):
                continue
            event_type = raw.get("event_type", "user_message")
            if not isinstance(event_type, str):
                event_type = "user_message"
            raw_payload = raw.get("payload")
            payload: dict[str, Any] = dict(raw_payload) if isinstance(raw_payload, dict) else {}
            role = _event_role(event_type, payload)

            if role not in capture_cfg["include_roles"]:
                skipped_role += 1
                continue
            if role == "tool" and event_type == "tool_result" and not capture_cfg["include_tool_results"]:
                skipped_tool_result += 1
                continue
            # Strip reasoning blocks first so subsequent length / echo
            # checks see the user-visible body, not the model's scratchpad.
            content = _strip_think_tags(content)
            # D52-C anti-feedback: drop our own injection echoes. Match
            # the full render markers (recall._render / prompt-section
            # header), not the bare "[memory]" substring — users do
            # legitimately type that.
            if capture_cfg["skip_memory_echo"] and (
                "## Memory Recall" in content or "[memory] Earlier in this workspace" in content
            ):
                skipped_marker += 1
                continue
            if _effective_content_chars(content.strip()) < int(capture_cfg["min_message_chars"]):
                skipped_short += 1
                continue

            timestamp = _parse_iso(raw.get("timestamp_iso")) or datetime.now(UTC)
            event = RawEvent(
                id=raw.get("id") or _gen_event_id(),
                host=host,
                session_id=session_id,
                thread_id=thread_id,
                user=user,
                timestamp=timestamp,
                event_type=event_type,  # type: ignore[arg-type]
                content=content,
                payload=payload,
            )
            if is_runtime_error(event):
                skipped_runtime_error += 1
                continue
            event.content = _prepare_content(content, privacy_cfg)
            event.payload = _prepare_payload(payload, role=role, capture_cfg=capture_cfg, privacy_cfg=privacy_cfg)
            if privacy_cfg.get("store_raw_content") is False:
                event.payload["content_redacted"] = True
            events_to_write.append(event)
            accepted += 1

        # Single batch write = single fsync regardless of event count.
        if events_to_write:
            self._memory.add_raw_batch(events_to_write)

        return {
            "accepted": accepted,
            "skipped_recall_marker": skipped_marker,
            "skipped_too_short": skipped_short,
            "skipped_role": skipped_role,
            "skipped_tool_result": skipped_tool_result,
            "skipped_runtime_error": skipped_runtime_error,
        }

    def extract(self, params: dict[str, Any]) -> dict[str, Any]:
        """D26 session light extraction: L0 raw → L1 → L2 → L3 in one call.

        Params::

            {
              session_id: str!,            # which session's raw events
              incremental?: bool,          # default true — skip events
                                           # already extracted by this
                                           # runtime process
              promote?: bool,              # default extraction.promote
              regen_pages?: bool,          # default extraction.regen_pages
              max_candidates?: int
            }

        Pipeline (all synchronous; the TS shell fires this after
        agent_end capture, off the user's reply path):

        1. ``CandidateExtractor.extract`` over the session's (new) raw
           events → persist candidates via ``Memory.add_candidates``.
        2. ``PromotionWorker.promote`` over those candidates (5-check,
           demotion-only) — promoted atoms mark their entity page dirty.
        3. ``regenerate_dirty`` over dirty entity pages (heavy tier).

        Extraction failures (no LLM configured, parse retries exhausted)
        come back as ``failure_reason`` — never a JSON-RPC error — and
        the events are NOT marked extracted, so the next call retries.

        Every completed pass — empty, failed, or fruitful — appends one
        ``extract_run`` journal row so callers can see *when* extraction
        ran, not only when it mutated memory. A bad-params ``ValueError``
        is raised before that record (a rejected call is not a run).
        """
        try:
            response = self._extract_impl(params)
        except ValueError:
            raise
        except REPORTABLE_ERRORS as exc:
            logger.warning("memory extract failed; degrading", exc_info=True)
            session_id = params.get("session_id") if isinstance(params, dict) else None
            response = {
                "session_id": session_id,
                "events_considered": 0,
                "events_extracted": 0,
                "candidates": 0,
                "warnings": [],
                "cap_warning": None,
                "failure_reason": f"{type(exc).__name__}: {exc}",
                "llm_calls": 0,
                "promotion": None,
                "pages": None,
            }
        self._record_extract_run(response)
        return response

    def _record_extract_run(self, response: dict[str, Any]) -> None:
        """Remember the latest extract pass in ``{ns}_meta`` (ADR-028).

        ``extract_run`` is no longer appended to the journal: the table
        is a decision audit, and "last organized at" only needs one
        overwrite. Best-effort — a meta write failure is logged and
        swallowed so it can never fail the extraction it is recording.
        """
        promotion = response.get("promotion") or {}
        stats: dict[str, Any] = {
            "session_id": response.get("session_id"),
            "events_considered": response.get("events_considered", 0),
            "events_extracted": response.get("events_extracted", 0),
            "candidates": response.get("candidates", 0),
            "promoted": promotion.get("promoted", 0),
            "merged": promotion.get("merged", 0),
            "conflicts": promotion.get("conflicts", 0),
            "needs_review": promotion.get("needs_review", 0),
            "dropped": promotion.get("dropped", 0),
            "llm_calls": response.get("llm_calls", 0),
            "failure_reason": response.get("failure_reason"),
            "quiet": _is_quiet_extract_run(response),
            "note": "",
        }
        stats["note"] = _extract_run_note(stats)
        try:
            self._memory.record_extract_run(stats)
        except REPORTABLE_ERRORS:  # pragma: no cover - observability, never load-bearing
            logger.warning("failed to record extract_run meta", exc_info=True)

    def _extract_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("extract: 'session_id' must be a non-empty string")
        extraction_cfg = self._extraction_cfg()
        incremental = params.get("incremental", True)
        promote = bool(params.get("promote", extraction_cfg["promote"]))
        regen_pages = bool(params.get("regen_pages", extraction_cfg["regen_pages"]))
        max_candidates = _coerce_positive_int(
            params.get("max_candidates"),
            default=int(extraction_cfg["max_candidates"]),
            name="max_candidates",
        )
        cfg_max_tokens = extraction_cfg.get("max_tokens")
        max_tokens = (
            _coerce_positive_int(params.get("max_tokens"), default=int(cfg_max_tokens), name="max_tokens")
            if cfg_max_tokens is not None
            else _coerce_positive_int_or_none(params.get("max_tokens"), name="max_tokens")
        )

        events = self._memory.list_raw(session_id=session_id, limit=10_000)
        seen = self._seen_ids_for(session_id)
        new_events = [e for e in events if e.id not in seen] if incremental else list(events)

        response: dict[str, Any] = {
            "session_id": session_id,
            "events_considered": len(events),
            "events_extracted": len(new_events),
            "candidates": 0,
            "warnings": [],
            "cap_warning": None,
            "failure_reason": None,
            "llm_calls": 0,
            "promotion": None,
            "pages": None,
        }
        if not new_events:
            return response

        extractor = CandidateExtractor(llm=self._llm, max_candidates=max_candidates, max_tokens=max_tokens)
        result = extractor.extract(new_events, session_id=session_id)
        response["warnings"] = result.warnings
        response["cap_warning"] = result.cap_warning
        response["llm_calls"] = result.llm_calls
        if result.failure_reason is not None:
            # Leave the events unmarked so a later call (next turn, or
            # after the LLM endpoint recovers) retries them.
            response["failure_reason"] = result.failure_reason
            return response

        seen.update(e.id for e in new_events)
        response["candidates"] = len(result.candidates)
        if result.candidates:
            self._memory.add_candidates(result.candidates)

        if promote and result.candidates:
            worker = PromotionWorker(
                self._memory,
                llm_hook=ModelEscalationHook(self._llm) if self._llm_configured else None,
            )
            promo = worker.promote(result.candidates)
            response["promotion"] = {
                "promoted": promo.promoted,
                "merged": promo.merged,
                "conflicts": promo.conflicts,
                "needs_review": promo.needs_review,
                "dropped": promo.dropped,
                "llm_calls": promo.llm_calls,
            }
            response["llm_calls"] += promo.llm_calls
            if promo.promoted or promo.merged:
                response["manual_documents"] = self.review_new_memory()

        # Page regen needs the heavy tier — pointless against a Noop
        # client (every page would just record a regen failure).
        if regen_pages and self._llm_configured:
            batch = regenerate_dirty(
                self._memory,
                llm=self._llm,
                limit=int(extraction_cfg["page_regen_limit"]),
            )
            response["pages"] = {
                "regenerated": batch.success_count,
                "failed": batch.failure_count,
                "llm_calls": batch.llm_calls,
            }
            response["llm_calls"] += batch.llm_calls

        # M5 — Episode (diary) extraction. Runs in parallel with the
        # candidate path: it sees the SAME raw events but uses a
        # dedicated prompt that ONLY cares about user-experienced
        # events and emotion. Failures here are non-fatal: episodes
        # are an enrichment layer, not load-bearing for atom recall.
        if self._llm_configured:
            try:
                ep_extractor = EpisodeExtractor(llm=self._llm, max_tokens=max_tokens)
                ep_result = ep_extractor.extract(new_events, session_id=session_id)
                if ep_result.episodes:
                    self._memory.add_episodes(ep_result.episodes)
                response["episodes"] = {
                    "extracted": len(ep_result.episodes),
                    "warnings": ep_result.warnings,
                    "failure_reason": ep_result.failure_reason,
                    "llm_calls": ep_result.llm_calls,
                }
                response["llm_calls"] += ep_result.llm_calls
            except REPORTABLE_ERRORS as exc:  # pragma: no cover — defensive
                logger.warning("episode extractor crashed", exc_info=True)
                response["episodes"] = {
                    "extracted": 0,
                    "warnings": [],
                    "failure_reason": f"episode extractor crashed: {exc}",
                    "llm_calls": 0,
                }
        else:
            response["episodes"] = None

        return response

    def promote(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run the 5-check promotion worker over pending candidates.

        Params::

            { limit?: int, regen_pages?: bool }

        Exposed for the admin CLI (`openclaw octopmemory promote`) and
        for re-driving candidates that were extracted with
        ``promote=false`` or left pending by an earlier failure.
        """
        limit = _coerce_positive_int(params.get("limit"), default=50, name="limit")
        regen_pages = bool(params.get("regen_pages", False))
        worker = PromotionWorker(
            self._memory,
            llm_hook=ModelEscalationHook(self._llm) if self._llm_configured else None,
        )
        promo = worker.promote_pending(limit=limit)
        response: dict[str, Any] = {
            "promoted": promo.promoted,
            "merged": promo.merged,
            "conflicts": promo.conflicts,
            "needs_review": promo.needs_review,
            "dropped": promo.dropped,
            "llm_calls": promo.llm_calls,
            "pages": None,
        }
        if promo.promoted or promo.merged:
            response["manual_documents"] = self.review_new_memory()
        if regen_pages and self._llm_configured:
            extraction_cfg = self._extraction_cfg()
            batch = regenerate_dirty(
                self._memory,
                llm=self._llm,
                limit=int(extraction_cfg["page_regen_limit"]),
            )
            response["pages"] = {
                "regenerated": batch.success_count,
                "failed": batch.failure_count,
                "llm_calls": batch.llm_calls,
            }
        return response

    def _seen_ids_for(self, session_id: str) -> set[str]:
        """Fetch (or create) the extracted-id set for a session, LRU-evicting."""
        if session_id in self._extracted_ids:
            self._extracted_ids.move_to_end(session_id)
            return self._extracted_ids[session_id]
        seen: set[str] = set()
        self._extracted_ids[session_id] = seen
        while len(self._extracted_ids) > _MAX_TRACKED_SESSIONS:
            self._extracted_ids.popitem(last=False)
        return seen

    def _recall_cfg(self) -> dict[str, Any]:
        return {**DEFAULT_RECALL_CFG, **self._config.recall}

    def _extraction_cfg(self) -> dict[str, Any]:
        return {**DEFAULT_EXTRACTION_CFG, **self._config.extraction}

    def _capture_cfg(self) -> dict[str, Any]:
        return {**DEFAULT_CAPTURE_CFG, **self._config.capture}

    def _privacy_cfg(self) -> dict[str, Any]:
        return {**DEFAULT_PRIVACY_CFG, **self._config.privacy}

    # ------------------------------------------------------------------
    # Internal: render dispatch
    # ------------------------------------------------------------------

    def _render_for_path(self, ref: PathRef) -> tuple[str, dict[str, Any]]:
        """Pull the row from SQLite and render it as markdown.

        Returns ``(body, metadata)`` where ``metadata`` is a small dict
        of provenance fields the agent might want to surface verbatim
        (kept separate from the front-matter so adapters can render it
        differently).
        """
        if ref.kind == "atom":
            assert ref.id is not None
            atom = self._memory.get_atom(ref.id)
            if atom is None:
                raise _NotFoundError(f"atom {ref.id!r} not found")
            return render_atom_md(atom), {
                "id": atom.id,
                "entity_id": atom.entity_id,
                "importance": atom.importance,
                "confidence": atom.confidence,
            }
        if ref.kind == "page":
            assert ref.id is not None
            page = self._memory.get_entity_page(ref.id)
            if page is None:
                raise _NotFoundError(f"page {ref.id!r} not found")
            return render_page_md(page), {
                "entity_id": page.entity_id,
                "version": page.summary_version,
                "dirty": page.dirty,
            }
        if ref.kind == "raw":
            assert ref.id is not None
            event = self._memory.get_raw(ref.id)
            if event is None:
                raise _NotFoundError(f"raw event {ref.id!r} not found")
            return render_raw_md(event), {
                "id": event.id,
                "event_type": event.event_type,
                "session_id": event.session_id,
            }
        # host_root / host_daily / host_dreams — D51-C real-file paths.
        # Served by the optional :class:`HostFilesIndex`. Without an
        # index we surface a clear configuration error.
        if self._host_files is None:
            raise _HostFileUnavailableError(
                f"host-file path {ref.raw_path!r} is not served — "
                "instantiate MemoryRuntime(memory, host_files=HostFilesIndex(...)) "
                "or pass --host-files-root to the runtime server"
            )
        host_file = self._host_files.get(ref.raw_path)
        if host_file is None:
            # Index hasn't seen this file yet (poll cadence is 30s by
            # default). Surface as PATH_NOT_FOUND so the agent retries.
            raise _NotFoundError(
                f"host-file {ref.raw_path!r} not in the index yet "
                "(may be < 30s old; retry shortly or call a manual scan)"
            )
        return host_file.content, {
            "path": host_file.path,
            "size": host_file.size,
            "indexed_at": host_file.indexed_at,
        }


# ---------------------------------------------------------------------------
# Internal exceptions — adapters translate these to transport-specific errors.
# ---------------------------------------------------------------------------


class _NotFoundError(Exception):
    """Virtual path resolved but row missing in storage."""


class _HostFileUnavailableError(Exception):
    """Real-file path requested but the host-file index is unavailable."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_llm_client(llm_cfg: dict[str, Any]) -> LLMClient:
    """Build the runtime's LLM client from the ``--config-json`` ``llm`` block.

    No / incomplete config → :class:`NoopLLMClient` (extract degrades to
    ``failure_reason``; capture / search are unaffected). A present-but-
    broken config is also downgraded to Noop with a log line rather than
    failing runtime startup — memory recall must keep working even when
    the LLM endpoint is misconfigured.
    """
    if not llm_cfg.get("endpoint") and not llm_cfg.get("base_url"):
        return NoopLLMClient()
    try:
        return OpenAICompatClient.from_config(llm_cfg)
    except LLMClientError as exc:
        logger.warning("llm config rejected (%s); extraction disabled", exc)
        return NoopLLMClient()


def _error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }


def _coerce_positive_int(value: Any, *, default: int, name: str) -> int:
    if value is None:
        return default
    try:
        ivalue = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: must be a positive integer, got {value!r}") from exc
    if ivalue < 1:
        raise ValueError(f"{name}: must be >= 1, got {ivalue}")
    return ivalue


def _coerce_positive_int_or_none(value: Any, *, name: str) -> int | None:
    if value is None:
        return None
    return _coerce_positive_int(value, default=1, name=name)


_QUIET_ACTIVITY_KEYS = ("promoted", "merged", "conflicts", "needs_review", "dropped")
"""Promotion counters that mark an extract_run as non-quiet."""


def _is_quiet_extract_run(response: dict[str, Any]) -> bool:
    """True when a completed pass produced nothing new.

    "Quiet" = no failure, no new candidates, no promotion activity, no
    episodes. Stored on the latest-extract meta row so a dashboard can
    tell "ran but found nothing" from "never ran" (missing meta).
    """
    if response.get("failure_reason"):
        return False
    if response.get("candidates", 0):
        return False
    promotion = response.get("promotion") or {}
    if any(promotion.get(key, 0) for key in _QUIET_ACTIVITY_KEYS):
        return False
    episodes = response.get("episodes") or {}
    return not episodes.get("extracted", 0)


def _extract_run_note(stats: dict[str, Any]) -> str:
    """Concise English one-liner for CLI / logs (dashboards read ``after``)."""
    failure = stats.get("failure_reason")
    if failure:
        base = f"extraction failed: {failure}"
    elif not stats.get("events_extracted"):
        base = f"no new events (scanned {stats.get('events_considered', 0)})"
    else:
        base = (
            f"scanned {stats.get('events_considered', 0)} events, "
            f"{stats.get('events_extracted', 0)} new; "
            f"{stats.get('candidates', 0)} candidates, "
            f"{stats.get('promoted', 0)} promoted"
        )
    skipped = stats.get("skipped_noop_runs_since_last")
    if skipped:
        base += f"; heartbeat after {skipped} quiet run(s) skipped"
    return base


def _opt_str(params: dict[str, Any], key: str) -> str | None:
    val = params.get(key)
    if val is None:
        return None
    if isinstance(val, str):
        return val or None
    raise ValueError(f"capture: {key!r} must be a string or null")


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _gen_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _event_role(event_type: str, payload: dict[str, Any]) -> str:
    role = payload.get("role")
    if isinstance(role, str) and role in {"user", "assistant", "tool"}:
        return role
    if event_type.startswith("assistant"):
        return "assistant"
    if event_type.startswith("tool"):
        return "tool"
    return "user"


# CJK Unified Ideographs (same narrow range as pipeline/recall/budget.py).
_CJK_CHAR_WEIGHT = 4
"""One Han character carries roughly one English word's worth of
information (~4-5 ASCII characters incl. the trailing space), so the
``min_message_chars`` threshold counts it as 4. Without this, the
default threshold of 50 silently drops most Chinese messages — 50
Chinese characters is a full paragraph, not a short message."""


def _effective_content_chars(text: str) -> int:
    """Length proxy for the min_message_chars filter, CJK-weighted."""
    total = 0
    for ch in text:
        total += _CJK_CHAR_WEIGHT if _CJK_UNICODE_START <= ord(ch) <= _CJK_UNICODE_END else 1
    return total


# Strip <think>...</think> reasoning blocks emitted by some chat models
# (DeepSeek-R1 / Qwen-thinking / etc.). They are internal scratchpad,
# not user-visible content, and would otherwise pollute raw_events and
# the recall corpus. Multiline + non-greedy; tolerant of whitespace
# around the tag.
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
# Streaming may truncate either the opening or the closing tag, so the
# paired regex above misses two real-world shapes observed in raw_events:
#   1. only the closing tag survives: "</think>\n\n<actual reply>"
#      → the scratchpad before it must be stripped.
#   2. only the opening tag survives: "<think>scratchpad without close"
#      → strip from the tag through end-of-string.
# Order matters: pair-matched blocks are removed first, then the
# leading-orphan-close, then the trailing-unclosed-open.
_THINK_LEADING_CLOSE_RE = re.compile(r"\A\s*[^<]*?</think>\s*", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED_OPEN_RE = re.compile(r"<think\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)


def _strip_think_tags(content: str) -> str:
    """Remove ``<think>...</think>`` reasoning blocks from message content.

    Handles three streaming-truncation shapes observed in real raw_events:

    * Paired ``<think>...</think>`` blocks (the common case).
    * Leading orphan ``</think>`` (opening tag dropped by streaming start).
    * Trailing unclosed ``<think>`` (closing tag dropped by streaming end).
    """
    lowered = content.lower()
    if "<think" not in lowered and "</think>" not in lowered:
        return content
    cleaned = _THINK_BLOCK_RE.sub("", content)
    cleaned = _THINK_LEADING_CLOSE_RE.sub("", cleaned)
    cleaned = _THINK_UNCLOSED_OPEN_RE.sub("", cleaned)
    return cleaned.strip()


def _prepare_content(content: str, privacy_cfg: dict[str, Any]) -> str:
    if privacy_cfg.get("store_raw_content") is False:
        return "[raw content disabled by privacy.store_raw_content=false]"
    cleaned = _strip_think_tags(content)
    return _redact_text(cleaned, privacy_cfg)


def _prepare_payload(
    payload: dict[str, Any],
    *,
    role: str,
    capture_cfg: dict[str, Any],
    privacy_cfg: dict[str, Any],
) -> dict[str, Any]:
    next_payload = dict(payload)
    if not capture_cfg.get("include_tool_calls"):
        next_payload.pop("toolCalls", None)
        next_payload.pop("tool_calls", None)
    if role == "tool" and not privacy_cfg.get("store_tool_payloads"):
        return {"role": role}
    if not privacy_cfg.get("store_tool_payloads"):
        for key in list(next_payload):
            if _looks_secret_key(key):
                next_payload.pop(key, None)
    return _redact_payload_strings(next_payload, privacy_cfg)


def _redact_payload_strings(payload: dict[str, Any], privacy_cfg: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        redacted[key] = _redact_text(value, privacy_cfg) if isinstance(value, str) else value
    return redacted


def _looks_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("api_key", "apikey", "token", "secret", "password", "authorization"))


def _redact_text(value: str, privacy_cfg: dict[str, Any]) -> str:
    if not privacy_cfg.get("redact_secrets") and not privacy_cfg.get("redact_patterns"):
        return value
    next_value = value
    if privacy_cfg.get("redact_secrets"):
        for pattern in SECRET_PATTERNS:
            next_value = pattern.sub("[REDACTED]", next_value)
    for raw_pattern in privacy_cfg.get("redact_patterns") or []:
        if not isinstance(raw_pattern, str):
            continue
        try:
            next_value = re.sub(raw_pattern, "[REDACTED]", next_value)
        except re.error:
            logger.warning("ignoring invalid redact pattern: %r", raw_pattern)
    return next_value


def _apply_raw_policy(hits: list[dict[str, Any]], raw_policy: str) -> list[dict[str, Any]]:
    if raw_policy == "always":
        return hits
    non_raw_hits = [h for h in hits if _hit_layer(h) != "raw"]
    if raw_policy == "never":
        return non_raw_hits
    if raw_policy == "fallback" and non_raw_hits:
        return non_raw_hits
    return hits


def _sort_hits_by_layer(hits: list[dict[str, Any]], layer_order: list[str]) -> list[dict[str, Any]]:
    order = {layer: i for i, layer in enumerate(layer_order)}
    return [hit for _, hit in sorted(enumerate(hits), key=lambda pair: (order.get(_hit_layer(pair[1]), 999), pair[0]))]


def _hit_layer(hit: dict[str, Any]) -> str:
    layer = hit.get("layer")
    path = hit.get("path")
    if layer == "host_file":
        return "host_file"
    if isinstance(path, str) and path.startswith("raw/"):
        return "raw"
    if isinstance(path, str) and path.startswith("page/"):
        return "page"
    return "atom" if layer == "atom" else str(layer or "raw")


def _project_snippet_path(snip: Any) -> str:
    """Project a ``RecallSnippet`` onto a virtual path string.

    M4's :class:`RecallSnippet` only carries ``layer`` + ``source_id`` +
    ``timestamp_iso``. We use those to build the same path strings as
    :mod:`path_projection` produces from full rows. For atom snippets the
    path is ``atom/<source_id>.md``; for raw snippets we synthesize the
    date from ``timestamp_iso`` (matching :func:`raw_to_path`).
    """
    layer = getattr(snip, "layer", "raw")
    source_id = getattr(snip, "source_id", "")
    timestamp_iso = getattr(snip, "timestamp_iso", "")
    if layer == "atom":
        return f"atom/{source_id}.md"
    # The current runtime recall path emits atom/raw snippets.
    date = (timestamp_iso[:_ISO_DATE_LEN]) if len(timestamp_iso) >= _ISO_DATE_LEN else "unknown"
    return f"raw/{date}/{source_id}.md"


__all__ = [
    "MemoryRuntime",
    "MemoryRuntimeConfig",
    "_HostFileUnavailableError",
    "_NotFoundError",
    "_strip_think_tags",
]
