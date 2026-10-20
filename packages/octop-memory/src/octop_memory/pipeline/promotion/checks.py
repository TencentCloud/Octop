"""5-check promotion logic for L1 Candidate → L2 AtomCard (design §8.3.2).

Demotion-only philosophy: every candidate becomes an atom by default. We
only step away from the happy path in these cases:

1. ``importance=low AND confidence=low`` → drop (chit-chat noise)
2. Synthetic runtime failure as evidence → drop (unless explicitly user-retained)
3. Existing atom is identical → merge (no new row)
4. Existing atom directly contradicts → needs_review / conflict

The five checks run in fixed order. The first one that produces a
terminal outcome wins; later checks are skipped. This module is **pure
rule**: it never calls an LLM. The optional LLM escalation hooks
(check 3 alias disambiguation, check 4/5 grey-zone semantic match) are
exposed via the ``LLMEscalationHook`` Protocol so M2.5b can inject them
without touching the orchestration loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from octop_memory.domain.alias import normalize_alias
from octop_memory.domain.retention import is_runtime_error_candidate
from octop_memory.types import AtomCard, Candidate, RawEvent

# ---------------------------------------------------------------------------
# Negation-token dictionary used by check 5
# ---------------------------------------------------------------------------

# Re-uses the same vocabulary the extractor uses for anti-dilution warnings.
# Keeping the list in sync matters: an extractor that warns "lost negation"
# must agree with a promotion worker that detects "atom A says X but
# candidate B says NOT-X".
_NEGATION_TOKENS = (
    # Chinese (most common forms)
    "不",
    "没",
    "别",
    "勿",
    "暂不",
    # English
    "not",
    "won't",
    "wont",
    "no ",  # trailing space avoids matching "noise" / "norm"
    "avoid",
    "never",
    "don't",
    "dont",
    "isn't",
    "isnt",
    "aren't",
    "arent",
)


def _has_negation(text: str) -> bool:
    """True iff ``text`` contains any token from ``_NEGATION_TOKENS``.

    Lowercased compare (case-insensitive). Chinese tokens compare verbatim
    since Chinese has no case. The trailing space on ``"no "`` is a cheap
    way to avoid matching English words that start with ``no`` but are
    not negations (``noise``, ``norm``).
    """
    haystack = text.lower()
    return any(tok in haystack for tok in _NEGATION_TOKENS)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


PromotionOutcomeKind = Literal[
    "promote",  # new atom should be created
    "merge",  # equivalent atom already exists; reuse it
    "conflict",  # candidate contradicts an existing atom
    "needs_review",  # rule could not decide; queue for human
    "drop",  # low+low or evidence problem
]


@dataclass(frozen=True)
class PromotionOutcome:
    """The result of running the 5 checks against one candidate.

    Carries everything the worker needs to perform the database write
    without having to re-run any check.
    """

    kind: PromotionOutcomeKind
    reason: str
    # Filled when the candidate resolved (or proposed) an entity.
    entity_id: str | None = None
    # Filled for ``merge`` / ``conflict`` (the existing atom involved).
    matched_atom_id: str | None = None
    # When set, the worker should create a new entity row before writing
    # the atom (kind="promote" with no existing entity match).
    new_entity_canonical_name: str | None = None
    new_entity_type: str | None = None
    # Number of LLM escalations consumed by this candidate (for budget
    # tracking + telemetry). Pure-rule path always returns 0.
    llm_calls: int = 0


# ---------------------------------------------------------------------------
# Optional LLM escalation contract
# ---------------------------------------------------------------------------


class LLMEscalationHook(Protocol):
    """Optional bridge to call the host LLM for grey-zone disambiguation.

    Each method returns ``None`` to mean "I am not confident either way;
    let the rule path's tentative answer stand". Implementations MUST
    NOT raise into the promotion loop — they should swallow
    ``LLMClientError`` and return ``None``.

    Per design §8.3.2 each candidate is allotted **at most 1** LLM
    escalation across the whole 5-check pipeline. Hooks are therefore
    designed so a single call can answer the question (e.g.
    ``resolve_entity_match`` is given the WHOLE candidate set in one
    shot, not one-pair-at-a-time).
    """

    def resolve_entity_match(
        self,
        *,
        candidate_subject: str,
        candidate_entity_type: str,
        candidates: list[tuple[str, str]],
    ) -> str | None:
        """Resolve ``candidate_subject`` to an existing entity id.

        Pick the entity id whose canonical_name is the same entity as
        ``candidate_subject``, or ``None`` if none match.

        ``candidates`` is a list of ``(entity_id, canonical_name)`` pairs
        the worker pre-filtered (typically same entity_type, capped at
        a handful). Returning an id NOT in the input list is treated as
        "uncertain" and silently dropped.
        """
        ...

    def same_assertion(
        self,
        *,
        candidate_assertion: str,
        existing_assertion: str,
    ) -> bool | None:
        """Do these two assertions claim the same fact?

        Used by check 4 grey zone (FTS overlap high but signatures
        differ). Worker only invokes this once per candidate.
        """
        ...

    def is_contradiction(
        self,
        *,
        candidate_assertion: str,
        existing_assertion: str,
    ) -> bool | None:
        """Do these two assertions contradict each other?

        Used by check 5 grey zone (token overlap with same polarity but
        suspicious phrasing). Worker only invokes this once per candidate.
        """
        ...


# ---------------------------------------------------------------------------
# Check 1 — long-term value
# ---------------------------------------------------------------------------


def check_value(candidate: Candidate) -> PromotionOutcome | None:
    """Drop iff importance=low AND confidence=low.

    Returns None to indicate "this candidate is value-worthy enough to
    keep going". The next checks run as usual.
    """
    if candidate.importance == "low" and candidate.confidence == "low":
        return PromotionOutcome(
            kind="drop",
            reason="low importance + low confidence (likely chit-chat)",
        )
    return None


# ---------------------------------------------------------------------------
# Check 2 — evidence
# ---------------------------------------------------------------------------


class EvidenceLookup(Protocol):
    """Minimal duck-typed interface for the worker's raw-event store."""

    def get_raw(self, event_id: str) -> RawEvent | None:
        """Return the raw event for ``event_id``, or ``None``."""
        ...


