"""Cross-namespace recall — project → team → agent private, merged and deduped.

``octop_memory`` isolates stores by ``namespace`` (``agent_{id}`` /
``team_{id}`` / ``project_{id}``), and
``octop_memory.pipeline.recall.multi_source.gather_candidates`` only fans out
*between sources* (``atom``, ``raw``, …) inside **one** namespace. This module
is the layer above it: one ``gather_candidates`` call per namespace, then a
merge that

1. runs the layers in the fixed order **project → team → agent private**,
2. drops a memory already contributed by an earlier layer, and
3. tags every surviving hit with the ``source_layer`` it came from.

Inheritance is *the order itself* — nothing is copied between namespaces.
Plainly concatenating the three layers would surface one memory up to three
times (PLAN ``R17``), so :meth:`MultiNsRecall.recall` dedupes on **both** the
memory id and the normalized text. The content key is the one that matters
across layers: the same fact written into two namespaces is two rows with two
ids, so the id key alone would not catch it.

Without project context the project layer is never guessed and never opened —
recall covers the team layer (when the host belongs to a team) plus the host
agent's private layer.

Only ``projects.inject_version`` is written, through the existing
``ProjectRepo.bump_inject_version`` (see :class:`ProjectInjectVersion`); no new
table or column is involved.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from octop_harness.memory.store import MemoryIdentity

from octop.config import OctopConfig
from octop.infra.agents.memory.backend import (
    agent_memory_namespace,
    open_memory_kwargs,
    resolve_project_namespace,
    team_memory_namespace,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from octop_memory.pipeline.recall.parser import ParsedQuery
    from octop_memory.pipeline.recall.rerank import RerankCandidate
    from octop_memory.pipeline.recall.timeout import Stopwatch
    from octop_memory.types import ConfidenceLevel, ImportanceLevel

logger = logging.getLogger(__name__)

MemoryLayer = Literal["project", "team", "agent"]
"""Which of the three memory layers a hit came from."""

LAYER_ORDER: tuple[MemoryLayer, ...] = ("project", "team", "agent")
"""Fixed recall order (``PLAN.md``「记忆分层」). Earlier layers win a duplicate."""

_WHITESPACE_RE = re.compile(r"\s+")

_IMPORTANCE_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

_MAX_CACHED_MEMORIES = 32

RankKey = tuple[int, float, int]
"""``(importance, recency, layer)`` — lower sorts first."""


def normalize_memory_text(text: str) -> str:
    """Fold whitespace and case, so the same fact matches across namespaces.

    Content is the only key that can identify a memory copied into two
    namespaces — each copy gets its own id — so this is what makes the
    cross-layer dedup work.
    """
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


@dataclass(frozen=True, slots=True)
class RecallHit:
    """One merged recall result, tagged with the layer it came from."""

    source_id: str
    """The memory id inside its own namespace."""

    text: str

    source_layer: MemoryLayer
    """Which layer produced this hit (``project`` > ``team`` > ``agent``)."""

    layer: str
    """The inner ``octop_memory`` source: ``atom`` / ``raw`` / ``page_headline`` / …"""

    occurred_at: datetime
    importance: ImportanceLevel
    confidence: ConfidenceLevel
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryScope:
    """Where one host agent's three memory layers live.

    All three layers share the host agent's backend location; only the
    namespace differs, which is exactly what ``open_memory_kwargs(...,
    namespace=...)`` exists for. ``team_agent_id`` is the id of the team host
    whose layer this agent inherits — ``None`` when the agent has no team, in
    which case the team layer is skipped rather than guessed.
    """

    agent_id: str
    cfg: dict[str, Any]
    octop_config: OctopConfig
    workspace_dir: Path
    team_agent_id: str | None = None


def _memory_identity(
    namespace: str,
    backend: str,
    backend_config: dict[str, Any] | None,
) -> MemoryIdentity:
    """Build the cache key: one ``Memory`` per namespace + backend location.

    Mirrors ``octop_harness/memory/store.py · memory_identity`` — a namespace
    over a different SQLite file (or DSN) is a different store.
    """
    config = backend_config or {}
    if backend == "postgres":
        location = str(config.get("dsn") or "").strip()
    else:
        raw_path = str(config.get("db_path") or "")
        try:
            location = str(Path(raw_path).expanduser().resolve()) if raw_path else ""
        except OSError:  # pragma: no cover - only on an unusable path
            location = raw_path
    return MemoryIdentity(namespace=namespace, backend=backend, location=location)


def _rank_key(hit: RecallHit) -> RankKey:
    """Sort by importance weight, then freshness, then layer priority."""
    return (
        _IMPORTANCE_RANK.get(hit.importance, 1),
        -hit.occurred_at.timestamp(),
        LAYER_ORDER.index(hit.source_layer),
    )


class MultiNsRecall:
    """Recall across the project / team / agent layers, merged and deduped.

    Long-lived per host agent: ``Memory`` handles are cached by
    :class:`~octop_harness.memory.store.MemoryIdentity`, so repeated turns do
    not reopen the backend. Call :meth:`close` when the owner shuts down.

    ``per_namespace_budget_ms`` / ``total_budget_ms`` default to
    ``octop-memory``'s own atom / total budgets, clamped per namespace to the
    remaining global slice — the same per-source discipline
    ``multi_source.gather_candidates`` applies inside one namespace, with each
    namespace treated as one source.
    """

    def __init__(
        self,
        scope: MemoryScope,
        *,
        sources: Sequence[str] = ("atom", "raw"),
        per_source_limit: int = 10,
        per_namespace_budget_ms: int | None = None,
        total_budget_ms: int | None = None,
        max_cached: int = _MAX_CACHED_MEMORIES,
    ) -> None:
        self._scope = scope
        self._sources = tuple(sources)
        self._per_source_limit = per_source_limit
        self._per_namespace_budget_ms = per_namespace_budget_ms
        self._total_budget_ms = total_budget_ms
        self._max_cached = max_cached
        self._lock = threading.Lock()
        self._memories: OrderedDict[MemoryIdentity, Any] = OrderedDict()

    # ------------------------------------------------------------------
    # Layers
    # ------------------------------------------------------------------

    def layers(self, *, project_id: str | None = None) -> tuple[MemoryLayer, ...]:
        """Return the layers to consult, in recall order.

        A layer is included only when it exists: no ``project_id`` means no
        project layer (never guessed), and no ``team_agent_id`` means no team
        layer.
        """
        present: dict[MemoryLayer, bool] = {
            "project": project_id is not None,
            "team": bool(self._scope.team_agent_id),
            "agent": True,
        }
        return tuple(layer for layer in LAYER_ORDER if present[layer])

    def _namespace(
        self,
        layer: MemoryLayer,
        *,
        project_id: str | None,
        project_namespace: str | None,
    ) -> str:
        if layer == "agent":
            return agent_memory_namespace(self._scope.agent_id)
        if layer == "team":
            team_agent_id = self._scope.team_agent_id
            if not team_agent_id:  # pragma: no cover - guarded by layers()
                raise ValueError("team layer requires MemoryScope.team_agent_id")
            return team_memory_namespace(team_agent_id)
        if project_id is None:  # pragma: no cover - guarded by layers()
            raise ValueError("project layer requires project_id")
        # ``projects.memory_namespace`` is the single authority when present.
        return resolve_project_namespace(memory_namespace=project_namespace, project_id=project_id)

    # ------------------------------------------------------------------
    # Memory handles
    # ------------------------------------------------------------------

    def memory_for(
        self,
        layer: MemoryLayer,
        *,
        project_id: str | None = None,
        project_namespace: str | None = None,
    ) -> Any:
        """Return the cached ``Memory`` handle for one layer.

        The writer path (``learnings.py``) uses ``layer="project"`` to reach the
        very store this module recalls from, so what is written is what is read.
        """
        return self._memory(
            self._namespace(layer, project_id=project_id, project_namespace=project_namespace)
        )

    def _memory(self, namespace: str) -> Any:
        from octop_memory.core import Memory

        resolved_ns, backend, backend_config = open_memory_kwargs(
            agent_id=self._scope.agent_id,
            cfg=self._scope.cfg,
            octop_config=self._scope.octop_config,
            workspace_dir=self._scope.workspace_dir,
            namespace=namespace,
        )
        key = _memory_identity(resolved_ns, backend, backend_config)
        with self._lock:
            cached = self._memories.get(key)
            if cached is not None:
                self._memories.move_to_end(key)
                return cached
            memory = Memory(namespace=resolved_ns, backend=backend, backend_config=backend_config)
            self._memories[key] = memory
            while len(self._memories) > self._max_cached:
                _, evicted = self._memories.popitem(last=False)
                logger.debug("multi-ns memory cache evicted %s", evicted)
            return memory

    def close(self) -> None:
        """Drop the cached handles and close their backends."""
        with self._lock:
            memories = list(self._memories.values())
            self._memories.clear()
        for memory in memories:
            backend = getattr(memory, "backend", None)
            close = getattr(backend, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    logger.debug("closing multi-ns memory backend failed", exc_info=True)

    # ------------------------------------------------------------------
    # Recall
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        *,
        project_id: str | None = None,
        project_namespace: str | None = None,
    ) -> list[RecallHit]:
        """Recall across layers, highest weight / freshest first, each tagged.

        Raises no layer-specific error: a namespace that times out or fails at
        the driver contributes zero hits and the remaining layers still return,
        matching ``gather_candidates``' advisory-source contract.
        """
        from octop_memory.pipeline.recall.parser import parse_query
        from octop_memory.pipeline.recall.timeout import (
            DEFAULT_TOTAL_BUDGET_MS,
            Stopwatch,
        )

        parsed = parse_query(query)
        if not parsed.text:
            return []

        # One stopwatch for the whole cross-namespace pass, so the per-layer
        # slices compete for the same global budget instead of each getting a
        # fresh one.
        stopwatch = Stopwatch(
            total_budget_ms=(
                self._total_budget_ms
                if self._total_budget_ms is not None
                else DEFAULT_TOTAL_BUDGET_MS
            )
        )
        seen_ids: set[str] = set()
        seen_texts: set[str] = set()
        hits: list[RecallHit] = []
        for layer in self.layers(project_id=project_id):
            if stopwatch.expired:
                break
            namespace = self._namespace(
                layer, project_id=project_id, project_namespace=project_namespace
            )
            for candidate in self._gather(namespace, layer, parsed, stopwatch):
                text_key = normalize_memory_text(candidate.text)
                if candidate.source_id in seen_ids:
                    continue
                # A blank snippet carries no identity, so it must not dedupe
                # against another blank one.
                if text_key and text_key in seen_texts:
                    continue
                seen_ids.add(candidate.source_id)
                if text_key:
                    seen_texts.add(text_key)
                hits.append(
                    RecallHit(
                        source_id=candidate.source_id,
                        text=candidate.text,
                        source_layer=layer,
                        layer=candidate.layer,
                        occurred_at=candidate.occurred_at,
                        importance=candidate.importance,
                        confidence=candidate.confidence,
                        entity_id=candidate.entity_id,
                    )
                )
        return sorted(hits, key=_rank_key)

    def _gather(
        self,
        namespace: str,
        layer: MemoryLayer,
        parsed: ParsedQuery,
        stopwatch: Stopwatch,
    ) -> list[RerankCandidate]:
        """Run ``gather_candidates`` for one namespace, under its own deadline."""
        from octop_memory.pipeline.recall.multi_source import gather_candidates
        from octop_memory.pipeline.recall.timeout import (
            DEFAULT_ATOM_BUDGET_MS,
            TimeoutExceededError,
            with_deadline,
        )
        from octop_memory.storage.driver_errors import DRIVER_ERRORS

        slice_ms = (
            self._per_namespace_budget_ms
            if self._per_namespace_budget_ms is not None
            else DEFAULT_ATOM_BUDGET_MS
        )
        memory = self._memory(namespace)
        try:
            candidates: list[RerankCandidate] = with_deadline(
                lambda: gather_candidates(
                    memory,
                    parsed,
                    sources=self._sources,
                    per_source_limit=self._per_source_limit,
                ),
                stage=f"ns:{layer}",
                budget_ms=min(slice_ms, max(1, stopwatch.remaining_ms)),
            )
        except TimeoutExceededError:
            logger.warning("multi-ns recall timed out layer=%s", layer)
            return []
        except DRIVER_ERRORS:
            logger.warning("multi-ns recall failed layer=%s", layer, exc_info=True)
            return []
        stopwatch.split(f"ns:{layer}")
        return candidates


class InjectVersionSource(Protocol):
    """The one existing repo method this module needs (``ProjectRepo``)."""

    def bump_inject_version(self, project_id: str) -> int: ...


class ProjectInjectVersion:
    """Wires ``projects.inject_version`` to project-layer writes and injection.

    Write side: :meth:`note_write` delegates to the existing
    ``ProjectRepo.bump_inject_version`` — the repo and the schema are untouched.
    Inject side: the project's current ``inject_version`` is compared against
    the revision last injected, so an unchanged project is not re-injected and
    a changed one is.

    The watermark is per-process state (``inject_version`` already lives in the
    ``projects`` row; this design adds no table and no column).
    """

    def __init__(self, projects: InjectVersionSource) -> None:
        self._projects = projects
        self._lock = threading.Lock()
        self._injected: dict[str, int] = {}

    def note_write(self, project_id: str) -> int:
        """Record a project-layer write; returns the new ``inject_version``."""
        return int(self._projects.bump_inject_version(project_id))

    def last_injected(self, project_id: str) -> int | None:
        """Return the revision last injected, or ``None`` if never injected."""
        with self._lock:
            return self._injected.get(project_id)

    def should_inject(self, project_id: str, current_version: int) -> bool:
        """Whether the project's memory changed since the last injection."""
        with self._lock:
            last = self._injected.get(project_id)
        return last is None or current_version > last

    def mark_injected(self, project_id: str, current_version: int) -> None:
        """Remember the revision that was just injected."""
        with self._lock:
            self._injected[project_id] = current_version


__all__ = [
    "LAYER_ORDER",
    "InjectVersionSource",
    "MemoryLayer",
    "MemoryScope",
    "MultiNsRecall",
    "ProjectInjectVersion",
    "RankKey",
    "RecallHit",
    "normalize_memory_text",
    "team_memory_namespace",
]
