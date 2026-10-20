"""Periodic intra-entity semantic dedup (Entity Consolidation).

Promotion-time dedup (``pipeline/promotion/checks.py::check_duplicate``) only
catches **exact** signature matches (``normalize_alias`` whole-string
equality). That stops mechanical repeats (replay / re-ingest / case &
whitespace noise) but **not paraphrase duplicates** — e.g. the same
entity ending up with both ``user likes Python`` and ``user prefers Python``.

This task adds **standing-stock semantic dedup**, designed as a sibling
of :mod:`octop_memory.pipeline.lifecycle.gc`: a bounded, dry-run-able,
fully-journaled lifecycle pass that cron and CLI share through one
:func:`run_consolidation` entry point.

Pipeline per entity (``atom_count >= min_atoms`` only):

1. List live atoms (``include_deprecated=False``, capped at 200 like
   ``check_duplicate`` — wider entities are pathological, skip).
2. **Cheap prefilter** — pairwise Jaccard (reusing
   :func:`octop_memory.pipeline.recall.suppress.jaccard`). Pairs scoring
   ``>= jaccard_prefilter`` are "suspect". This keeps the O(n²) LLM
   confirmation down to only suspect pairs.
3. **Confirm**:
   - ``jaccard >= 0.85`` (``suppress.DEFAULT_JACCARD_THRESHOLD``) →
     near-duplicate, confirmed without an LLM call.
   - else if an ``llm_hook`` is supplied and the budget isn't spent →
     ``llm_hook.same_assertion(...)``; ``None``/``False`` means "not a
     duplicate" (conservative: when unsure, keep both).
4. **Cluster** confirmed pairs via union-find.
5. **Pick keeper** per cluster: importance > confidence > newer
   ``occurred_at`` > newer ``created_at``.
6. **Deprecate** the losers via :meth:`Memory.supersede_atom` pointing
   at the keeper, journaling each (``consolidate``).
7. Any deprecation on an entity → :meth:`Memory.mark_entity_page_dirty`
   so the summary regenerates from the clean set.

The back half of cleanup (deprecate → delayed GC reclaim → page regen)
is already end-to-end; this module only does **detect + mark
deprecated**. The existing ``gc._gc_deprecated_atoms`` reclaims the
rows after the 90-day window.

Each pass is bounded by ``max_entities`` and ``max_llm_calls`` so a
single tick can't lock the database or blow the LLM budget.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from octop_memory.pipeline.recall.suppress import DEFAULT_JACCARD_THRESHOLD, jaccard
from octop_memory.types import AtomCard, ConfidenceLevel, ImportanceLevel, JournalEntry

if TYPE_CHECKING:
    from octop_memory.core import Memory
    from octop_memory.pipeline.promotion.checks import LLMEscalationHook


_LOG = logging.getLogger(__name__)


DEFAULT_MIN_ATOMS = 2
"""Entities with fewer live atoms than this can't have intra-entity
duplicates, so we skip them outright."""

DEFAULT_JACCARD_PREFILTER = 0.6
"""Suspect-pair cutoff. Lower than the near-duplicate confirm threshold
(:data:`DEFAULT_JACCARD_THRESHOLD`) so paraphrases survive the prefilter
and get a chance at LLM confirmation, but high enough that obviously
unrelated atoms never reach the (expensive) confirm step."""

DEFAULT_MAX_ENTITIES = 200
"""Soft cap on entities processed per pass so a single tick can't lock
the database on a huge namespace. Caller can run multiple passes."""

DEFAULT_MAX_LLM_CALLS = 50
"""Budget cap on ``same_assertion`` calls per pass."""

DEFAULT_ATOM_SCAN_LIMIT = 200
"""Matches ``check_duplicate`` — entities wider than this are
pathological; we'd rather skip dedup than scan unbounded."""


# Rank maps for keeper selection (higher = preferred). Mirrors the
# ordering rerank.py uses but kept local: we only need the ordinal, not
# the calibrated factor weight.
_IMPORTANCE_RANK: dict[ImportanceLevel, int] = {"low": 0, "medium": 1, "high": 2}
_CONFIDENCE_RANK: dict[ConfidenceLevel, int] = {"low": 0, "medium": 1, "high": 2}