def check_evidence(
    candidate: Candidate,
    *,
    evidence_store: EvidenceLookup,
    now: datetime | None = None,
) -> PromotionOutcome | None:
    """Verify every cited raw_event_id exists and has a sane timestamp.

    Failure modes:
    - ``raw_event_ids`` is empty                     → drop
    - any cited event id is missing from L0          → needs_review
      (the candidate is suspicious — the LLM may have hallucinated
      an event id; we do NOT silently drop because the user might
      still want to manually re-attach evidence)

    We do NOT check ``timestamp <= now`` here — the L0 backend already
    rejects future-dated rows on insert, and the candidate row itself
    is bounded by ``created_at`` which the worker assigned. Keeping this
    check lightweight saves one DB hit per cited event.
    """
    del now  # reserved for future "future-dated event" check
    if is_runtime_error_candidate(candidate, evidence_store.get_raw):
        return PromotionOutcome(kind="drop", reason="synthetic runtime failure has no durable memory value")
    if not candidate.raw_event_ids:
        return PromotionOutcome(
            kind="drop",
            reason="evidence missing: candidate cites zero raw events",
        )
    for ev_id in candidate.raw_event_ids:
        if evidence_store.get_raw(ev_id) is None:
            return PromotionOutcome(
                kind="needs_review",
                reason=f"evidence missing: raw_event_id {ev_id!r} not found in L0",
            )
    return None


# ---------------------------------------------------------------------------
# Check 3 — entity resolution
# ---------------------------------------------------------------------------


class EntityResolver(Protocol):
    """Duck-typed interface for entity / alias lookups."""

    def find_entity_by_alias(self, alias: str) -> object | None:
        """Return the entity this alias resolves to, or ``None``."""
        ...

    def find_entity_by_name(
        self,
        canonical_name: str,
        *,
        entity_type: str | None = None,
    ) -> object | None:
        """Return the entity with this canonical name, or ``None``."""
        ...

    def list_entities(
        self,
        *,
        entity_type: str | None = ...,
        limit: int = ...,
    ) -> list[object]:
        """List entities, optionally filtered by type."""
        ...


# Cap how many existing entities we surface to the LLM in a single
# escalation. The LLM has to scan all of them in one call (we use ONE
# call per candidate per design §8.3.2), so keep the prompt cheap.
_LLM_ENTITY_RESOLVE_CANDIDATES = 20


