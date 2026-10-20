"""EntityPage regenerator — turn atoms into markdown summary.

Implements the M3 D33-B / D36-A / D37-B contract:

- Pulled atoms (non-deprecated, newest first) are sent to the host LLM
  in a single prompt that requests a JSON object containing
  ``headline`` + ``summary_markdown`` + ``topics`` (D36-A).
- The newest atoms up to ``DEFAULT_MAX_ATOMS_PER_REGEN`` are sent every
  time (D37-B). Incremental-diff regeneration is not implemented.
- The user's hand-edited ``## My Notes`` block from the previous page
  is extracted before the LLM sees anything, and re-spliced into the
  freshly generated body afterwards (D34-A).
- On any failure (LLM error, malformed JSON, dropped notes) we keep
  the previous summary verbatim and increment ``regen_attempt_count``;
  the page stays ``dirty=True`` so the next cron tick retries (D35-A).

Public API:

- :func:`regenerate_page` — regenerate a single entity by id.
- :func:`regenerate_dirty` — pull all dirty pages and regenerate up to
  ``limit`` of them. Used by the ``memory page regen --dirty`` CLI.

Both functions write a journal entry (``page_regen`` or
``page_regen_failed``) per attempt so the audit trail is complete.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from octop_memory.pipeline.page.headline import coerce_headline, truncate_headline
from octop_memory.pipeline.page.prompts import PAGE_REGEN_VERSION, render_page_regen_prompt
from octop_memory.pipeline.page.user_notes import (
    detect_dropped_notes,
    extract_user_notes,
    merge_user_notes,
)
from octop_memory.ports.llm._protocol import LLMClient, LLMClientError
from octop_memory.types import AtomCard, EntityPage, JournalEntry

if TYPE_CHECKING:
    from octop_memory.core import Memory

_LOG = logging.getLogger(__name__)

# Cap on atom count per prompt; safer than blindly trusting the host
# LLM context window. Entities with more atoms get the newest N.
DEFAULT_MAX_ATOMS_PER_REGEN = 50


@dataclass
class PageRegenResult:
    """Outcome of regenerating a single page."""

    entity_id: str
    success: bool
    reason: str = ""
    headline: str = ""
    summary_markdown: str = ""
    topics: list[str] = field(default_factory=list)
    llm_calls: int = 0


@dataclass
class PageRegenBatchResult:
    """Aggregate outcome of :func:`regenerate_dirty`."""

    results: list[PageRegenResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def llm_calls(self) -> int:
        return sum(r.llm_calls for r in self.results)


# ---------------------------------------------------------------------------
# Single-page regen
# ---------------------------------------------------------------------------


def regenerate_page(
    memory: Memory,
    entity_id: str,
    *,
    llm: LLMClient,
    max_atoms: int = DEFAULT_MAX_ATOMS_PER_REGEN,
    now: datetime | None = None,
) -> PageRegenResult:
    """Regenerate the EntityPage for ``entity_id``.

    Returns a :class:`PageRegenResult` describing the outcome. Never
    raises on LLM / parse failures — those are converted to
    ``success=False`` results and recorded via
    :meth:`Memory.record_entity_page_regen_failure` + a
    ``page_regen_failed`` journal entry. Programmer errors (entity not
    found) propagate as ``ValueError``.
    """
    entity = memory.get_entity(entity_id)
    if entity is None:
        raise ValueError(f"entity {entity_id!r} not found; cannot regenerate page")

    when = now or datetime.now(UTC)
    existing = memory.get_entity_page(entity_id)
    preserved_notes = ""
    if existing is not None:
        _, preserved_notes = extract_user_notes(existing.summary_markdown)

    atoms = memory.list_atoms(
        entity_id=entity_id,
        include_deprecated=False,
        limit=max_atoms,
    )

    # Empty entity is a degenerate case — produce an empty page rather
    # than calling the LLM. Still counts as a success.
    if not atoms:
        empty_md = merge_user_notes("", preserved_notes)
        _apply_success(
            memory,
            entity_id=entity_id,
            summary_markdown=empty_md,
            headline="",
            topics=[],
            when=when,
            note=f"empty entity (no atoms); {PAGE_REGEN_VERSION}",
        )
        return PageRegenResult(
            entity_id=entity_id,
            success=True,
            reason="empty entity",
            summary_markdown=empty_md,
        )

    prompt = render_page_regen_prompt(
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        atoms_json=_atoms_to_prompt_json(atoms),
    )

    raw_output: str
    try:
        raw_output = llm.call_llm(
            prompt,
            tier="heavy",
            response_format="json",
            temperature=0.2,
        )
    except LLMClientError as exc:
        _apply_failure(
            memory,
            entity_id=entity_id,
            when=when,
            reason=f"llm_error: {exc}",
        )
        return PageRegenResult(
            entity_id=entity_id,
            success=False,
            reason=f"llm_error: {exc}",
            llm_calls=1,
        )

    try:
        parsed = _parse_regen_json(raw_output)
    except ValueError as exc:
        _LOG.warning("page regen parse failure for %s: %s", entity_id, exc)
        _apply_failure(
            memory,
            entity_id=entity_id,
            when=when,
            reason=f"parse_error: {exc}",
        )
        return PageRegenResult(
            entity_id=entity_id,
            success=False,
            reason=f"parse_error: {exc}",
            llm_calls=1,
        )

    fallback_headline = f"{entity.canonical_name}: {atoms[0].assertion}" if atoms else entity.canonical_name
    headline = coerce_headline(parsed.get("headline"), fallback=fallback_headline)
    summary_body = str(parsed.get("summary_markdown") or "").strip()
    topics = _coerce_topics(parsed.get("topics"))

    merged = merge_user_notes(summary_body, preserved_notes)

    if existing is not None and detect_dropped_notes(before=existing.summary_markdown, after=merged):
        _apply_failure(
            memory,
            entity_id=entity_id,
            when=when,
            reason="user notes dropped after merge (defensive refuse)",
        )
        return PageRegenResult(
            entity_id=entity_id,
            success=False,
            reason="user notes dropped",
            llm_calls=1,
        )

    _apply_success(
        memory,
        entity_id=entity_id,
        summary_markdown=merged,
        headline=headline,
        topics=topics,
        when=when,
        note=f"{PAGE_REGEN_VERSION}; atoms={len(atoms)}",
    )
    return PageRegenResult(
        entity_id=entity_id,
        success=True,
        reason="ok",
        headline=headline,
        summary_markdown=merged,
        topics=topics,
        llm_calls=1,
    )


# ---------------------------------------------------------------------------
# Batch regen — drives the D33-B async cron
# ---------------------------------------------------------------------------


def regenerate_dirty(
    memory: Memory,
    *,
    llm: LLMClient,
    limit: int = 20,
    max_atoms: int = DEFAULT_MAX_ATOMS_PER_REGEN,
) -> PageRegenBatchResult:
    """Pull dirty pages and regenerate up to ``limit`` of them.

    Iterates over ``memory.list_dirty_entity_pages(limit=limit)``,
    regenerating each one independently. A failure on one page does
    NOT stop the loop — the failing page stays dirty for the next
    tick, and the next page is processed.
    """
    dirty = memory.list_dirty_entity_pages(limit=limit)
    batch = PageRegenBatchResult()
    for page in dirty:
        result = regenerate_page(memory, page.entity_id, llm=llm, max_atoms=max_atoms)
        batch.results.append(result)
    return batch


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _atoms_to_prompt_json(atoms: list[AtomCard]) -> str:
    """Serialize atoms into the input shape expected by the prompt.

    We deliberately strip fields the LLM doesn't need (entity_id,
    candidate_id, deprecated_at, …) to keep the prompt compact and to
    avoid leaking ids the LLM might hallucinate back at us.
    """
    payload = [
        {
            "id": a.id[:12],  # shorthand id is enough for citation
            "assertion": a.assertion,
            "verbatim_quote": a.verbatim_quote,
            "importance": a.importance,
            "confidence": a.confidence,
            "occurred_at": a.occurred_at.isoformat(),
        }
        for a in atoms
    ]
    return json.dumps(payload, ensure_ascii=False)


def _parse_regen_json(raw: str) -> dict[str, Any]:
    """Parse the LLM's JSON output, tolerating common wrappers.

    Strips markdown code fences if the model ignored the "no fences"
    rule. Raises ``ValueError`` with a short reason on any failure.
    """
    if not raw or not raw.strip():
        raise ValueError("empty LLM output")

    text = raw.strip()
    # Strip markdown fences if present.
    if text.startswith("```"):
        # Drop opening fence (``` or ```json) and closing fence.
        lines = text.splitlines()
        if lines:
            lines = lines[1:]  # drop opening
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")

    return parsed


def _coerce_topics(value: Any) -> list[str]:
    """Normalize the LLM-emitted ``topics`` field into a clean list."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned[:64])
    return out[:5]  # cap at 5 — see prompt rule 4


