"""M2.8 fallback rules — keep the review queue from rotting.

Two scheduled tasks the user can run via ``memory candidate fallback``:

1. **Stale needs_review → auto-promote (D19)**
   Per design §8.3.3, a candidate sitting in ``needs_review`` longer
   than ``stale_days`` (default 7) gets force-promoted as a low-confidence
   atom. We do NOT silently drop it — even if the rule path was uncertain,
   the user's words deserve to live somewhere recallable. The
   journal actor is ``"rule"`` so audit can distinguish from auto / user.

2. **Repeated rejections → re-escalate**
   Per design §8.3.3, when a candidate's normalized assertion has been
   rejected ``rejection_threshold`` times (default 2) in the past and
   re-appears as ``pending``, we flip it to ``needs_review`` rather
   than letting the rule path silently drop it again. The journal
   records the action so reviewers see the trail.

These functions are pure idempotent rule passes — no LLM calls. Safe to
run on a cron / Code Studio nightly task.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from octop_memory.domain.alias import normalize_alias
from octop_memory.pipeline.promotion.checks import build_atom_from_candidate
from octop_memory.types import (
    Alias,
    Candidate,
    Entity,
    JournalEntry,
)

if TYPE_CHECKING:
    from octop_memory.core import Memory


DEFAULT_STALE_DAYS = 7
DEFAULT_REJECTION_THRESHOLD = 2


@dataclass
class FallbackResult:
    """Aggregate of one ``run_fallback_pass`` invocation.

    ``stale_promoted`` are candidates auto-promoted from needs_review.
    ``re_escalated`` are pending candidates flipped to needs_review.
    """

    stale_promoted: list[str]
    re_escalated: list[str]


def run_fallback_pass(
    memory: Memory,
    *,
    now: datetime | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    rejection_threshold: int = DEFAULT_REJECTION_THRESHOLD,
    limit: int = 200,
) -> FallbackResult:
    """Run both fallback tasks against the current memory namespace.

    Returns the aggregated :class:`FallbackResult`. Both tasks are
    idempotent — re-running the same day adds nothing once the queues
    are clean.
    """
    when = now or datetime.now(UTC)
    stale = _promote_stale_needs_review(
        memory,
        when=when,
        stale_days=stale_days,
        limit=limit,
    )
    re_esc = _re_escalate_repeated_rejections(
        memory,
        when=when,
        threshold=rejection_threshold,
        limit=limit,
    )
    return FallbackResult(stale_promoted=stale, re_escalated=re_esc)


# ---------------------------------------------------------------------------
# Task 1 — stale needs_review → auto-promote
# ---------------------------------------------------------------------------


def _promote_stale_needs_review(
    memory: Memory,
    *,
    when: datetime,
    stale_days: int,
    limit: int,
) -> list[str]:
    """Auto-promote needs_review candidates older than ``stale_days``.

    The atom is created with ``importance`` and ``confidence`` of the
    candidate **forced down to "low"** so it ranks low at recall time
    (per design §8.3.3 "not lost, but ranked low").
    """
    cutoff = when - timedelta(days=stale_days)
    queue = memory.list_candidates(status="needs_review", limit=limit)

    promoted: list[str] = []
    for cand in queue:
        # ``decided_at`` is when the candidate ENTERED needs_review —
        # we age from there. Some legacy rows may not have decided_at;
        # fall back to created_at so they still age out eventually.
        anchor = cand.decided_at or cand.created_at
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        if anchor > cutoff:
            continue

        # Force-promote: build atom with confidence=low; reuse subject_name
        # to resolve / create the entity, mirroring the worker happy path
        # but with actor="rule" + reason flagging the fallback.
        downgraded = _downgrade_for_fallback(cand)
        entity_id = _resolve_or_create_entity(memory, downgraded, when=when)
        atom = build_atom_from_candidate(
            downgraded,
            atom_id=str(uuid.uuid4()),
            entity_id=entity_id,
            now=when,
        )
        memory.add_atom(atom)
        memory.bump_entity_atom_count(entity_id, delta=1, last_promoted_at=when)
        memory.update_candidate_status(
            cand.id,
            status="promoted",
            decided_by="rule",
            decided_at=when,
            target_entity_id=entity_id,
            promotion_reason=f"7-day fallback auto-promote (stale needs_review > {stale_days}d)",
        )
        memory.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=when,
                action="promote",
                actor="rule",
                target_entity_id=entity_id,
                target_atom_id=atom.id,
                target_candidate_id=cand.id,
                note=f"stale_days={stale_days}",
            )
        )
        promoted.append(cand.id)
    return promoted


def _downgrade_for_fallback(c: Candidate) -> Candidate:
    """Return a copy with confidence forced to 'low' for fallback promotion."""
    return Candidate(
        id=c.id,
        raw_event_ids=list(c.raw_event_ids),
        candidate_type=c.candidate_type,
        status=c.status,
        title=c.title,
        assertion=c.assertion,
        verbatim_quote=c.verbatim_quote,
        quote_event_id=c.quote_event_id,
        subject_name=c.subject_name,
        subject_entity_type=c.subject_entity_type,
        target_entity_id=c.target_entity_id,
        confidence="low",  # forced
        importance=c.importance,
        recommended_action=c.recommended_action,
        promotion_reason=c.promotion_reason,
        extractor_version=c.extractor_version,
        created_at=c.created_at,
        decided_at=c.decided_at,
        decided_by=c.decided_by,
        session_id=c.session_id,
    )


def _resolve_or_create_entity(memory: Memory, c: Candidate, *, when: datetime) -> str:
    """Mini version of check 3 happy path (no LLM). Returns entity_id.

    Mirrors the User singleton rule from ``check_entity``: if the candidate
    is of entity_type "User", always resolve to the single existing User
    entity (if any) rather than creating a duplicate.
    """
    # User singleton rule: one agent → one User entity, regardless of subject_name.
    if c.subject_entity_type == "User":
        existing_users = memory.list_entities(entity_type="User", limit=1)
        if existing_users:
            return existing_users[0].id

    normalized = normalize_alias(c.subject_name)
    if normalized:
        hit = memory.find_entity_by_alias(normalized)
        if hit is not None:
            return hit.id
    if c.subject_name.strip():
        by_name = memory.find_entity_by_name(c.subject_name, entity_type=c.subject_entity_type)
        if by_name is not None:
            return by_name.id
    new_id = str(uuid.uuid4())
    memory.add_entity(
        Entity(
            id=new_id,
            entity_type=c.subject_entity_type,
            canonical_name=c.subject_name or "(unknown)",
            aliases=[],
            atom_count=0,
            created_at=when,
        )
    )
    if normalized:
        memory.add_alias(
            Alias(
                alias=normalized,
                entity_id=new_id,
                entity_type=c.subject_entity_type,
                created_by="rule",
                created_at=when,
            )
        )
    return new_id


# ---------------------------------------------------------------------------
# Task 2 — repeated rejections → re-escalate to needs_review
# ---------------------------------------------------------------------------


def _re_escalate_repeated_rejections(
    memory: Memory,
    *,
    when: datetime,
    threshold: int,
    limit: int,
) -> list[str]:
    """Flip pending candidates whose assertion was rejected >= ``threshold`` times in the past.

    Implementation: scan all rejected candidates, build a frequency map
    of normalized assertions. For every pending candidate whose normalized
    assertion is in the map AND the count >= threshold, flip to
    needs_review and journal the escalation.
    """
    rejected = memory.list_candidates(status="rejected", limit=2_000)
    if not rejected:
        return []

    rejection_counts: dict[str, int] = {}
    for r in rejected:
        sig = normalize_alias(r.assertion)
        if sig:
            rejection_counts[sig] = rejection_counts.get(sig, 0) + 1

    if not rejection_counts:
        return []

    pending = memory.list_candidates(status="pending", limit=limit)
    escalated: list[str] = []
    for cand in pending:
        sig = normalize_alias(cand.assertion)
        count = rejection_counts.get(sig, 0)
        if count < threshold:
            continue
        memory.update_candidate_status(
            cand.id,
            status="needs_review",
            decided_at=when,
            promotion_reason=(f"re-escalated: same assertion rejected {count} times previously"),
        )
        memory.append_journal(
            JournalEntry(
                id=str(uuid.uuid4()),
                timestamp=when,
                action="conflict",
                actor="rule",
                target_candidate_id=cand.id,
                note=f"re-escalated: prior_rejections={count} (threshold={threshold})",
            )
        )
        escalated.append(cand.id)
    return escalated


__all__ = [
    "DEFAULT_REJECTION_THRESHOLD",
    "DEFAULT_STALE_DAYS",
    "FallbackResult",
    "run_fallback_pass",
]
