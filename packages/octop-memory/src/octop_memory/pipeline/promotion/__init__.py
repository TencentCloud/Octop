"""PromotionWorker — turns L1 Candidates into L2 AtomCards (design §8.3).

Synchronous by design (D29): CLI and host bridge callers block until
the whole batch is decided.
The worst-case path is ~20 candidates x 1 LLM escalation each, which
fits comfortably inside the user-blocking budget.

Public surface:
- :class:`PromotionWorker` — orchestrator; wraps a :class:`Memory`
- :class:`PromotionResult` — aggregate counts + per-candidate outcomes

The worker is **demotion-only**: every candidate becomes an atom unless
one of the explicit downgrade conditions fires (low+low / dup / conflict
/ evidence problem). See ``checks.py`` for the per-check logic.

LLM escalation (alias disambiguation, semantic dup, semantic conflict)
is represented by :class:`LLMEscalationHook` from ``checks.py``.
Current host adapters inject :class:`ModelEscalationHook` for entity
disambiguation; duplicate/conflict checks remain rule-only in this worker.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from octop_memory.domain.alias import normalize_alias
from octop_memory.pipeline.promotion.checks import (
    LLMEscalationHook,
    PromotionOutcome,
    build_atom_from_candidate,
    check_conflict,
    check_duplicate,
    check_entity,
    check_evidence,
    check_value,
)
from octop_memory.types import (
    Alias,
    AtomCard,
    Candidate,
    Entity,
    JournalEntry,
)

if TYPE_CHECKING:
    from octop_memory.core import Memory


# ---------------------------------------------------------------------------
# Public result shape
# ---------------------------------------------------------------------------


@dataclass
class CandidateDecision:
    """Per-candidate outcome record (kept on the result for telemetry / CLI).

    ``atom`` is set only on ``promote`` (the new atom row); on ``merge``
    the candidate was attached to ``matched_atom_id`` of an existing atom.
    """

    candidate_id: str
    outcome: PromotionOutcome
    atom: AtomCard | None = None


@dataclass
class PromotionResult:
    """Aggregate of one ``promote()`` call.

    Counts are derived from ``decisions`` but pre-computed for
    convenience in tests / CLI summaries. ``llm_calls`` is the **total**
    consumed by this batch (each candidate is capped at 1 individually).
    """

    decisions: list[CandidateDecision] = field(default_factory=list)
    promoted: int = 0
    merged: int = 0
    conflicts: int = 0
    needs_review: int = 0
    dropped: int = 0
    llm_calls: int = 0

    def __post_init__(self) -> None:
        # Allow callers to construct an empty result and then ``.decisions``
        # populated step by step; we recompute counts here only when
        # explicit values are still zero AND decisions has content.
        if self.decisions and (self.promoted == self.merged == 0):
            for d in self.decisions:
                if d.outcome.kind == "promote":
                    self.promoted += 1
                elif d.outcome.kind == "merge":
                    self.merged += 1
                elif d.outcome.kind == "conflict":
                    self.conflicts += 1
                elif d.outcome.kind == "needs_review":
                    self.needs_review += 1
                elif d.outcome.kind == "drop":
                    self.dropped += 1
                self.llm_calls += d.outcome.llm_calls


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


# Maps candidate.candidate_type → JournalEntry actor / actions reuse
# the same vocabulary regardless of the originating candidate kind.
class PromotionWorker:
    """Run the 5-check promotion pipeline against a list of candidates.

    Construction is cheap; reuse one worker per ``Memory`` instance.

    The worker is the *only* place that mutates atom / entity / alias /
    journal tables when promoting from candidates. Other callers (CLI
    one-off ``add_atom`` etc.) bypass the worker by design.
    """

    def __init__(
        self,
        memory: Memory,
        *,
        llm_hook: LLMEscalationHook | None = None,
        clock: type[datetime] | None = None,
    ) -> None:
        self._memory = memory
        self._llm_hook = llm_hook
        self._clock = clock or datetime

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def promote(self, candidates: Sequence[Candidate]) -> PromotionResult:
        """Promote a batch of candidates synchronously.

        Candidates already in a terminal status (``promoted`` /
        ``rejected``) are skipped — the worker is idempotent w.r.t.
        status, but DOES re-decide ``pending`` / ``needs_review`` /
        ``conflict`` rows (so re-running after fixing data is safe).
        """
        decisions: list[CandidateDecision] = []
        for cand in candidates:
            if cand.status in ("promoted", "rejected"):
                continue
            decision = self._promote_one(cand)
            decisions.append(decision)
        return PromotionResult(decisions=decisions)

    def promote_pending(self, *, limit: int = 50) -> PromotionResult:
        """Convenience: pick up all current ``pending`` candidates and run them.

        ``limit`` caps a single batch — busy systems should call this in
        a loop until ``promoted + merged + conflicts + needs_review +
        dropped == 0``.
        """
        cands = self._memory.list_candidates(status="pending", limit=limit)
        return self.promote(cands)

    def approve(self, candidate: Candidate) -> CandidateDecision:
        """User override: write the atom without re-running demotion checks.

        Dashboard / CLI "采纳" for ``needs_review`` and ``conflict`` rows.
        The automatic 5-check path would just park a conflict candidate
        back in ``conflict`` (same polarity-flip still holds), so a human
        accept has to skip check 5 and, when a live contradictory atom
        exists, supersede it — "以这条草稿为准".

        Exact-match duplicates still merge (no second identical row).
        Terminal rows (``promoted`` / ``rejected``) raise ``ValueError``.
        """
        if candidate.status in ("promoted", "rejected"):
            raise ValueError(f"candidate {candidate.id!r} is already {candidate.status}")
        if candidate.payload.get("manual_revision"):
            from octop_memory.domain.retention import MANUAL_DOCUMENTS_META_KEY

            with self._memory.backend.transaction():
                record = json.loads(self._memory.get_meta(MANUAL_DOCUMENTS_META_KEY) or "{}")
                if record.get("revision") != candidate.payload["manual_revision"]:
                    raise ValueError("The manual document changed; review the current version before approving")
                return self._approve_one(candidate)
        return self._approve_one(candidate)

    # ------------------------------------------------------------------
    # Internal: per-candidate decision
    # ------------------------------------------------------------------

    def _promote_one(self, candidate: Candidate) -> CandidateDecision:
        # ---- check 1: long-term value -------------------------------
        outcome = check_value(candidate)
        if outcome is not None:
            return self._apply_drop(candidate, outcome)

        # ---- check 2: evidence --------------------------------------
        outcome = check_evidence(candidate, evidence_store=self._memory)
        if outcome is not None:
            if outcome.kind == "drop":
                return self._apply_drop(candidate, outcome)
            return self._apply_needs_review(candidate, outcome)

        # ---- check 3: entity resolution -----------------------------
        entity_outcome = check_entity(
            candidate,
            resolver=self._memory,
            llm_hook=self._llm_hook,
        )
        # check_entity returns either a "promote" carrier (with entity_id
        # OR new_entity_canonical_name set) or a "needs_review" if subject
        # was empty — handle the latter first.
        if entity_outcome.kind == "needs_review":
            return self._apply_needs_review(candidate, entity_outcome)

        entity_id = entity_outcome.entity_id
        if entity_id is None:
            # A new entity needs to be created before atom write. We
            # do this BEFORE check 4/5 so those checks can scan an
            # empty atom set (no false-positive dups against pre-existing
            # entities of a different name).
            entity_id = self._create_entity(
                canonical_name=entity_outcome.new_entity_canonical_name or candidate.subject_name,
                entity_type=entity_outcome.new_entity_type or candidate.subject_entity_type,
            )
        else:
            # check_entity routed the candidate to an existing entity
            # (entity_id). Check whether candidate.subject_name resolves to
            # a *different* existing entity: if so, that entity is a
            # duplicate of the current one, so migrate its atoms over.
            subject_entity = self._memory.find_entity_by_name(
                candidate.subject_name,
                entity_type=candidate.subject_entity_type,
            )
            if subject_entity is not None and subject_entity.id != entity_id:
                # Migrate subject_entity's atoms into the resolved entity_id.
                self._memory.merge_entity(subject_entity.id, entity_id)

        # ---- check 4: duplicate -------------------------------------
        outcome = check_duplicate(
            candidate,
            entity_id=entity_id,
            atom_lookup=self._memory,
            llm_hook=self._llm_hook,
        )
        if outcome is not None:
            return self._apply_merge(candidate, outcome)

        # ---- check 5: conflict --------------------------------------
        outcome = check_conflict(
            candidate,
            entity_id=entity_id,
            atom_lookup=self._memory,
            llm_hook=self._llm_hook,
        )
        if outcome is not None:
            return self._apply_conflict(candidate, outcome)

        # ---- happy path: write a new atom ---------------------------
        return self._apply_promote(
            candidate,
            entity_id=entity_id,
            entity_outcome=entity_outcome,
        )

    def _approve_one(self, candidate: Candidate) -> CandidateDecision:
        """Force-promote after resolving the entity (and maybe superseding)."""
        entity_outcome = check_entity(
            candidate,
            resolver=self._memory,
            llm_hook=self._llm_hook,
        )
        entity_id: str | None
        if entity_outcome.kind == "needs_review":
            if candidate.target_entity_id:
                entity_id = candidate.target_entity_id
                entity_outcome = PromotionOutcome(
                    kind="promote",
                    reason="user-approved; reused target_entity_id",
                    entity_id=entity_id,
                )
            else:
                return self._apply_needs_review(candidate, entity_outcome)
        else:
            entity_id = entity_outcome.entity_id
            if entity_id is None:
                entity_id = self._create_entity(
                    canonical_name=entity_outcome.new_entity_canonical_name or candidate.subject_name,
                    entity_type=entity_outcome.new_entity_type or candidate.subject_entity_type,
                )

        duplicate = check_duplicate(
            candidate,
            entity_id=entity_id,
            atom_lookup=self._memory,
            llm_hook=self._llm_hook,
        )
        if duplicate is not None:
            return self._apply_merge(candidate, duplicate, actor="user")

        conflict = check_conflict(
            candidate,
            entity_id=entity_id,
            atom_lookup=self._memory,
            llm_hook=self._llm_hook,
        )
        approved = PromotionOutcome(
            kind="promote",
            reason="user-approved via dashboard",
            entity_id=entity_id,
            matched_atom_id=conflict.matched_atom_id if conflict is not None else None,
            llm_calls=entity_outcome.llm_calls,
        )
        return self._apply_promote(
            candidate,
            entity_id=entity_id,
            entity_outcome=approved,
            actor="user",
            supersede_atom_id=conflict.matched_atom_id if conflict is not None else None,
        )

    # ------------------------------------------------------------------
    # Internal: state transitions (one per Outcome kind)
    # ------------------------------------------------------------------

    def _apply_drop(self, candidate: Candidate, outcome: PromotionOutcome) -> CandidateDecision:
        now = self._clock.now(UTC)
        self._memory.update_candidate_status(
            candidate.id,
            status="rejected",
            decided_by="rule",
            decided_at=now,
            promotion_reason=outcome.reason,
        )
        self._memory.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now,
                action="reject",
                actor="rule",
                target_candidate_id=candidate.id,
                note=outcome.reason,
            )
        )
        return CandidateDecision(candidate_id=candidate.id, outcome=outcome)

    def _apply_needs_review(self, candidate: Candidate, outcome: PromotionOutcome) -> CandidateDecision:
        now = self._clock.now(UTC)
        self._memory.update_candidate_status(
            candidate.id,
            status="needs_review",
            decided_by=None,
            decided_at=now,
            promotion_reason=outcome.reason,
        )
        # No journal append for needs_review — it's a queue state, not
        # a decision. Journal only captures terminal / decisive moves.
        return CandidateDecision(candidate_id=candidate.id, outcome=outcome)

    def _apply_merge(
        self,
        candidate: Candidate,
        outcome: PromotionOutcome,
        *,
        actor: Literal["user", "auto", "rule"] = "rule",
    ) -> CandidateDecision:
        now = self._clock.now(UTC)
        self._memory.update_candidate_status(
            candidate.id,
            status="promoted",
            decided_by=actor,
            decided_at=now,
            target_entity_id=outcome.entity_id,
            promotion_reason=outcome.reason,
        )
        self._memory.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now,
                action="merge",
                actor=actor,
                target_entity_id=outcome.entity_id,
                target_atom_id=outcome.matched_atom_id,
                target_candidate_id=candidate.id,
                note=outcome.reason,
            )
        )
        return CandidateDecision(candidate_id=candidate.id, outcome=outcome)

    def _apply_conflict(self, candidate: Candidate, outcome: PromotionOutcome) -> CandidateDecision:
        now = self._clock.now(UTC)
        self._memory.update_candidate_status(
            candidate.id,
            status="conflict",
            decided_by=None,
            decided_at=now,
            target_entity_id=outcome.entity_id,
            promotion_reason=outcome.reason,
        )
        self._memory.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=now,
                action="conflict",
                actor="rule",
                target_entity_id=outcome.entity_id,
                target_atom_id=outcome.matched_atom_id,
                target_candidate_id=candidate.id,
                note=outcome.reason,
            )
        )
        return CandidateDecision(candidate_id=candidate.id, outcome=outcome)

    def _apply_promote(
        self,
        candidate: Candidate,
        *,
        entity_id: str,
        entity_outcome: PromotionOutcome,
        actor: Literal["user", "auto", "rule"] = "auto",
        supersede_atom_id: str | None = None,
    ) -> CandidateDecision:
        now = self._clock.now(UTC)
        # Use the earliest timestamp among raw_event_ids as occurred_at, so
        # it reflects when the event actually happened rather than when the
        # candidate was extracted (fixes wrong timestamps on re-extraction).
        occurred_at: datetime | None = None
        if candidate.raw_event_ids:
            raw_events = self._memory.get_raw_events_by_ids(list(candidate.raw_event_ids))
            if raw_events:
                occurred_at = min(e.timestamp for e in raw_events)
        atom = build_atom_from_candidate(
            candidate,
            atom_id=str(uuid.uuid4()),
            entity_id=entity_id,
            now=now,
            occurred_at=occurred_at,
        )
        # Wrap all writes in a single transaction so that a mid-flight
        # exception leaves no partial rows (RISK-013). SQLite and Postgres
        # both no-op nested ``_commit()`` while ``_in_transaction`` is set.
        with self._memory._backend.transaction():
            # Ensure the entity has a branch node in the tree, then link the
            # new atom leaf under it so promoted facts are organized by entity.
            entity_branch = self._memory.get_or_create_entity_branch(entity_id)
            self._memory.add_atom(atom, parent_id=entity_branch.id)
            if supersede_atom_id:
                # Replacement: old row already counted on the entity.
                superseded = self._memory.supersede_atom(
                    supersede_atom_id,
                    new_atom_id=atom.id,
                    deprecated_at=now,
                )
                if not superseded:
                    raise ValueError(f"atom {supersede_atom_id!r} was replaced concurrently")
            else:
                self._memory.bump_entity_atom_count(
                    entity_id,
                    delta=1,
                    last_promoted_at=now,
                )
            # M3 D33-B: mark the entity's page dirty so the async cron worker
            # picks it up. Imported lazily to keep the promotion module
            # importable without the page subpackage on the path (and to
            # avoid pulling page deps into M2-only test setups).
            from octop_memory.pipeline.page.trigger import mark_entity_dirty_after_promote

            mark_entity_dirty_after_promote(self._memory, entity_id, when=now)

            # Always materialize the candidate's subject_name as an alias.
            # Idempotent at the DB layer (PRIMARY KEY (alias, entity_id) +
            # INSERT OR IGNORE), so re-running on the same candidate is safe.
            self._save_alias_if_needed(
                subject_name=candidate.subject_name,
                entity_id=entity_id,
                entity_type=candidate.subject_entity_type,
            )
            # User singleton upgrade: if the existing canonical_name is a
            # generic placeholder (e.g. "User") and the candidate provides a
            # real name, promote the real name to canonical_name.
            if candidate.subject_entity_type == "User":
                self._upgrade_user_canonical_name(
                    entity_id=entity_id,
                    new_subject_name=candidate.subject_name,
                )

            note = entity_outcome.reason
            if supersede_atom_id:
                note = f"{note}; superseded {supersede_atom_id}"
            self._memory.update_candidate_status(
                candidate.id,
                status="promoted",
                decided_by=actor,
                decided_at=now,
                target_entity_id=entity_id,
                promotion_reason=note,
            )
            self._memory.append_journal(
                JournalEntry(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    action="promote",
                    actor=actor,
                    target_entity_id=entity_id,
                    target_atom_id=atom.id,
                    target_candidate_id=candidate.id,
                    before={"atom_id": supersede_atom_id} if supersede_atom_id else None,
                    after={"atom_id": atom.id, "assertion": atom.assertion},
                    note=note,
                )
            )
        # Index atom vector after transaction commit (outside tx; failure does not affect relational data)
        self._memory._index_atom_vector(atom)
        # Refresh the outcome with the resolved entity_id (it may have
        # been None when check_entity proposed a NEW entity).
        resolved_outcome = PromotionOutcome(
            kind="promote",
            reason=entity_outcome.reason,
            entity_id=entity_id,
            llm_calls=entity_outcome.llm_calls,
        )
        return CandidateDecision(
            candidate_id=candidate.id,
            outcome=resolved_outcome,
            atom=atom,
        )

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    def _create_entity(self, *, canonical_name: str, entity_type: str) -> str:
        """Insert a new Entity row and return its id.

        Also eagerly creates the corresponding branch node in the memory
        tree so that the first promoted atom for this entity is immediately
        organized under the branch rather than floating as an orphan.
        """
        entity_id = str(uuid.uuid4())
        now = self._clock.now(UTC)
        entity = Entity(
            id=entity_id,
            entity_type=entity_type,  # type: ignore[arg-type]
            canonical_name=canonical_name,
            aliases=[],
            atom_count=0,
            created_at=now,
        )
        self._memory.add_entity(entity)
        # Eagerly create the branch node so the first atom link has a parent.
        self._memory.get_or_create_entity_branch(entity_id)
        return entity_id

    def _save_alias_if_needed(
        self,
        *,
        subject_name: str,
        entity_id: str,
        entity_type: str,
    ) -> None:
        normalized = normalize_alias(subject_name)
        if not normalized:
            return
        existing = self._memory.find_entity_by_alias(normalized)
        if existing is not None and existing.id == entity_id:
            return
        self._memory.add_alias(
            Alias(
                alias=normalized,
                entity_id=entity_id,
                entity_type=entity_type,  # type: ignore[arg-type]
                created_by="rule",
                created_at=self._clock.now(UTC),
            )
        )

    # Generic placeholder names that should be replaced by a real name
    # when the user later reveals their actual name.
    _GENERIC_USER_NAMES = frozenset({"user", "the user", "用户", "我", "i"})

    def _upgrade_user_canonical_name(
        self,
        *,
        entity_id: str,
        new_subject_name: str,
    ) -> None:
        """Upgrade a generic User canonical_name (e.g. 'User') to a real name.

        When the extractor first sees a User candidate it may use a generic
        placeholder like 'User'. Once the user reveals their real name
        (e.g. 'Eileen'), we upgrade the canonical_name so the entity is
        human-readable. The old name is kept as an alias.
        """
        entity = self._memory.get_entity(entity_id)
        if entity is None:
            return
        current = (getattr(entity, "canonical_name", "") or "").strip()
        new_name = new_subject_name.strip()
        # Only upgrade if the current name is a known generic placeholder
        # and the new name looks like a real name (not also a placeholder).
        if (
            current.lower() in self._GENERIC_USER_NAMES
            and new_name
            and new_name.lower() not in self._GENERIC_USER_NAMES
            and current.lower() != new_name.lower()
        ):
            self._memory.update_entity_canonical_name(entity_id, new_name)


# ---------------------------------------------------------------------------
# Convenience: top-level function for callers that already have a Memory
# ---------------------------------------------------------------------------


def promote_candidates(
    memory: Memory,
    candidates: Iterable[Candidate],
    *,
    llm_hook: LLMEscalationHook | None = None,
) -> PromotionResult:
    """Stateless one-shot wrapper around :class:`PromotionWorker`.

    Useful for tests and one-off CLI invocations where constructing a
    long-lived worker is overkill.
    """
    worker = PromotionWorker(memory, llm_hook=llm_hook)
    return worker.promote(list(candidates))


__all__ = [
    "CandidateDecision",
    "PromotionResult",
    "PromotionWorker",
    "promote_candidates",
]
