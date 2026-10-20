"""Memory backend protocol and registry."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol, Self, runtime_checkable

from octop_memory.types import (
    ActiveEntity,
    Alias,
    AtomCard,
    Candidate,
    CandidateStatus,
    DigestPeriod,
    DigestRecord,
    Entity,
    EntityPage,
    EntityType,
    Episode,
    ImportanceLevel,
    JournalAction,
    JournalEntry,
    MemoryNode,
    RawEvent,
    RawEventType,
)


class _Unset:
    """Sentinel type for "argument not provided" in update APIs.

    Used so that ``None`` can be passed explicitly to mean "set this
    field to NULL" (e.g. clearing ``topic``), distinct from "leave this
    field unchanged".
    """

    _instance: _Unset | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance  # type: ignore[return-value]

    def __repr__(self) -> str:
        return "_UNSET"


_UNSET = _Unset()


@runtime_checkable
class MemoryBackend(Protocol):
    """Abstract interface for memory storage backends.

    Implementations: SqliteMemoryBackend, PostgresMemoryBackend, QdrantMemoryBackend.
    """

    def transaction(self) -> AbstractContextManager[None]:
        """Context manager that wraps multiple writes in a single atomic transaction.

        Usage::

            with memory.backend.transaction():
                backend.save_raw(raw)
                backend.save_candidate(candidate)
                backend.save_atom(atom)
                backend.save_node(leaf)

        All writes inside the block are committed together on exit.
        On exception the entire block is rolled back, leaving no partial rows.
        Implementations must be re-entrant safe (nested calls are no-ops).
        """
        ...

    def save_node(self, node: MemoryNode) -> None:
        """Insert a new node. Re-inserting same id raises an error."""
        ...

    def get_node(self, node_id: str) -> MemoryNode | None:
        """Fetch a node by id, or ``None`` if not found."""
        ...

    def get_node_by_atom_id(self, atom_id: str) -> MemoryNode | None:
        """Fetch the leaf node that references ``atom_id``, or ``None`` if not found.

        Used by ``Memory._link_atom_to_tree`` to avoid a full-tree scan
        when checking for an existing leaf reference.
        """
        ...

    def get_children(self, parent_id: str | None) -> list[MemoryNode]:
        """Return child nodes of ``parent_id`` (``None`` means roots)."""
        ...

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        topic: str | _Unset | None = _UNSET,
        metadata: dict[str, Any] | _Unset | None = _UNSET,
    ) -> bool:
        """Update mutable fields. ``parent_id`` / ``level`` are not mutable here."""
        ...

    def delete_node(self, node_id: str, *, cascade: bool = False) -> bool:
        """Delete node. Without ``cascade`` and with children → raises ValueError."""
        ...

    def search_memories(self, query: str, limit: int = 5) -> list[MemoryNode]:
        """Full-text search over memory-tree nodes."""
        ...

    def get_tree(self) -> list[MemoryNode]:
        """Return every node in the memory tree."""
        ...

    # L0 raw events (M1)
    def save_raw(self, event: RawEvent) -> None:
        """Append a raw event. Raw events are immutable / append-only."""
        ...

    def save_raw_batch(self, events: list[RawEvent]) -> None:
        """Append many raw events in a single transaction (1 fsync)."""
        ...

    def get_raw(self, event_id: str) -> RawEvent | None:
        """Return one raw event, or ``None`` if it does not exist."""
        ...

    def list_raw(
        self,
        *,
        host: str | None = None,
        session_id: str | None = None,
        thread_id: str | None = None,
        user: str | None = None,
        event_type: RawEventType | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[RawEvent]:
        """List raw events matching the given filters."""
        ...

    def search_raw(self, query: str, *, limit: int = 10) -> list[RawEvent]:
        """Full-text search over raw events."""
        ...

    def delete_raw_before(self, before: datetime) -> int:
        """GC: delete events older than ``before``. Returns row count."""
        ...

    def get_raw_events_by_ids(self, event_ids: list[str]) -> list[RawEvent]:
        """Fetch multiple raw events by their IDs."""
        ...

    # ------------------------------------------------------------------
    # M2 — Candidates / Atoms / Entities / Aliases / Journal
    # ------------------------------------------------------------------

    # Candidates --------------------------------------------------------

    def find_duplicate_candidate(self, assertion: str, raw_event_ids: list[str], subject_name: str) -> bool:
        """Whether this assertion was already promoted for the same events.

        Whether a ``promoted`` candidate already has this assertion + subject
        and the exact same ``raw_event_ids`` set.

        Guards against re-extracting an old raw event after a restart. Only
        ``promoted`` rows count, so identical ``pending`` content is not
        silently skipped.
        """
        ...

    def save_candidate(self, candidate: Candidate) -> None:
        """Insert a new candidate. Re-inserting same id raises an error."""
        ...

    def get_candidate(self, candidate_id: str) -> Candidate | None:
        """Return one candidate, or ``None`` if it does not exist."""
        ...

    def list_candidates(
        self,
        *,
        status: CandidateStatus | None = None,
        session_id: str | None = None,
        target_entity_id: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Candidate]:
        """List candidates matching the given filters."""
        ...

    def update_candidate_status(
        self,
        candidate_id: str,
        *,
        status: CandidateStatus,
        decided_by: str | None = None,
        decided_at: datetime | None = None,
        target_entity_id: str | _Unset | None = _UNSET,
        promotion_reason: str | None = None,
    ) -> bool:
        """Update candidate decision-state fields. Other fields stay frozen."""
        ...

    def search_candidates(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Candidate]:
        """FTS over title + assertion + verbatim_quote."""
        ...

    # Atoms -------------------------------------------------------------

    def save_atom(self, atom: AtomCard) -> None:
        """Insert a new atom. Re-inserting same id raises an error."""
        ...

    def get_atom(self, atom_id: str) -> AtomCard | None:
        """Return one atom, or ``None`` if it does not exist."""
        ...

    def list_atoms(
        self,
        *,
        entity_id: str | None = None,
        importance: ImportanceLevel | None = None,
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[AtomCard]:
        """List atoms matching the given filters."""
        ...

    def supersede_atom(
        self,
        old_atom_id: str,
        *,
        new_atom_id: str,
        deprecated_at: datetime,
    ) -> bool:
        """Supersede an active atom, returning false when it is missing or already inactive."""
        ...

    def deprecate_atom(self, atom_id: str, *, deprecated_at: datetime) -> bool:
        """Mark an atom inactive without creating a replacement."""
        ...

    def migrate_atoms_to_entity(
        self,
        source_entity_id: str,
        target_entity_id: str,
    ) -> int:
        """Move non-deprecated atoms from one entity to another.

        Bulk-update the entity_id of every non-deprecated atom under
        ``source_entity_id`` to ``target_entity_id``, in a single database
        transaction.

        Any atom that ends up with a duplicate assertion signature under
        the target entity after the migration is marked deprecated
        (``superseded_by`` points at the keeper under the target entity).

        Returns the number of atoms actually migrated (entity_id updated).
        """
        ...

    def find_atom_by_signature(self, signature: str) -> AtomCard | None:
        """Look up an atom by its assertion signature hash."""
        ...

    def search_atoms(
        self,
        query: str,
        *,
        include_deprecated: bool = False,
        limit: int = 10,
    ) -> list[AtomCard]:
        """FTS over assertion + verbatim_quote + search_terms."""
        ...

    def search_atoms_by_time_range(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        entity_id: str | None = None,
        include_deprecated: bool = False,
        limit: int = 50,
    ) -> list[AtomCard]:
        """Time-bounded atom lookup ordered by ``occurred_at DESC``.

        Used by the recall router for time-anchored queries
        ("yesterday", "上次", "上周")  — the parser converts the
        time hint into a ``[start, end]`` window and asks for the
        most recent atoms inside it. ``entity_id`` further narrows
        when an entity hint coexists ("那个项目上周").
        """
        ...

    # Thread Active-Entity Stack (M4) -----------------------------------

    def upsert_active_entity(self, record: ActiveEntity) -> None:
        """Insert or refresh ``last_seen_at`` for ``(thread_id, entity_id)``.

        D41b-B: persisted to SQLite / Postgres so co-reference still
        resolves after a host restart. Idempotent — re-seeing the
        same entity bumps the timestamp instead of duplicating rows.
        """
        ...

    def list_active_entities(
        self,
        thread_id: str,
        *,
        limit: int = 5,
    ) -> list[ActiveEntity]:
        """Return entities active in ``thread_id``, newest first.

        The recall router pulls the head of this list to resolve
        co-references like "那个项目"; the rest is for debugging via
        ``octop-memory thread show <thread_id>``.
        """
        ...

    def evict_active_entities(
        self,
        thread_id: str,
        *,
        keep: int = 5,
    ) -> int:
        """Trim a thread's stack to the most recent ``keep`` entries.

        Called from :class:`Memory.upsert_active_entity` after every
        insert so the table doesn't grow unbounded for long-lived
        threads. Returns the number of rows removed.
        """
        ...

    # Entities ----------------------------------------------------------

    def save_entity(self, entity: Entity) -> None:
        """Insert a new entity. Re-inserting same id raises an error."""
        ...

    def get_entity(self, entity_id: str) -> Entity | None:
        """Return one entity, or ``None`` if it does not exist."""
        ...

    def find_entity_by_name(
        self,
        canonical_name: str,
        *,
        entity_type: EntityType | None = None,
    ) -> Entity | None:
        """Return the entity with this canonical name, if any."""
        ...

    def list_entities(
        self,
        *,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        """List entities, optionally filtered by type."""
        ...

    def bump_entity_atom_count(
        self,
        entity_id: str,
        *,
        delta: int,
        last_promoted_at: datetime | None = None,
    ) -> bool:
        """Increment / decrement ``atom_count`` (used by promotion worker)."""
        ...

    def update_entity_canonical_name(self, entity_id: str, canonical_name: str) -> bool:
        """Update the canonical_name of an existing entity.

        Used by the User singleton upgrade path when the user reveals their
        real name after the entity was initially created with a generic
        placeholder (e.g. 'User'). Returns True if a row was updated.
        """
        ...

    # Entity Pages (M3) -------------------------------------------------

    def upsert_entity_page(self, page: EntityPage) -> None:
        """Insert or replace the EntityPage row keyed by ``entity_id``.

        Page rows are NOT append-only: every successful regen / user edit
        rewrites the row in place. The journal captures the full history.
        """
        ...

    def get_entity_page(self, entity_id: str) -> EntityPage | None:
        """Fetch the page attached to ``entity_id``, or ``None`` if absent."""
        ...

    def count_stats(self) -> dict[str, int]:
        """Cheap row counts for status surfaces.

        Returns ``{"raw_events", "atoms", "entities", "dirty_pages"}``
        computed via ``COUNT(*)`` — never by materializing rows.
        """
        ...

    def list_dirty_entity_pages(self, *, limit: int = 50) -> list[EntityPage]:
        """List pages with ``dirty=True`` ordered by oldest ``updated_at`` first.

        Used by the async cron worker (``memory page regen --dirty``);
        ``last_regen_at IS NULL`` rows always sort first so brand-new
        entities are picked up before stale ones.
        """
        ...

    def mark_entity_page_dirty(self, entity_id: str, *, when: datetime) -> None:
        """Set ``dirty=True`` on the page for ``entity_id``.

        If no page row exists yet (first promotion against this entity),
        a stub row is inserted with empty ``summary_markdown`` /
        ``headline`` so the cron worker has something to materialize.
        Idempotent — safe to call repeatedly.
        """
        ...

    def apply_entity_page_regen(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        headline: str,
        topics: list[str],
        when: datetime,
    ) -> bool:
        """Store a successful entity-page regeneration.

        Apply a successful regen: replace summary fields, clear dirty,
        bump ``summary_version``, reset ``regen_attempt_count``.

        Returns ``True`` if the row existed and was updated.
        """
        ...

    def record_entity_page_regen_failure(
        self,
        entity_id: str,
        *,
        when: datetime,
    ) -> bool:
        """Record a failed entity-page regeneration.

        Record an LLM regen failure: keep ``dirty=True``, increment
        ``regen_attempt_count``, leave ``summary_markdown`` /
        ``headline`` untouched (D35-A — keep old version on failure).

        Returns ``True`` if the row existed.
        """
        ...

    def apply_entity_page_user_edit(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        when: datetime,
    ) -> bool:
        """Apply a user edit to ``summary_markdown``.

        Bumps ``summary_version`` and updates ``last_user_edit_at``;
        does NOT mark the row dirty (the user's edit is the latest
        truth — only future promotions re-dirty the page).

        Returns ``True`` if the row existed and was updated.
        """
        ...

    # Aliases -----------------------------------------------------------

    def save_alias(self, alias: Alias) -> None:
        """Insert a new alias mapping. Duplicate (alias, entity_id) is a no-op."""
        ...

    def find_entity_by_alias(self, alias: str) -> Entity | None:
        """Look up the entity that the given alias resolves to."""
        ...

    def list_aliases(
        self,
        *,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[Alias]:
        """List alias rows, optionally for one entity."""
        ...

    # Journal -----------------------------------------------------------

    def append_journal(self, entry: JournalEntry) -> None:
        """Append a journal entry. Decision rows stay; pipeline rows expire (ADR-028)."""
        ...

    def list_journal(
        self,
        *,
        action: JournalAction | None = None,
        target_entity_id: str | None = None,
        target_atom_id: str | None = None,
        target_candidate_id: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[JournalEntry]:
        """List journal rows matching the given filters."""
        ...

    def delete_journal(
        self,
        *,
        actions: Sequence[str],
        before: datetime,
        limit: int,
        dry_run: bool = False,
    ) -> int:
        """Delete up to ``limit`` rows with ``action IN actions`` and ``timestamp < before``.

        ``dry_run`` counts without deleting. Returns the row count.
        """
        ...

    def get_meta(self, key: str) -> str | None:
        """Return a namespace-scoped meta value, or ``None`` if missing."""
        ...

    def set_meta(self, key: str, value: str) -> None:
        """Upsert a namespace-scoped meta value."""
        ...

    # Episodes (M5 — L2.5 diary layer) ----------------------------------

    def save_episode(self, episode: Episode) -> None:
        """Insert a new Episode. Strict insert; duplicate id raises."""
        ...

    def get_episode(self, episode_id: str) -> Episode | None:
        """Return one episode, or ``None`` if it does not exist."""
        ...

    def list_episodes(
        self,
        *,
        session_id: str | None = None,
        emotion: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Episode]:
        """List episodes matching the given filters."""
        ...

    def search_episodes(self, query: str, *, limit: int = 10) -> list[Episode]:
        """FTS over summary + verbatim_quote + people + topics."""
        ...

    def list_episodes_in_range(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[Episode]:
        """List episodes whose ``occurred_at`` falls in ``[start, end)``.

        Used by the digest aggregator. Ordered ASC.
        """
        ...

    # Digests (M5 — weekly/monthly aggregates over episodes) -----------

    def upsert_digest(self, digest: DigestRecord) -> None:
        """Insert or replace a digest row keyed by ``(period_kind, period_key)``."""
        ...

    def get_digest(self, period_kind: DigestPeriod, period_key: str) -> DigestRecord | None:
        """Return one digest row, or ``None`` if it does not exist."""
        ...

    def list_digests(
        self,
        *,
        period_kind: DigestPeriod | None = None,
        limit: int = 50,
    ) -> list[DigestRecord]:
        """List digest rows, optionally for one period kind."""
        ...


__all__ = ["_UNSET", "MemoryBackend", "_Unset"]
