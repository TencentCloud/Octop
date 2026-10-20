"""Memory — the unified interface for the memory system."""

from __future__ import annotations

import asyncio
import builtins
import json
import logging
import os
import threading
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from octop_memory.storage.backends import _UNSET, MemoryBackend, _Unset
from octop_memory.storage.driver_errors import DRIVER_ERRORS, VECTOR_ERRORS
from octop_memory.types import (
    ActiveEntity,
    Alias,
    AtomCard,
    Candidate,
    CandidateStatus,
    CandidateType,
    ConfidenceLevel,
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
    ThreadState,
    ThreadSummary,
)

if TYPE_CHECKING:
    from octop_memory.pipeline.promotion import PromotionResult
    from octop_memory.storage.vector import EmbeddingProvider, VectorIndex

logger = logging.getLogger("octop_memory")

MemoryLevel = Literal["root", "branch", "leaf"]
_VALID_LEVELS: frozenset[str] = frozenset({"root", "branch", "leaf"})
_ENTITY_TYPES: frozenset[str] = frozenset({"User", "Person", "Project", "Decision", "Task", "Fact"})
_ATOM_KINDS: frozenset[str] = frozenset({"Fact", "Decision", "Task", "Preference", "ConflictCandidate"})
_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})

# ---------------------------------------------------------------------------
# Dynamic base class: inherit from BaseCheckpointSaver when langgraph available
# ---------------------------------------------------------------------------

try:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    _LANGGRAPH_AVAILABLE = True
    _CheckpointerBase: type = BaseCheckpointSaver
except ImportError:  # pragma: no cover
    _LANGGRAPH_AVAILABLE = False
    _CheckpointerBase = object