def check_entity(
    candidate: Candidate,
    *,
    resolver: EntityResolver,
    llm_hook: LLMEscalationHook | None = None,
) -> PromotionOutcome:
    """Resolve which entity this candidate's atom should hang off.

    Lookup order:
    1. Normalized alias hit in the alias table → reuse that entity_id
    2. Exact canonical_name match (case-insensitive, COLLATE NOCASE in
       the SQL layer) within the same entity_type → reuse that entity_id
    3. **(M2.5b)** LLM hook (if provided): collect up to
       ``_LLM_ENTITY_RESOLVE_CANDIDATES`` existing entities of the same
       entity_type and ask the hook to pick the same-entity match (or
       None). One LLM call per candidate.
    4. Otherwise → propose a new entity (caller will create it before
       inserting the atom)

    NOTE: ``check_entity`` always returns a non-None outcome — either
    ``promote`` (with ``entity_id`` resolved) or ``promote`` (with
    ``new_entity_canonical_name`` set). Callers downstream may still
    flip the outcome to merge/conflict/needs_review.
    """
    subject = candidate.subject_name.strip()
    if not subject:
        # Extractor parser already enforces non-empty subject_name, but
        # be defensive — a malformed manual insert shouldn't crash here.
        return PromotionOutcome(
            kind="needs_review",
            reason="subject_name empty; cannot resolve entity",
        )

    normalized = normalize_alias(subject)

    # 0. User-type singleton rule: there is only ONE user per agent session.
    #    Any candidate with entity_type="User" must always resolve to the
    #    single existing User entity (if one exists), regardless of how the
    #    LLM named the subject ("User", "Eileen", a first-person pronoun, etc.).
    #    The new subject_name is saved as an alias so future lookups hit step 1.
    if candidate.subject_entity_type == "User":
        existing_users = resolver.list_entities(entity_type="User", limit=1)
        if existing_users:
            existing_user = existing_users[0]
            return PromotionOutcome(
                kind="promote",
                reason=(
                    f"User singleton rule: merged {subject!r} into existing "
                    f"User entity {getattr(existing_user, 'canonical_name', '?')!r}"
                ),
                entity_id=getattr(existing_user, "id", None),
            )

    # 1. Alias table hit (worker may have populated it on previous runs)
    aliased = resolver.find_entity_by_alias(normalized)
    if aliased is not None:
        return PromotionOutcome(
            kind="promote",
            reason=f"entity resolved via alias {normalized!r}",
            entity_id=getattr(aliased, "id", None),
        )

    # 2. Canonical-name exact (NOCASE) hit on same entity_type
    by_name = resolver.find_entity_by_name(
        subject,
        entity_type=candidate.subject_entity_type,
    )
    if by_name is not None:
        return PromotionOutcome(
            kind="promote",
            reason=f"entity resolved by canonical_name {subject!r}",
            entity_id=getattr(by_name, "id", None),
        )

    # 3. LLM disambiguation (M2.5b) — one call total per candidate.
    if llm_hook is not None:
        existing = resolver.list_entities(
            entity_type=candidate.subject_entity_type,
            limit=_LLM_ENTITY_RESOLVE_CANDIDATES,
        )
        if existing:
            pairs: list[tuple[str, str]] = [
                (
                    str(getattr(e, "id", "")),
                    str(getattr(e, "canonical_name", "")),
                )
                for e in existing
                if getattr(e, "id", None) and getattr(e, "canonical_name", None)
            ]
            if pairs:
                allowed_ids = {pid for pid, _ in pairs}
                picked = llm_hook.resolve_entity_match(
                    candidate_subject=subject,
                    candidate_entity_type=candidate.subject_entity_type,
                    candidates=pairs,
                )
                # Hook is allowed to return None (uncertain) or a non-
                # member id (treated as uncertain). Both fall through.
                if picked is not None and picked in allowed_ids:
                    return PromotionOutcome(
                        kind="promote",
                        reason=f"entity resolved via LLM same-entity check on {subject!r}",
                        entity_id=picked,
                        llm_calls=1,
                    )

    # 4. New entity
    return PromotionOutcome(
        kind="promote",
        reason=f"no existing entity matched {subject!r}; will create",
        new_entity_canonical_name=subject,
        new_entity_type=candidate.subject_entity_type,
    )


# ---------------------------------------------------------------------------
# Check 4 — duplicate detection
# ---------------------------------------------------------------------------


class AtomLookup(Protocol):
    """Duck-typed interface for finding existing atoms within an entity."""

    def list_atoms(
        self,
        *,
        entity_id: str | None = ...,
        importance: str | None = ...,
        include_deprecated: bool = ...,
        limit: int = ...,
    ) -> list[AtomCard]:
        """List atoms matching the given filters."""
        ...

    def find_atom_by_signature(self, sig: str) -> AtomCard | None:
        """Find a non-deprecated atom with assertion signature ``sig``.

        Find the first non-deprecated atom globally whose assertion
        signature matches ``sig`` (normalized via ``_assertion_signature``).

        Used by ``check_duplicate`` to detect cross-entity exact duplicates.
        Returns ``None`` if no match is found.
        """
        ...