def _apply_success(
    memory: Memory,
    *,
    entity_id: str,
    summary_markdown: str,
    headline: str,
    topics: list[str],
    when: datetime,
    note: str,
) -> None:
    # Mutating call sequence: page row first (so a journal-only orphan is
    # impossible), then journal append.
    headline_clamped = truncate_headline(headline)
    updated = memory.apply_entity_page_regen(
        entity_id,
        summary_markdown=summary_markdown,
        headline=headline_clamped,
        topics=topics,
        when=when,
    )
    if not updated:
        # Page row was missing (race vs. delete or migration gap):
        # upsert a fresh row to recover gracefully.
        memory.upsert_entity_page(
            EntityPage(
                id=f"page_{entity_id}",
                entity_id=entity_id,
                summary_markdown=summary_markdown,
                headline=headline_clamped,
                topics=topics,
                dirty=False,
                regen_attempt_count=0,
                summary_version=1,
                last_regen_at=when,
                last_user_edit_at=None,
                created_at=when,
                updated_at=when,
            )
        )
    memory.append_journal(
        JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=when,
            action="page_regen",
            actor="auto",
            target_entity_id=entity_id,
            note=note,
        )
    )


def _apply_failure(
    memory: Memory,
    *,
    entity_id: str,
    when: datetime,
    reason: str,
) -> None:
    memory.record_entity_page_regen_failure(entity_id, when=when)
    memory.append_journal(
        JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=when,
            action="page_regen_failed",
            actor="auto",
            target_entity_id=entity_id,
            note=reason,
        )
    )


__all__ = [
    "DEFAULT_MAX_ATOMS_PER_REGEN",
    "PageRegenBatchResult",
    "PageRegenResult",
    "regenerate_dirty",
    "regenerate_page",
]