class Memory(_CheckpointerBase):  # type: ignore[misc]
    """High-level memory interface.

    Wraps a ``MemoryBackend`` and provides the developer-facing API for
    storing/recalling memories.

    When ``langgraph`` is installed, Memory also acts as a
    ``BaseCheckpointSaver``, delegating checkpointer operations to
    an internal saver backed by the same database.

    Args:
        namespace: Isolation namespace (typically agent name).
        backend: Either a backend type string (``"sqlite"`` / ``"postgres"``)
            that will be resolved via factory, or a pre-built
            ``MemoryBackend`` instance for direct injection.
        backend_config: Backend-specific configuration dict. Only used when
            ``backend`` is a string. Ignored when ``backend`` is an instance.
    """

    def __init__(
        self,
        namespace: str,
        backend: str | MemoryBackend = "sqlite",
        backend_config: dict[str, Any] | None = None,
        *,
        vector_index: VectorIndex | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        if _LANGGRAPH_AVAILABLE:
            super().__init__()

        self._namespace = namespace
        if isinstance(backend, str):
            self._backend = _resolve_memory_backend(backend, namespace, backend_config or {})
        else:
            self._backend = backend

        # Vector-search enhancement layer (optional)
        self._vector_index = vector_index
        self._embedding_provider = embedding_provider

        self._checkpointer_pool: Any | None = None
        # Postgres savers are built on first use (see _ensure_checkpointer);
        # the lock keeps concurrent checkpoint calls from opening two pools.
        self._checkpointer_lock = threading.Lock()
        self._checkpointer = self._create_checkpointer()

    @property
    def backend(self) -> MemoryBackend:
        """The underlying storage backend."""
        return self._backend

    @property
    def namespace(self) -> str:
        """The isolation namespace."""
        return self._namespace

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def store(
        self,
        content: str,
        *,
        topic: str | None = None,
        level: MemoryLevel = "leaf",
        parent_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryNode:
        """Create an organizational node or a canonical memory fact.

        ``root`` and ``branch`` create directory nodes. ``leaf`` takes the
        manual-write path ``RawEvent → Candidate → AtomCard`` and creates a
        tree leaf that references the atom. The leaf's displayed ``content``
        is projected from ``AtomCard.assertion``; it is not stored twice.

        Validation:
        - ``level`` must be one of ``root`` / ``branch`` / ``leaf``.
        - ``root`` nodes MUST NOT have a ``parent_id``.
        - ``branch`` / ``leaf`` nodes with ``parent_id`` require the
          parent to exist.
        - A node cannot be its own parent (self-loop).
        - **leaf nodes cannot have children.** Trying to create
          ``branch`` / ``leaf`` under a ``leaf`` parent raises
          ``ValueError``. Promote the parent to ``branch`` first via a
          dedicated API (not via ``update``, which is intentionally
          immutable for ``level``).

        ``metadata`` defaults to ``{}`` and is organizational only.
        """
        if level not in _VALID_LEVELS:
            raise ValueError(f"Invalid level {level!r}; must be one of {sorted(_VALID_LEVELS)}")

        if level == "root":
            if parent_id is not None:
                raise ValueError("root nodes must not have a parent_id")
        elif parent_id is not None:
            parent = self._backend.get_node(parent_id)
            if parent is None:
                raise ValueError(f"parent_id {parent_id!r} does not exist")
            if parent.level == "leaf":
                raise ValueError(
                    f"cannot attach {level!r} under leaf parent {parent_id!r}; leaf nodes cannot have children"
                )

        if level == "leaf":
            return self._store_manual_atom(
                content,
                topic=topic,
                parent_id=parent_id,
                conversation_id=conversation_id,
                metadata=metadata,
            )

        now = datetime.now(UTC)
        node = MemoryNode(
            id=str(uuid.uuid4()),
            parent_id=parent_id,
            level=level,
            content=content,
            topic=topic,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata) if metadata else {},
        )
        # Self-parent is structurally impossible since id is freshly
        # generated, but we keep the check here as a property guard
        # against future API shifts (e.g. caller-supplied id).
        if node.parent_id == node.id:
            raise ValueError("a node cannot be its own parent")
        self._backend.save_node(node)
        return node

    def get(self, node_id: str) -> MemoryNode | None:
        """Fetch a memory node by id, or ``None`` if not found."""
        return self._backend.get_node(node_id)

    def update(
        self,
        node_id: str,
        *,
        content: str | None = None,
        topic: str | _Unset | None = _UNSET,
        metadata: dict[str, Any] | _Unset | None = _UNSET,
    ) -> bool:
        """Update organizational fields on an existing node.

        - ``parent_id`` and ``level`` are intentionally **not** mutable
          here. Re-parenting belongs in a future ``move()`` API where
          cycle detection is centralized.
        - ``metadata`` semantics is **replace** (whole-dict overwrite),
          not patch-merge.

        Returns ``True`` if the node existed and was updated.
        """
        node = self._backend.get_node(node_id)
        if node is None:
            return False
        if node.level == "leaf" and content is not None:
            raise ValueError("leaf content is owned by AtomCard; create a replacement atom instead")
        return self._backend.update_node(
            node_id,
            content=content,
            topic=topic,
            metadata=metadata,
        )

    def delete(self, node_id: str, *, cascade: bool = False) -> bool:
        """Delete a memory node.

        Without ``cascade`` and with children → raises ``ValueError``.
        With ``cascade=True`` deletes the entire subtree.
        """
        node = self._backend.get_node(node_id)
        if node is None:
            return False

        descendants = self._subtree_nodes(node_id) if cascade else [node]
        if not cascade and self._backend.get_children(node_id):
            return self._backend.delete_node(node_id, cascade=False)

        deleted = self._backend.delete_node(node_id, cascade=cascade)
        if not deleted:
            return False

        now = datetime.now(UTC)
        for descendant in descendants:
            if descendant.atom_id is None:
                continue
            atom = self._backend.get_atom(descendant.atom_id)
            if atom is None:
                continue
            self._backend.deprecate_atom(atom.id, deprecated_at=now)
            self._backend.bump_entity_atom_count(atom.entity_id, delta=-1)
            self._backend.mark_entity_page_dirty(atom.entity_id, when=now)
            self._backend.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="delete",
                    actor="user",
                    target_entity_id=atom.entity_id,
                    target_atom_id=atom.id,
                    target_candidate_id=atom.candidate_id,
                    before={"assertion": atom.assertion},
                    note="Deleted through Memory.delete(); atom deprecated and tree reference removed.",
                )
            )
        return True

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryNode]:
        """Recall canonical atoms projected as their tree leaves."""
        return self._backend.search_memories(query, limit=limit)

    # ------------------------------------------------------------------
    # L0 Raw events (M1)
    # ------------------------------------------------------------------

    def add_raw(
        self,
        content: str,
        *,
        event_type: RawEventType,
        host: str = "manual",
        session_id: str | None = None,
        thread_id: str | None = None,
        user: str | None = None,
        timestamp: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RawEvent:
        """Append a raw event to L0.

        ``host`` defaults to ``"manual"`` so calling ``add_raw(...)``
        from CLI / tests doesn't need to invent a host name. Real
        adapters supply the actual host (``"openclaw"`` / ``"hermes"``).

        ``timestamp`` defaults to ``now(UTC)`` if not provided. Adapters
        with their own clock should pass the host-supplied time.

        Raw events are immutable once written; corrections must append
        new events rather than mutate old ones.
        """
        event = RawEvent(
            id=str(uuid.uuid4()),
            host=host,
            session_id=session_id,
            thread_id=thread_id,
            user=user,
            timestamp=timestamp or datetime.now(UTC),
            event_type=event_type,
            content=content,
            payload=dict(payload) if payload else {},
        )
        self._backend.save_raw(event)
        return event

    def add_raw_batch(self, events: list[RawEvent]) -> None:
        """Append many raw events in a single transaction (1 fsync).

        Use this for high-throughput mirror writes where ``save_raw``
        per event would cause an fsync storm. Caller is responsible for
        constructing fully-populated ``RawEvent`` objects.
        """
        self._backend.save_raw_batch(events)

    def get_raw(self, event_id: str) -> RawEvent | None:
        """Fetch a raw event by id, or ``None`` if not found."""
        return self._backend.get_raw(event_id)

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
        """List raw events with optional filters, ordered by timestamp DESC."""
        return self._backend.list_raw(
            host=host,
            session_id=session_id,
            thread_id=thread_id,
            user=user,
            event_type=event_type,
            after=after,
            before=before,
            limit=limit,
        )

    def search_raw(self, query: str, *, limit: int = 10) -> list[RawEvent]:
        """FTS5 full-text search over raw event content."""
        return self._backend.search_raw(query, limit=limit)

    def get_raw_events_by_ids(self, event_ids: list[str]) -> list[RawEvent]:
        """Batch-fetch raw events by a list of ids, returning the matching RawEvent list."""
        return self._backend.get_raw_events_by_ids(event_ids)

    # ------------------------------------------------------------------
    # M2 — Candidates (L1)
    # ------------------------------------------------------------------

    def add_candidate(self, candidate: Candidate) -> None:
        """Persist a candidate. Strict insert; duplicate id raises."""
        self._backend.save_candidate(candidate)

    def add_candidates(self, candidates: list[Candidate]) -> None:
        """Persist many candidates (one transaction per row in current backends).

        Skips duplicate candidates whose ``assertion`` and ``raw_event_ids``
        are identical, preventing duplicate atoms from being generated when
        old raw events get rescanned after a process restart.
        """
        for c in candidates:
            if self._backend.find_duplicate_candidate(c.assertion, c.raw_event_ids, c.subject_name):
                continue
            self._backend.save_candidate(c)

    def get_candidate(self, candidate_id: str) -> Candidate | None:
        return self._backend.get_candidate(candidate_id)

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
        return self._backend.list_candidates(
            status=status,
            session_id=session_id,
            target_entity_id=target_entity_id,
            after=after,
            before=before,
            limit=limit,
        )

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
        return self._backend.update_candidate_status(
            candidate_id,
            status=status,
            decided_by=decided_by,
            decided_at=decided_at,
            target_entity_id=target_entity_id,
            promotion_reason=promotion_reason,
        )

    def search_candidates(self, query: str, *, limit: int = 10) -> list[Candidate]:
        """FTS over title + assertion + verbatim_quote."""
        return self._backend.search_candidates(query, limit=limit)

    # ------------------------------------------------------------------
    # M2 — Atoms (L2)
    # ------------------------------------------------------------------

    def add_atom(self, atom: AtomCard, *, parent_id: str | None = None) -> None:
        self._backend.save_atom(atom)
        self._link_atom_to_tree(atom, parent_id=parent_id)

    def get_atom(self, atom_id: str) -> AtomCard | None:
        return self._backend.get_atom(atom_id)

    def list_atoms(
        self,
        *,
        entity_id: str | None = None,
        importance: ImportanceLevel | None = None,
        include_deprecated: bool = False,
        limit: int = 100,
    ) -> list[AtomCard]:
        return self._backend.list_atoms(
            entity_id=entity_id,
            importance=importance,
            include_deprecated=include_deprecated,
            limit=limit,
        )

    def find_atom_by_signature(self, sig: str) -> AtomCard | None:
        """Find the first non-deprecated atom globally whose assertion signature matches ``sig``.

        Delegates to the backend's ``find_atom_by_signature`` implementation;
        used for exact cross-entity duplicate detection (check_duplicate step 2).
        """
        return self._backend.find_atom_by_signature(sig)

    def supersede_atom(
        self,
        old_atom_id: str,
        *,
        new_atom_id: str,
        deprecated_at: datetime | None = None,
    ) -> bool:
        when = deprecated_at or datetime.now(UTC)
        updated = self._backend.supersede_atom(old_atom_id, new_atom_id=new_atom_id, deprecated_at=when)
        if updated:
            for node in self._backend.get_tree():
                if node.atom_id == old_atom_id:
                    self._backend.delete_node(node.id)
        return updated

    def deprecate_atom(
        self,
        atom_id: str,
        *,
        actor: Literal["user", "auto", "rule"] = "user",
        note: str = "",
        when: datetime | None = None,
    ) -> bool:
        """Soft-delete an atom without a replacement.

        Used by the dashboard "deprecate" action where the user judges
        the atom incorrect but has nothing better to put in its place.
        Differs from :meth:`supersede_atom` (which requires a successor)
        and from :meth:`delete` (which removes the tree node and emits
        an ``action="delete"`` journal entry).

        Side effects performed atomically with the backend update:

        * ``deprecated_at`` is set on the atom row.
        * The owning entity's ``atom_count`` is decremented by 1.
        * The owning entity page is marked dirty so the next regen
          picks up the loss of evidence.
        * One ``action="deprecate"`` journal entry is appended with
          the given ``actor`` and ``note``.

        Returns ``False`` (no journal write, no side effects) when
        ``atom_id`` is unknown or the row is already deprecated.
        """
        atom = self._backend.get_atom(atom_id)
        if atom is None:
            return False
        if atom.deprecated_at is not None:
            return False

        timestamp = when or datetime.now(UTC)
        updated = self._backend.deprecate_atom(atom_id, deprecated_at=timestamp)
        if not updated:
            return False

        self._backend.bump_entity_atom_count(atom.entity_id, delta=-1)
        self._backend.mark_entity_page_dirty(atom.entity_id, when=timestamp)
        self._backend.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=timestamp,
                action="deprecate",
                actor=actor,
                target_entity_id=atom.entity_id,
                target_atom_id=atom.id,
                target_candidate_id=atom.candidate_id,
                before={"assertion": atom.assertion},
                note=note or "Atom deprecated without replacement.",
            )
        )
        return True

    def create_atom(
        self,
        assertion: str,
        *,
        entity_id: str | None = None,
        entity_name: str | None = None,
        entity_type: EntityType = "Fact",
        kind: CandidateType = "Fact",
        importance: ImportanceLevel = "medium",
        confidence: ConfidenceLevel = "high",
        verbatim_quote: str | None = None,
        actor: Literal["user", "auto", "rule"] = "user",
        note: str = "",
    ) -> tuple[AtomCard, Entity, bool]:
        """Manually create a canonical atom, optionally creating its entity.

        Dashboard / MCP "add a memory" path. Goes through the same
        ``RawEvent → Candidate → AtomCard → entity-branch leaf`` chain as
        promotion so recall, FTS, and the memory tree stay consistent.

        Pass ``entity_id`` to attach to an existing topic, or ``entity_name``
        (+ ``entity_type``) to resolve-or-create one. User-type entities
        remain a singleton.

        Returns ``(atom, entity, created_entity)``.
        """
        from octop_memory.domain.alias import normalize_alias

        text = assertion.strip()
        if not text:
            raise ValueError("assertion must be a non-empty string")
        if entity_type not in _ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(_ENTITY_TYPES)}")
        if kind not in _ATOM_KINDS:
            raise ValueError(f"kind must be one of {sorted(_ATOM_KINDS)}")
        if importance not in _LEVELS:
            raise ValueError(f"importance must be one of {sorted(_LEVELS)}")
        if confidence not in _LEVELS:
            raise ValueError(f"confidence must be one of {sorted(_LEVELS)}")

        now = datetime.now(UTC)
        quote = (verbatim_quote or text)[:200]
        atom: AtomCard
        entity: Entity
        created_entity = False
        with self._backend.transaction():
            entity, created_entity = self._resolve_manual_entity(
                entity_id=entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
            )
            if self._find_live_duplicate(entity.id, text) is not None:
                raise ValueError("duplicate assertion under this entity")
            raw = self.add_raw(
                text,
                event_type="manual",
                host="manual",
                payload={"source": "user_create", "note": note} if note else {"source": "user_create"},
            )
            candidate = Candidate(
                id=str(uuid.uuid4()),
                raw_event_ids=[raw.id],
                candidate_type=kind,
                status="promoted",
                title=text[:80],
                assertion=text,
                verbatim_quote=quote,
                quote_event_id=raw.id,
                subject_name=entity.canonical_name,
                subject_entity_type=entity.entity_type,
                target_entity_id=entity.id,
                confidence=confidence,
                importance=importance,
                recommended_action="promote",
                promotion_reason="Manual Memory.create_atom() write",
                extractor_version="manual/v1",
                created_at=now,
                decided_at=now,
                decided_by=actor,
            )
            self.add_candidate(candidate)
            atom = AtomCard(
                id=str(uuid.uuid4()),
                entity_id=entity.id,
                candidate_id=candidate.id,
                raw_event_ids=[raw.id],
                assertion=text,
                verbatim_quote=quote,
                quote_event_id=raw.id,
                search_terms=[entity.canonical_name],
                occurred_at=raw.timestamp,
                confidence=confidence,
                importance=importance,
                created_at=now,
            )
            branch = self.get_or_create_entity_branch(entity.id)
            self._backend.save_atom(atom)
            self._link_atom_to_tree(atom, parent_id=branch.id)
            self.bump_entity_atom_count(entity.id, delta=1, last_promoted_at=now)
            self.mark_entity_page_dirty(entity.id, when=now)
            if created_entity:
                normalized = normalize_alias(entity.canonical_name)
                if normalized and self.find_entity_by_alias(normalized) is None:
                    self.add_alias(
                        Alias(
                            alias=normalized,
                            entity_id=entity.id,
                            entity_type=entity.entity_type,
                            created_by=actor,
                            created_at=now,
                        )
                    )
            self.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="create",
                    actor=actor,
                    target_entity_id=entity.id,
                    target_atom_id=atom.id,
                    target_candidate_id=candidate.id,
                    after={"assertion": atom.assertion},
                    note=note or "Manual atom created through Memory.create_atom().",
                )
            )
        self._index_atom_vector(atom)
        refreshed = self.get_entity(entity.id) or entity
        logger.info(
            "memory.trigger create_atom ns=%s entity=%r atom=%s assertion=%r",
            self._namespace,
            refreshed.canonical_name,
            atom.id,
            text[:60],
        )
        return atom, refreshed, created_entity

    def replace_atom(
        self,
        atom_id: str,
        *,
        assertion: str,
        actor: Literal["user", "auto", "rule"] = "user",
        note: str = "",
    ) -> AtomCard | None:
        """Replace a live atom's assertion by creating a successor.

        ADR-010: atom text is append-only. The old row is superseded
        (``deprecated_at`` + ``superseded_by``), its tree leaf is removed,
        and a new leaf is linked under the same entity branch. ``atom_count``
        stays the same because this is a replacement, not an add.

        A correction is not a captured conversation or a new extraction, so
        it does not create a RawEvent or Candidate.  The successor retains the
        original lineage as historical context; the ``user_edit`` journal row
        is the authoritative record of who changed which assertion.

        Returns the new atom, the unchanged original when the assertion
        is identical, or ``None`` when ``atom_id`` is unknown / already
        deprecated.
        """
        from octop_memory.domain.alias import normalize_alias

        text = assertion.strip()
        if not text:
            raise ValueError("assertion must be a non-empty string")

        old = self._backend.get_atom(atom_id)
        if old is None or old.deprecated_at is not None:
            return None
        if normalize_alias(text) == normalize_alias(old.assertion):
            return old

        duplicate = self._find_live_duplicate(old.entity_id, text, exclude_id=old.id)
        if duplicate is not None:
            raise ValueError("duplicate assertion under this entity")

        now = datetime.now(UTC)
        new_atom: AtomCard
        with self._backend.transaction():
            new_atom = AtomCard(
                id=str(uuid.uuid4()),
                entity_id=old.entity_id,
                candidate_id=old.candidate_id,
                raw_event_ids=list(old.raw_event_ids),
                assertion=text,
                verbatim_quote=old.verbatim_quote,
                quote_event_id=old.quote_event_id,
                search_terms=list(old.search_terms),
                occurred_at=old.occurred_at,
                confidence=old.confidence,
                importance=old.importance,
                created_at=now,
            )
            self._backend.save_atom(new_atom)
            if not self.supersede_atom(old.id, new_atom_id=new_atom.id, deprecated_at=now):
                raise ValueError(f"atom {old.id!r} was replaced concurrently")
            branch = self.get_or_create_entity_branch(old.entity_id)
            self._link_atom_to_tree(new_atom, parent_id=branch.id)
            self.mark_entity_page_dirty(old.entity_id, when=now)
            self.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="user_edit",
                    actor=actor,
                    target_entity_id=old.entity_id,
                    target_atom_id=new_atom.id,
                    before={"assertion": old.assertion, "atom_id": old.id},
                    after={"assertion": new_atom.assertion, "atom_id": new_atom.id},
                    note=note or "Atom replaced through Memory.replace_atom().",
                )
            )
        self._index_atom_vector(new_atom)
        self._drop_atom_vector(old.id)
        logger.info(
            "memory.trigger replace_atom ns=%s old=%s new=%s",
            self._namespace,
            old.id,
            new_atom.id,
        )
        return new_atom

    def search_atoms(
        self,
        query: str,
        *,
        include_deprecated: bool = False,
        limit: int = 10,
    ) -> list[AtomCard]:
        return self._backend.search_atoms(query, include_deprecated=include_deprecated, limit=limit)

    def search_atoms_by_time_range(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        entity_id: str | None = None,
        include_deprecated: bool = False,
        limit: int = 50,
    ) -> list[AtomCard]:
        """Time-bounded atom lookup; used by the recall router for time hints."""
        return self._backend.search_atoms_by_time_range(
            start=start,
            end=end,
            entity_id=entity_id,
            include_deprecated=include_deprecated,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # M2 — Entities (L3 minimal — D28)
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        self._backend.save_entity(entity)

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._backend.get_entity(entity_id)

    def find_entity_by_name(
        self,
        canonical_name: str,
        *,
        entity_type: EntityType | None = None,
    ) -> Entity | None:
        return self._backend.find_entity_by_name(canonical_name, entity_type=entity_type)

    def list_entities(
        self,
        *,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> list[Entity]:
        return self._backend.list_entities(entity_type=entity_type, limit=limit)

    def bump_entity_atom_count(
        self,
        entity_id: str,
        *,
        delta: int,
        last_promoted_at: datetime | None = None,
    ) -> bool:
        return self._backend.bump_entity_atom_count(entity_id, delta=delta, last_promoted_at=last_promoted_at)

    def update_entity_canonical_name(self, entity_id: str, canonical_name: str) -> bool:
        """Update the canonical_name of an existing entity.

        Used by the User singleton upgrade path when the user reveals their
        real name after the entity was initially created with a generic
        placeholder (e.g. 'User').
        """
        return self._backend.update_entity_canonical_name(entity_id, canonical_name)

    def merge_entity(self, source_id: str, target_id: str) -> int:
        """Migrate all atoms under the source entity to the target entity and record a journal entry.

        Execution order:
        1. Call ``backend.migrate_atoms_to_entity`` to migrate atoms in bulk (transactional).
        2. Update ``atom_count``: target entity +N, source entity reset to 0.
        3. Write a journal entry (``action="entity_merge"``).
        4. Mark the target entity's ``EntityPage`` dirty.

        Returns the number of atoms actually migrated.
        """
        now = datetime.now(UTC)
        migrated = self._backend.migrate_atoms_to_entity(source_id, target_id)

        if migrated > 0:
            # Update atom_count: target +N, source reset to 0
            self._backend.bump_entity_atom_count(target_id, delta=migrated, last_promoted_at=now)
            # Subtract the migrated count from the source entity's atom_count (reset to 0)
            source_entity = self._backend.get_entity(source_id)
            if source_entity is not None and source_entity.atom_count > 0:
                self._backend.bump_entity_atom_count(
                    source_id,
                    delta=-source_entity.atom_count,
                )

        # Write a journal entry (record the merge regardless of whether any atoms were migrated)
        self._backend.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now,
                action="entity_merge",
                actor="rule",
                target_entity_id=target_id,
                note=(f"entity_merge: source={source_id} target={target_id} migrated_atoms={migrated}"),
            )
        )

        # Mark the target entity's EntityPage dirty
        self._backend.mark_entity_page_dirty(target_id, when=now)

        return migrated

    # ------------------------------------------------------------------
    # M3 - Entity Pages (long-form summary; D32-D37)
    # ------------------------------------------------------------------

    def upsert_entity_page(self, page: EntityPage) -> None:
        """Insert or replace an EntityPage row keyed by ``entity_id``."""
        self._backend.upsert_entity_page(page)

    def get_entity_page(self, entity_id: str) -> EntityPage | None:
        return self._backend.get_entity_page(entity_id)

    def list_dirty_entity_pages(self, *, limit: int = 50) -> list[EntityPage]:
        return self._backend.list_dirty_entity_pages(limit=limit)

    def mark_entity_page_dirty(self, entity_id: str, *, when: datetime | None = None) -> None:
        """Mark the page for ``entity_id`` dirty (D33-B async cron trigger)."""
        self._backend.mark_entity_page_dirty(entity_id, when=when or datetime.now(UTC))

    def apply_entity_page_regen(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        headline: str,
        topics: list[str],
        when: datetime | None = None,
    ) -> bool:
        """Apply a successful regen result to the page row."""
        return self._backend.apply_entity_page_regen(
            entity_id,
            summary_markdown=summary_markdown,
            headline=headline,
            topics=topics,
            when=when or datetime.now(UTC),
        )

    def record_entity_page_regen_failure(
        self,
        entity_id: str,
        *,
        when: datetime | None = None,
    ) -> bool:
        return self._backend.record_entity_page_regen_failure(
            entity_id,
            when=when or datetime.now(UTC),
        )

    def apply_entity_page_user_edit(
        self,
        entity_id: str,
        *,
        summary_markdown: str,
        when: datetime | None = None,
    ) -> bool:
        return self._backend.apply_entity_page_user_edit(
            entity_id,
            summary_markdown=summary_markdown,
            when=when or datetime.now(UTC),
        )

    # ------------------------------------------------------------------
    # M4 — Thread Active-Entity Stack (D41a + D41b)
    # ------------------------------------------------------------------

    def upsert_active_entity(
        self,
        thread_id: str,
        entity_id: str,
        *,
        source: str = "recall_hit",
        when: datetime | None = None,
        keep: int = 5,
    ) -> None:
        """Push ``entity_id`` to the head of ``thread_id``'s LRU stack.

        Idempotent — re-pushing refreshes ``last_seen_at``. After every
        upsert we evict everything past the ``keep`` newest rows so the
        table never grows unbounded for long threads.
        """
        record = ActiveEntity(
            thread_id=thread_id,
            entity_id=entity_id,
            last_seen_at=when or datetime.now(UTC),
            source=source,  # type: ignore[arg-type]
        )
        self._backend.upsert_active_entity(record)
        self._backend.evict_active_entities(thread_id, keep=keep)

    def list_active_entities(
        self,
        thread_id: str,
        *,
        limit: int = 5,
    ) -> list[ActiveEntity]:
        return self._backend.list_active_entities(thread_id, limit=limit)

    # ------------------------------------------------------------------
    # M2 — Aliases
    # ------------------------------------------------------------------

    def add_alias(self, alias: Alias) -> None:
        self._backend.save_alias(alias)

    def find_entity_by_alias(self, alias: str) -> Entity | None:
        """Look up the entity that the given (already-normalized) alias resolves to."""
        return self._backend.find_entity_by_alias(alias)

    def list_aliases(
        self,
        *,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[Alias]:
        return self._backend.list_aliases(entity_id=entity_id, limit=limit)

    # ------------------------------------------------------------------
    # M2 — Journal (L4)
    # ------------------------------------------------------------------

    LAST_EXTRACT_RUN_META_KEY = "last_extract_run"

    def append_journal(self, entry: JournalEntry) -> None:
        """Append a journal entry. Pipeline rows expire via :meth:`delete_journal`."""
        self._backend.append_journal(entry)

    def delete_journal(
        self,
        *,
        actions: Sequence[str],
        before: datetime,
        limit: int,
        dry_run: bool = False,
    ) -> int:
        """Delete expired pipeline journal rows. See ADR-028."""
        return self._backend.delete_journal(
            actions=actions,
            before=before,
            limit=limit,
            dry_run=dry_run,
        )

    def get_meta(self, key: str) -> str | None:
        return self._backend.get_meta(key)

    def set_meta(self, key: str, value: str) -> None:
        self._backend.set_meta(key, value)

    def get_last_extract_run(self) -> dict[str, Any] | None:
        """Latest extract pass summary (meta, not journal). ``None`` if never run."""
        raw = self.get_meta(self.LAST_EXTRACT_RUN_META_KEY)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def record_extract_run(self, stats: dict[str, Any], *, when: datetime | None = None) -> None:
        """Overwrite the latest extract summary in meta. Does not append journal."""
        payload = dict(stats)
        payload.setdefault("timestamp", (when or datetime.now(UTC)).isoformat())
        self.set_meta(self.LAST_EXTRACT_RUN_META_KEY, json.dumps(payload, ensure_ascii=False))

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
        return self._backend.list_journal(
            action=action,
            target_entity_id=target_entity_id,
            target_atom_id=target_atom_id,
            target_candidate_id=target_candidate_id,
            after=after,
            before=before,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # M2 — Promotion (L1 → L2)
    # ------------------------------------------------------------------

    def promote_candidates(
        self,
        candidates: list[Candidate] | None = None,
        *,
        limit: int = 50,
        llm_hook: object | None = None,
    ) -> PromotionResult:
        """Run the 5-check promotion worker against a batch of candidates.

        Convenience wrapper around :class:`PromotionWorker`. When
        ``candidates`` is ``None`` the worker picks up all currently
        ``pending`` rows up to ``limit``.

        ``llm_hook`` (optional) is any object satisfying the
        :class:`LLMEscalationHook` protocol — typically a
        :class:`ModelEscalationHook` wrapping the host LLM client.
        When ``None`` the worker runs the pure-rule path. Hook is
        ``object`` typed here to avoid a circular import; the worker
        re-narrows the type internally.
        """
        from octop_memory.pipeline.promotion import PromotionWorker

        worker = PromotionWorker(self, llm_hook=llm_hook)  # type: ignore[arg-type]
        n_in = "pending" if candidates is None else len(candidates)
        logger.info("memory.trigger promote start ns=%s candidates=%s limit=%d", self._namespace, n_in, limit)
        result = worker.promote_pending(limit=limit) if candidates is None else worker.promote(candidates)
        logger.info(
            "memory.trigger promote done ns=%s promoted=%d merged=%d conflicts=%d "
            "needs_review=%d dropped=%d llm_calls=%d",
            self._namespace,
            result.promoted,
            result.merged,
            result.conflicts,
            result.needs_review,
            result.dropped,
            result.llm_calls,
        )
        return result

    # ------------------------------------------------------------------
    # M5 — Episodes (L2.5) and Digests
    # ------------------------------------------------------------------

    def add_episodes(self, episodes: list[Episode]) -> None:
        """Persist many episodes inside a single backend transaction."""
        if not episodes:
            return
        with self._backend.transaction():
            for ep in episodes:
                self._backend.save_episode(ep)

    def get_episode(self, episode_id: str) -> Episode | None:
        return self._backend.get_episode(episode_id)

    def list_episodes(
        self,
        *,
        session_id: str | None = None,
        emotion: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Episode]:
        return self._backend.list_episodes(
            session_id=session_id,
            emotion=emotion,
            after=after,
            before=before,
            limit=limit,
        )

    def search_episodes(self, query: str, *, limit: int = 10) -> list[Episode]:
        return self._backend.search_episodes(query, limit=limit)

    def list_episodes_in_range(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> list[Episode]:
        return self._backend.list_episodes_in_range(start=start, end=end, limit=limit)

    def upsert_digest(self, digest: DigestRecord) -> None:
        self._backend.upsert_digest(digest)

    def get_digest(self, period_kind: DigestPeriod, period_key: str) -> DigestRecord | None:
        return self._backend.get_digest(period_kind, period_key)

    def list_digests(
        self,
        *,
        period_kind: DigestPeriod | None = None,
        limit: int = 50,
    ) -> list[DigestRecord]:
        return self._backend.list_digests(period_kind=period_kind, limit=limit)

    # ------------------------------------------------------------------
    # Memory tree
    # ------------------------------------------------------------------

    def get_tree(self) -> list[MemoryNode]:
        """Get the full memory tree."""
        return self._backend.get_tree()

    # ------------------------------------------------------------------
    # Checkpointer delegation (BaseCheckpointSaver protocol)
    # ------------------------------------------------------------------

    def get_tuple(self, config: Any) -> Any:
        """Get a checkpoint tuple by config. Delegates to internal checkpointer."""
        self._ensure_checkpointer()
        return self._checkpointer.get_tuple(config)

    def put(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        """Persist a checkpoint. Delegates to internal checkpointer."""
        self._ensure_checkpointer()
        return self._checkpointer.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persist intermediate writes. Delegates to internal checkpointer."""
        self._ensure_checkpointer()
        self._checkpointer.put_writes(config, writes, task_id, task_path)

    def list(
        self,
        config: Any | None,
        *,
        filter: dict[str, Any] | None = None,  # name fixed by BaseCheckpointSaver protocol
        before: Any | None = None,
        limit: int | None = None,
    ) -> Iterator[Any]:
        """List checkpoints. Delegates to internal checkpointer."""
        self._ensure_checkpointer()
        yield from self._checkpointer.list(config, filter=filter, before=before, limit=limit)

    # ------------------------------------------------------------------
    # Async checkpointer delegation
    # ------------------------------------------------------------------

    async def aget_tuple(self, config: Any) -> Any:
        """Async version of get_tuple. Wraps sync call via asyncio.to_thread."""
        self._ensure_checkpointer()
        return await asyncio.to_thread(self._checkpointer.get_tuple, config)

    async def aput(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        """Async version of put. Wraps sync call via asyncio.to_thread."""
        self._ensure_checkpointer()
        return await asyncio.to_thread(self._checkpointer.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Async version of put_writes. Wraps sync call via asyncio.to_thread."""
        self._ensure_checkpointer()
        await asyncio.to_thread(self._checkpointer.put_writes, config, writes, task_id, task_path)

    async def alist(
        self,
        config: Any | None,
        *,
        filter: dict[str, Any] | None = None,  # name fixed by BaseCheckpointSaver protocol
        before: Any | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Any]:
        """Async version of list. Wraps sync iteration via asyncio.to_thread."""
        self._ensure_checkpointer()
        results = await asyncio.to_thread(
            lambda: builtins.list(self._checkpointer.list(config, filter=filter, before=before, limit=limit))
        )
        for item in results:
            yield item

    # ------------------------------------------------------------------
    # Thread management
    # ------------------------------------------------------------------

    def list_threads(self, *, limit: int | None = None) -> builtins.list[ThreadSummary]:
        """List all checkpointed threads.

        Args:
            limit: Maximum number of threads to return. If None, return all.
        """
        self._ensure_checkpointer()
        seen: dict[str, ThreadSummary] = {}
        for cp_tuple in self._checkpointer.list(None):
            thread_id = cp_tuple.config["configurable"]["thread_id"]
            if thread_id not in seen:
                ts = cp_tuple.checkpoint.get("ts")
                seen[thread_id] = ThreadSummary(
                    thread_id=thread_id,
                    checkpoint_id=cp_tuple.checkpoint["id"],
                    created_at=datetime.fromisoformat(ts) if ts else None,
                    updated_at=datetime.fromisoformat(ts) if ts else None,
                )
            if limit is not None and len(seen) >= limit:
                break
        return list(seen.values())

    def get_thread_state(self, thread_id: str) -> ThreadState | None:
        """Get the latest state for a thread."""
        self._ensure_checkpointer()
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        result = self._checkpointer.get_tuple(config)
        if result is None:
            return None
        ts = result.checkpoint.get("ts")
        return ThreadState(
            thread_id=thread_id,
            checkpoint_id=result.checkpoint["id"],
            channel_values=result.checkpoint.get("channel_values", {}),
            metadata=result.metadata or {},
            created_at=datetime.fromisoformat(ts) if ts else None,
        )

    def delete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints for a thread.

        Raises ``NotImplementedError`` when the underlying saver has no
        delete support — silently keeping data the caller asked to
        delete is not an acceptable fallback (privacy/retention).
        """
        self._ensure_checkpointer()
        if not hasattr(self._checkpointer, "delete_thread"):
            raise NotImplementedError(
                f"checkpointer {type(self._checkpointer).__name__!r} does not support "
                f"delete_thread; thread {thread_id!r} was NOT deleted"
            )
        self._checkpointer.delete_thread(thread_id)

    async def adelete_thread(self, thread_id: str) -> None:
        """Async version of delete_thread. Wraps sync call via asyncio.to_thread."""
        await asyncio.to_thread(self.delete_thread, thread_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_manual_atom(
        self,
        content: str,
        *,
        topic: str | None,
        parent_id: str | None,
        conversation_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> MemoryNode:
        """Persist a manual fact through the same canonical pipeline as promotion.

        All writes are wrapped in a single backend transaction so that a
        mid-flight exception leaves no partial rows (RISK-013).
        """
        from octop_memory.domain.alias import normalize_alias

        now = datetime.now(UTC)

        entity_name = topic.strip() if topic and topic.strip() else "General"

        with self._backend.transaction():
            raw = self.add_raw(
                content,
                event_type="manual",
                host="manual",
                session_id=conversation_id,
                payload={"metadata": dict(metadata) if metadata else {}},
            )

            entity = self.find_entity_by_name(entity_name, entity_type="Fact")
            if entity is None:
                entity = Entity(
                    id=str(uuid.uuid4()),
                    entity_type="Fact",
                    canonical_name=entity_name,
                    aliases=[entity_name],
                    atom_count=0,
                    created_at=now,
                )
                self.add_entity(entity)
                normalized = normalize_alias(entity_name)
                if normalized:
                    self.add_alias(
                        Alias(
                            alias=normalized,
                            entity_id=entity.id,
                            entity_type=entity.entity_type,
                            created_by="user",
                            created_at=now,
                        )
                    )

            candidate = Candidate(
                id=str(uuid.uuid4()),
                raw_event_ids=[raw.id],
                candidate_type="Fact",
                status="promoted",
                title=topic or content[:80],
                assertion=content,
                verbatim_quote=content[:200],
                quote_event_id=raw.id,
                subject_name=entity.canonical_name,
                subject_entity_type=entity.entity_type,
                target_entity_id=entity.id,
                confidence="high",
                importance="medium",
                recommended_action="promote",
                promotion_reason="Manual Memory.store() write",
                extractor_version="manual/v1",
                created_at=now,
                decided_at=now,
                decided_by="user",
                session_id=conversation_id,
                payload={"metadata": dict(metadata) if metadata else {}},
            )
            self.add_candidate(candidate)

            atom = AtomCard(
                id=str(uuid.uuid4()),
                entity_id=entity.id,
                candidate_id=candidate.id,
                raw_event_ids=[raw.id],
                assertion=content,
                verbatim_quote=content[:200],
                quote_event_id=raw.id,
                search_terms=[entity.canonical_name, topic] if topic else [entity.canonical_name],
                occurred_at=raw.timestamp,
                confidence="high",
                importance="medium",
                created_at=now,
            )
            self._backend.save_atom(atom)
            leaf = self._link_atom_to_tree(
                atom,
                parent_id=parent_id,
                topic=topic,
                conversation_id=conversation_id,
                metadata=metadata,
            )
            self.bump_entity_atom_count(entity.id, delta=1, last_promoted_at=now)
            self.mark_entity_page_dirty(entity.id, when=now)
            self.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="promote",
                    actor="user",
                    target_entity_id=entity.id,
                    target_atom_id=atom.id,
                    target_candidate_id=candidate.id,
                    after={"assertion": atom.assertion},
                    note="Manual Memory.store() write promoted directly to AtomCard.",
                )
            )
        # After the transaction commits, sync-write to the vector index (outside the
        # transaction; a failure here doesn't affect the relational data)
        self._index_atom_vector(atom)
        logger.info(
            "memory.trigger store->atom ns=%s entity=%r atom=%s assertion=%r",
            self._namespace,
            entity.canonical_name,
            atom.id,
            content[:60],
        )
        return leaf

    def _index_atom_vector(
        self,
        atom: AtomCard,
        *,
        embedding: builtins.list[float] | None = None,
    ) -> None:
        """Write an AtomCard into the vector index (if a vector_index is configured).

        Args:
            atom: The AtomCard to index.
            embedding: A precomputed vector. If ``None`` and an embedding_provider is
                       configured, the provider is called to generate one automatically.
                       If neither is available, this silently no-ops.
        """
        if self._vector_index is None:
            return

        vec = embedding
        if vec is None:
            if self._embedding_provider is None:
                return  # No vector source available, silently skip
            try:
                vec = self._embedding_provider.embed(atom.assertion)
            except VECTOR_ERRORS:
                # embedding_provider is a user-supplied plugin; its concrete exception
                # types are unknown. Degrade the vector index, not the caller's write.
                logger.warning("atom embedding failed for %s", atom.id, exc_info=True)
                return

        payload: dict[str, object] = {
            "entity_id": atom.entity_id or "",
            "occurred_at": atom.occurred_at.isoformat(),
            "importance": atom.importance,
            "confidence": atom.confidence,
        }
        try:
            self._vector_index.upsert(atom.id, vec, payload)
        except VECTOR_ERRORS:
            logger.warning("vector upsert failed for %s", atom.id, exc_info=True)

    def _drop_atom_vector(self, atom_id: str) -> None:
        """Remove an atom from the vector index when one is configured."""
        if self._vector_index is None:
            return
        try:
            self._vector_index.delete(atom_id)
        except VECTOR_ERRORS:
            logger.warning("vector delete failed for %s", atom_id, exc_info=True)

    def _find_live_duplicate(
        self,
        entity_id: str,
        assertion: str,
        *,
        exclude_id: str | None = None,
    ) -> AtomCard | None:
        from octop_memory.domain.alias import normalize_alias

        sig = normalize_alias(assertion)
        if not sig:
            return None
        for atom in self.list_atoms(entity_id=entity_id, include_deprecated=False, limit=200):
            if exclude_id is not None and atom.id == exclude_id:
                continue
            if normalize_alias(atom.assertion) == sig:
                return atom
        return None

    def _resolve_manual_entity(
        self,
        *,
        entity_id: str | None,
        entity_name: str | None,
        entity_type: EntityType,
    ) -> tuple[Entity, bool]:
        """Return ``(entity, created)`` for a manual atom write.

        ``entity_id`` wins when provided. Otherwise resolve by User singleton,
        alias, then canonical name; create a new entity when nothing matches.
        """
        from octop_memory.domain.alias import normalize_alias

        if entity_id:
            entity = self.get_entity(entity_id)
            if entity is None:
                raise ValueError(f"entity {entity_id!r} not found")
            return entity, False

        name = (entity_name or "").strip()
        if not name:
            raise ValueError("entity_id or entity_name is required")

        if entity_type == "User":
            existing_users = self.list_entities(entity_type="User", limit=1)
            if existing_users:
                return existing_users[0], False

        normalized = normalize_alias(name)
        if normalized:
            aliased = self.find_entity_by_alias(normalized)
            if aliased is not None:
                return aliased, False
        by_name = self.find_entity_by_name(name, entity_type=entity_type)
        if by_name is not None:
            return by_name, False

        now = datetime.now(UTC)
        entity = Entity(
            id=str(uuid.uuid4()),
            entity_type=entity_type,
            canonical_name=name,
            aliases=[name],
            atom_count=0,
            created_at=now,
        )
        self.add_entity(entity)
        return entity, True

    @property
    def vector_index(self) -> VectorIndex | None:
        """The currently configured vector index (optional)."""
        return self._vector_index

    @property
    def embedding_provider(self) -> EmbeddingProvider | None:
        """The currently configured embedding provider (optional)."""
        return self._embedding_provider

    def get_or_create_entity_branch(self, entity_id: str) -> MemoryNode:
        """Return the branch node for ``entity_id``, creating it if absent.

        Promotion uses this to ensure every entity has a corresponding
        branch node so promoted leaves are organized under their entity
        rather than floating as top-level orphans.

        The branch ``content`` is set to the entity's ``canonical_name``
        at creation time; it is NOT updated on subsequent calls (the
        entity name is the stable organizational label).
        """
        # Check if a branch already exists for this entity via metadata.
        for node in self._backend.get_tree():
            if node.level == "branch" and node.metadata.get("entity_id") == entity_id:
                return node

        entity = self._backend.get_entity(entity_id)
        label = entity.canonical_name if entity else entity_id
        now = datetime.now(UTC)
        branch = MemoryNode(
            id=str(uuid.uuid4()),
            parent_id=None,
            level="branch",
            content=label,
            topic=None,
            conversation_id=None,
            created_at=now,
            updated_at=now,
            metadata={"entity_id": entity_id},
        )
        self._backend.save_node(branch)
        return branch

    def _link_atom_to_tree(
        self,
        atom: AtomCard,
        *,
        parent_id: str | None = None,
        topic: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryNode:
        """Create the unique organizational leaf that references ``atom``.

        Uses ``get_node_by_atom_id`` for O(1) duplicate detection instead
        of a full-tree scan.  ``content`` is intentionally left empty here
        because ``save_node`` enforces the ADR-010 rule (leaf content is
        always projected from ``AtomCard.assertion`` at read time).
        """
        existing = self._backend.get_node_by_atom_id(atom.id)
        if existing is not None:
            return existing

        if parent_id is not None:
            parent = self._backend.get_node(parent_id)
            if parent is None:
                raise ValueError(f"parent_id {parent_id!r} does not exist")
            if parent.level == "leaf":
                raise ValueError(
                    f"cannot attach 'leaf' under leaf parent {parent_id!r}; leaf nodes cannot have children"
                )

        now = datetime.now(UTC)
        node = MemoryNode(
            id=str(uuid.uuid4()),
            parent_id=parent_id,
            level="leaf",
            content=atom.assertion,  # projected value; save_node stores "" in DB per ADR-010
            topic=topic,
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata) if metadata else {},
            atom_id=atom.id,
        )
        self._backend.save_node(node)
        return node

    def _subtree_nodes(self, node_id: str) -> builtins.list[MemoryNode]:
        """Return a subtree snapshot before cascade deletion."""
        by_parent: dict[str | None, builtins.list[MemoryNode]] = {}
        by_id: dict[str, MemoryNode] = {}
        for node in self._backend.get_tree():
            by_id[node.id] = node
            by_parent.setdefault(node.parent_id, []).append(node)
        root = by_id.get(node_id)
        if root is None:
            return []
        out: builtins.list[MemoryNode] = []
        frontier = [root]
        while frontier:
            current = frontier.pop()
            out.append(current)
            frontier.extend(by_parent.get(current.id, []))
        return out

    def _is_postgres_backend(self) -> bool:
        try:
            from octop_memory.storage.backends.postgres import PostgresMemoryBackend
        except ImportError:
            return False
        return isinstance(self._backend, PostgresMemoryBackend)

    def _ensure_checkpointer(self) -> None:
        """Resolve the checkpointer on first use, or raise a precise error.

        The Postgres saver is built here rather than in ``__init__`` because it
        owns a ``ConnectionPool``: consumers that only read memory (dashboard
        RPC, the bridge, CLI inspection) never checkpoint, and opening a pool
        per ``Memory`` there just burns Postgres connections.
        """
        if self._checkpointer is None:
            with self._checkpointer_lock:
                if self._checkpointer is None:
                    self._checkpointer = self._create_postgres_checkpointer()
        if self._checkpointer is not None:
            return

        from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

        # Give a precise extras hint based on the backend type.
        if self._is_postgres_backend():
            raise ImportError(
                "Checkpointer with PostgreSQL backend requires "
                "'octop-memory[langgraph-postgres]'. "
                "Install with: pip install 'octop-memory[langgraph-postgres]'"
            )
        if not _LANGGRAPH_AVAILABLE:
            if isinstance(self._backend, SqliteMemoryBackend):
                raise ImportError(
                    "Checkpointer requires 'octop-memory[langgraph]'. "
                    "Install with: pip install 'octop-memory[langgraph]'"
                )
            raise ImportError(
                "Checkpointer requires 'octop-memory[langgraph]' (SQLite) or "
                "'octop-memory[langgraph-postgres]' (PostgreSQL). "
                "Install the appropriate extra for your backend."
            )
        raise ValueError(
            f"Backend {type(self._backend).__name__!r} does not support checkpointing. "
            "Supported backends: sqlite, postgres."
        )

    def _create_checkpointer(self) -> Any:
        """Create the saver eagerly, for backends whose handles are cheap.

        Only SQLite is built here — a local file handle. Postgres is deferred to
        :meth:`_ensure_checkpointer` because its saver owns a connection pool.
        """
        if not _LANGGRAPH_AVAILABLE:
            return None

        from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

        if isinstance(self._backend, SqliteMemoryBackend):
            import sqlite3

            try:
                from octop_memory.storage.backends.sqlite_checkpoint import CompactSqliteSaver
            except ImportError:
                # Base `langgraph` is installed but the SQLite checkpoint
                # extra isn't — degrade gracefully like the `_LANGGRAPH_AVAILABLE`
                # False case. `_ensure_checkpointer` raises a precise, helpful
                # error only if/when a caller actually reaches for checkpointing;
                # consumers that never touch it (e.g. the OpenClaw bridge)
                # must not fail to construct `Memory` over this.
                return None

            # Use a separate connection for the checkpointer so its
            # transaction management doesn't conflict with the memory
            # backend's own writes (they may run concurrently from
            # different threads).
            conn = sqlite3.connect(str(self._backend._db_path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            from octop_memory.storage.backends.sqlite import SQLITE_BUSY_TIMEOUT_MS

            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            # The switch changes new writes only; both formats remain readable.
            compact = os.environ.get("OCTOP_MEMORY_CHECKPOINT_DEDUP", "1") != "0"
            saver = CompactSqliteSaver(conn=conn, compact=compact)
            saver.setup()
            return saver

        return None

    def _create_postgres_checkpointer(self) -> Any:
        """Build the Postgres saver and its pool. Called on first checkpoint use.

        Returns ``None`` for non-Postgres backends and when
        ``langgraph-checkpoint-postgres`` is not installed; the caller turns
        that into a precise error only if checkpointing was actually needed.
        """
        if not _LANGGRAPH_AVAILABLE:
            return None

        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            from octop_memory.storage.backends.postgres import PostgresMemoryBackend
            from octop_memory.storage.backends.postgres_pool import acquire_pool
        except ImportError:
            return None

        # Narrow rather than duck-type ``_dsn``: reading backend privates without
        # a type check is what let SQLite-only GC run against Postgres.
        backend = self._backend
        if not isinstance(backend, PostgresMemoryBackend):
            return None

        pool = acquire_pool(backend._dsn, purpose="checkpoint", connect_kwargs=backend._connect_kwargs)
        try:
            saver = PostgresSaver(pool)

            def initialize() -> None:
                saver.setup()
                try:
                    from octop_memory.pipeline.lifecycle.vacuum import tune_checkpoint_autovacuum

                    with pool.connection() as conn:
                        tune_checkpoint_autovacuum(backend._dsn, connection=conn)
                except DRIVER_ERRORS:  # best-effort, never load-bearing
                    logger.warning("failed to tune checkpoint table autovacuum settings", exc_info=True)

            pool.initialize(initialize)
        except BaseException:
            pool.close()
            raise
        self._checkpointer_pool = pool
        return saver


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------


def _resolve_memory_backend(
    backend_type: str,
    namespace: str,
    config: dict[str, Any],
) -> MemoryBackend:
    """Resolve a backend type string to a MemoryBackend instance."""
    if backend_type == "sqlite":
        from octop_memory.storage.backends.sqlite import SqliteMemoryBackend

        return SqliteMemoryBackend(
            namespace=namespace,
            db_path=config.get("db_path", "~/.octop-memory/session.sqlite"),
        )
    if backend_type == "postgres":
        try:
            from octop_memory.storage.backends.postgres import PostgresMemoryBackend
        except ImportError as exc:
            raise ImportError(
                "PostgresMemoryBackend requires 'octop-memory[postgres]'. "
                "Install with: pip install 'octop-memory[postgres]'"
            ) from exc
        return PostgresMemoryBackend(namespace=namespace, **config)
    raise ValueError(f"Unknown memory backend type: {backend_type!r}. Supported: 'sqlite', 'postgres'")


__all__ = ["Memory"]