@dataclass
class ConsolidationStats:
    """Per-pass counters. ``dry_run`` reports what *would* happen."""

    entities_scanned: int = 0
    duplicate_clusters_found: int = 0
    atoms_deprecated: int = 0
    llm_calls: int = 0
    journal_rows_added: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    dry_run: bool = False


@dataclass
class DuplicateCluster:
    """One resolved cluster of duplicate atoms within a single entity.

    Self-contained so callers (journal + CLI dry-run printer) need no
    second DB read: it carries the keeper's assertion and each loser's
    ``(atom_id, assertion)``.
    """

    entity_id: str
    keeper_id: str
    keeper_assertion: str
    confirmed_by: str  # "rule" (high-Jaccard) | "auto" (LLM-confirmed)
    losers: list[tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_consolidation(
    memory: Memory,
    *,
    llm_hook: LLMEscalationHook | None = None,
    entity_type: str | None = None,
    min_atoms: int = DEFAULT_MIN_ATOMS,
    jaccard_prefilter: float = DEFAULT_JACCARD_PREFILTER,
    max_entities: int = DEFAULT_MAX_ENTITIES,
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
    dry_run: bool = False,
    when: datetime | None = None,
    on_cluster: Callable[[DuplicateCluster], None] | None = None,
) -> ConsolidationStats:
    """Run one intra-entity semantic-dedup pass over the namespace.

    With ``llm_hook=None`` only high-Jaccard near-duplicates are merged
    (no LLM calls). Supplying a hook additionally confirms paraphrase
    duplicates in the grey zone between ``jaccard_prefilter`` and
    :data:`DEFAULT_JACCARD_THRESHOLD`.

    Set ``dry_run=True`` to compute the clusters and counters without
    calling ``supersede_atom`` / ``mark_entity_page_dirty`` / writing
    journal rows — same semantics as ``gc.run_gc(dry_run=True)``.

    ``on_cluster`` (if given) is invoked once per resolved cluster
    *before* any mutation, so a dry-run caller can print exactly what
    would be merged.
    """
    stats = ConsolidationStats(started_at=datetime.now(UTC), dry_run=dry_run)
    now = when or datetime.now(UTC)

    entities = memory.list_entities(entity_type=entity_type, limit=max_entities)  # type: ignore[arg-type]
    for entity in entities:
        if entity.atom_count < min_atoms:
            continue
        stats.entities_scanned += 1
        clusters = _consolidate_entity(
            memory,
            entity_id=entity.id,
            llm_hook=llm_hook,
            jaccard_prefilter=jaccard_prefilter,
            max_llm_calls=max_llm_calls,
            stats=stats,
        )
        if not clusters:
            continue

        for cluster in clusters:
            stats.duplicate_clusters_found += 1
            if on_cluster is not None:
                on_cluster(cluster)
            for loser_id, loser_assertion in cluster.losers:
                if not dry_run:
                    memory.supersede_atom(loser_id, new_atom_id=cluster.keeper_id, deprecated_at=now)
                _journal(
                    memory,
                    keeper_id=cluster.keeper_id,
                    loser_id=loser_id,
                    entity_id=cluster.entity_id,
                    loser_assertion=loser_assertion,
                    actor=cluster.confirmed_by,
                    when=now,
                    stats=stats,
                    dry_run=dry_run,
                )
                stats.atoms_deprecated += 1

        if not dry_run:
            memory.mark_entity_page_dirty(entity.id, when=now)

    stats.finished_at = datetime.now(UTC)
    return stats


# ---------------------------------------------------------------------------
# Single-entity work
# ---------------------------------------------------------------------------


def _consolidate_entity(
    memory: Memory,
    *,
    entity_id: str,
    llm_hook: LLMEscalationHook | None,
    jaccard_prefilter: float,
    max_llm_calls: int,
    stats: ConsolidationStats,
) -> list[DuplicateCluster]:
    """Detect duplicate clusters within one entity.

    Detect duplicate clusters within one entity. No mutation here —
    the caller performs deprecation so dry-run stays trivial.
    """
    atoms = memory.list_atoms(
        entity_id=entity_id,
        include_deprecated=False,
        limit=DEFAULT_ATOM_SCAN_LIMIT,
    )
    if len(atoms) < DEFAULT_MIN_ATOMS:
        return []

    uf = _UnionFind(atom.id for atom in atoms)
    by_id = {atom.id: atom for atom in atoms}
    # Atoms touched by an LLM-confirmed edge: a cluster containing any of
    # them is attributed to "auto", otherwise to the pure-rule path.
    llm_confirmed: set[str] = set()

    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            a, b = atoms[i], atoms[j]
            score = jaccard(a.assertion, b.assertion)
            if score < jaccard_prefilter:
                continue
            if score >= DEFAULT_JACCARD_THRESHOLD:
                uf.union(a.id, b.id)
                continue
            # Grey zone — needs LLM confirmation (conservative when absent).
            if llm_hook is None or stats.llm_calls >= max_llm_calls:
                continue
            stats.llm_calls += 1
            same = llm_hook.same_assertion(
                candidate_assertion=a.assertion,
                existing_assertion=b.assertion,
            )
            if same is True:
                uf.union(a.id, b.id)
                llm_confirmed.update((a.id, b.id))

    clusters: list[DuplicateCluster] = []
    for member_ids in uf.groups():
        if len(member_ids) < DEFAULT_MIN_ATOMS:
            continue
        members = [by_id[mid] for mid in member_ids]
        keeper = max(members, key=_keeper_sort_key)
        confirmed_by = "auto" if any(mid in llm_confirmed for mid in member_ids) else "rule"
        clusters.append(
            DuplicateCluster(
                entity_id=entity_id,
                keeper_id=keeper.id,
                keeper_assertion=keeper.assertion,
                confirmed_by=confirmed_by,
                losers=[(m.id, m.assertion) for m in members if m.id != keeper.id],
            )
        )
    return clusters


def _keeper_sort_key(atom: AtomCard) -> tuple[int, int, datetime, datetime]:
    """Higher tuple wins: importance > confidence > newer occurred_at > newer created_at."""
    return (
        _IMPORTANCE_RANK.get(atom.importance, 0),
        _CONFIDENCE_RANK.get(atom.confidence, 0),
        atom.occurred_at,
        atom.created_at,
    )


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------


class _UnionFind:
    """Minimal union-find over atom ids for clustering confirmed pairs."""

    def __init__(self, ids: Iterable[str]) -> None:
        self._parent: dict[str, str] = {i: i for i in ids}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def groups(self) -> list[list[str]]:
        buckets: dict[str, list[str]] = {}
        for node in self._parent:
            buckets.setdefault(self.find(node), []).append(node)
        return list(buckets.values())


# ---------------------------------------------------------------------------
# Journaling
# ---------------------------------------------------------------------------


def _journal(
    memory: Memory,
    *,
    keeper_id: str,
    loser_id: str,
    entity_id: str,
    loser_assertion: str,
    actor: str,
    when: datetime,
    stats: ConsolidationStats,
    dry_run: bool,
) -> None:
    """Append a ``consolidate`` journal row for one deprecated atom.

    Dry-run counts the would-be write but persists nothing — keeps the
    journal clean from what-if passes (same as ``gc._journal``).
    """
    if dry_run:
        stats.journal_rows_added += 1
        return
    memory.append_journal(
        JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=when,
            action="consolidate",
            actor=actor,  # type: ignore[arg-type]
            target_entity_id=entity_id,
            target_atom_id=loser_id,
            before={"assertion": loser_assertion},
            after={"superseded_by": keeper_id},
            note=f"semantic duplicate; superseded by {keeper_id}",
        )
    )
    stats.journal_rows_added += 1


__all__ = [
    "DEFAULT_ATOM_SCAN_LIMIT",
    "DEFAULT_JACCARD_PREFILTER",
    "DEFAULT_MAX_ENTITIES",
    "DEFAULT_MAX_LLM_CALLS",
    "DEFAULT_MIN_ATOMS",
    "ConsolidationStats",
    "DuplicateCluster",
    "run_consolidation",
]