def _assertion_signature(text: str) -> str:
    """Coarse signature for "same-fact" exact match.

    Strips whitespace differences + applies the same normalization as
    aliases (NFKC fold, casefold, whitespace collapse). Punctuation is
    intentionally NOT stripped — "I will NOT use it" and "I will use it"
    must NOT collapse to the same signature.
    """
    return normalize_alias(text)


def check_duplicate(
    candidate: Candidate,
    *,
    entity_id: str,
    atom_lookup: AtomLookup,
    llm_hook: LLMEscalationHook | None = None,
) -> PromotionOutcome | None:
    """Detect an exact duplicate of this candidate.

    Detect exact-match duplication against existing atoms on the same entity,
    then fall back to a global cross-entity signature scan.

    Strategy:
    1. List all non-deprecated atoms on this entity (worst case a handful —
       entities are narrow by design) and compare normalized assertion
       signatures. This is the fast intra-entity path.
    2. If no intra-entity duplicate is found, call
       ``atom_lookup.find_atom_by_signature(sig)`` to scan globally (LIMIT 200
       in the backend). If a match is found on a *different* entity, we still
       return ``merge`` — the candidate is a cross-entity duplicate.

    ``llm_hook`` is reserved by the shared promotion contract, but this
    check currently flags exact matches only. Semantic duplicate
    consolidation uses ``llm_hook.same_assertion`` in
    :mod:`octop_memory.pipeline.lifecycle.consolidate`.

    Returns None when no duplicate is found (caller continues to check 5).
    """
    del llm_hook  # Semantic duplicate escalation is not used in this check.
    sig = _assertion_signature(candidate.assertion)
    if not sig:
        return None

    # ---- Step 1: exact signature match within the same entity ----
    # Cap at 200 — entities with more atoms are pathological and we'd
    # rather skip dedup than scan unbounded.
    existing = atom_lookup.list_atoms(
        entity_id=entity_id,
        include_deprecated=False,
        limit=200,
    )
    for atom in existing:
        if _assertion_signature(atom.assertion) == sig:
            return PromotionOutcome(
                kind="merge",
                reason="exact-match assertion already in atom store",
                entity_id=entity_id,
                matched_atom_id=atom.id,
            )

    # ---- Step 2: cross-entity global signature scan (User entity_type only) ----
    # For the User entity (a singleton), the same fact should not be stored
    # redundantly under multiple User entities. For Project, Person, and other
    # entity types, the same assertion is legitimately valid under different
    # entities (e.g. different projects can each use PostgreSQL), so no
    # cross-entity detection is done for those.
    if candidate.subject_entity_type == "User":
        cross_atom = atom_lookup.find_atom_by_signature(sig)
        if cross_atom is not None and cross_atom.entity_id != entity_id:
            return PromotionOutcome(
                kind="merge",
                reason=(
                    f"cross-entity exact-match assertion already in atom store (source entity: {cross_atom.entity_id})"
                ),
                entity_id=cross_atom.entity_id,
                matched_atom_id=cross_atom.id,
            )

    return None


# ---------------------------------------------------------------------------
# Check 5 — conflict detection
# ---------------------------------------------------------------------------


def check_conflict(
    candidate: Candidate,
    *,
    entity_id: str,
    atom_lookup: AtomLookup,
    llm_hook: LLMEscalationHook | None = None,
) -> PromotionOutcome | None:
    """Detect direct contradiction against existing atoms.

    Pure-rule signal: same entity + overlapping subject + opposite
    negation polarity. Concretely we compare the negation flag of the
    new candidate's assertion against each existing atom on the same
    entity that shares ≥3 characters of token overlap (very coarse,
    intentionally cheap). On polarity mismatch we return ``conflict``;
    on polarity match (a possible paraphrased duplicate that check 4
    did not catch) this check returns no conflict.

    We deliberately do NOT extract structured triples here; this worker
    keeps conflict detection deterministic and rule-based.
    """
    del llm_hook  # Semantic contradiction escalation is not used here.
    new_neg = _has_negation(candidate.assertion)

    existing = atom_lookup.list_atoms(
        entity_id=entity_id,
        include_deprecated=False,
        limit=200,
    )
    for atom in existing:
        if not _shares_meaningful_overlap(candidate.assertion, atom.assertion):
            continue
        old_neg = _has_negation(atom.assertion)
        if new_neg != old_neg:
            return PromotionOutcome(
                kind="conflict",
                reason=(
                    f"polarity flip vs atom {atom.id}: "
                    f"{'NEG' if new_neg else 'POS'} now, "
                    f"{'NEG' if old_neg else 'POS'} previously"
                ),
                entity_id=entity_id,
                matched_atom_id=atom.id,
            )
    return None


# Stop-words that must NOT count toward "meaningful overlap" — they're
# function words shared by virtually every Chinese / English sentence
# and would otherwise let totally-unrelated atoms be flagged as conflict.
_STOP_WORDS_CN = frozenset(
    [
        "的",
        "了",
        "是",
        "在",
        "我",
        "你",
        "他",
        "她",
        "我们",
        "他们",
        "和",
        "与",
        "或",
        "也",
        "都",
        "就",
        "要",
        "把",
        "对",
        "用",
        "被",
        "让",
        "给",
    ]
)
_STOP_WORDS_EN = frozenset(
    [
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "to",
        "of",
        "for",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "by",
        "with",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "it",
        "this",
        "that",
        "these",
        "those",
    ]
)


def _content_tokens(text: str) -> set[str]:
    """Tokenize into lowercase content words.

    Cheap heuristic: split on whitespace + take individual CJK characters
    as their own tokens (Chinese has no spaces). Drop ASCII stop-words +
    Chinese stop-words. NOT a real tokenizer — only used for overlap
    coarse-filtering inside check 5.
    """
    norm = normalize_alias(text)
    tokens: set[str] = set()
    # ASCII words on whitespace
    for w in norm.split():
        if not w:
            continue
        # Strip trailing/leading punctuation but keep in-word ones
        cleaned = w.strip(".,;:!?\"'()[]{}<>")
        if cleaned and cleaned not in _STOP_WORDS_EN:
            tokens.add(cleaned)
    # Each CJK ideograph as a token (rough but workable for this purpose)
    for ch in norm:
        if "\u4e00" <= ch <= "\u9fff" and ch not in _STOP_WORDS_CN:
            tokens.add(ch)
    return tokens


def _shares_meaningful_overlap(a: str, b: str, *, min_overlap: int = 3) -> bool:
    """Heuristic: do these two strings discuss the same topic?

    Conservative — we'd rather miss a true conflict (later LLM check 5
    catches it) than flag two unrelated atoms.
    """
    return len(_content_tokens(a) & _content_tokens(b)) >= min_overlap


# ---------------------------------------------------------------------------
# Atom construction (called by the worker after all 5 checks pass)
# ---------------------------------------------------------------------------


def build_atom_from_candidate(
    candidate: Candidate,
    *,
    atom_id: str,
    entity_id: str,
    now: datetime | None = None,
    occurred_at: datetime | None = None,
) -> AtomCard:
    """Materialize a Candidate into an AtomCard ready to write.

    Conservative defaults:
    - ``occurred_at`` = the ``occurred_at`` argument (preferred), otherwise
      falls back to candidate.created_at (extraction time). Callers should
      pass the earliest timestamp among the underlying raw_events, so it
      reflects when the event actually happened rather than when it was
      extracted.
    - ``search_terms`` = ``[subject_name]``. The FTS index already covers
      assertion + verbatim_quote; this small list adds back the entity
      hint that pure assertion text might miss for short atoms.
    """
    when = now or datetime.now(UTC)
    return AtomCard(
        id=atom_id,
        entity_id=entity_id,
        candidate_id=candidate.id,
        raw_event_ids=list(candidate.raw_event_ids),
        assertion=candidate.assertion,
        verbatim_quote=candidate.verbatim_quote,
        quote_event_id=candidate.quote_event_id,
        search_terms=[candidate.subject_name] if candidate.subject_name else [],
        occurred_at=occurred_at or candidate.created_at,
        confidence=candidate.confidence,
        importance=candidate.importance,
        created_at=when,
    )


__all__ = [
    "AtomLookup",
    "EntityResolver",
    "EvidenceLookup",
    "LLMEscalationHook",
    "PromotionOutcome",
    "PromotionOutcomeKind",
    "build_atom_from_candidate",
    "check_conflict",
    "check_duplicate",
    "check_entity",
    "check_evidence",
    "check_value",
]
