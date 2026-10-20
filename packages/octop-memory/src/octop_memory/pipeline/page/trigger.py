"""Trigger logic for marking EntityPages dirty (D33-B — async cron).

The PromotionWorker calls :func:`mark_entity_dirty_after_promote` at the
very end of a successful atom write. That function is intentionally
zero-LLM and zero-heavy-IO — it just flips a boolean column so the
async cron worker can pick the entity up later.

Cold-entity skip (M3.3): exposed via :func:`should_regenerate` so the
CLI / cron worker can filter out pages that have already been
regenerated and don't have enough new content to be worth re-running.
The default policy is "regenerate if dirty" — the cold-skip logic is
a refinement available to the worker, not a hard gate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from octop_memory.types import EntityPage

if TYPE_CHECKING:
    from octop_memory.core import Memory


def mark_entity_dirty_after_promote(
    memory: Memory,
    entity_id: str,
    *,
    when: datetime | None = None,
) -> None:
    """Mark the page for ``entity_id`` as dirty.

    Called from :class:`PromotionWorker` immediately after a new atom
    has been persisted and the entity's atom_count has been bumped.
    Idempotent — safe to call repeatedly without changing semantics
    beyond updating ``updated_at``.

    Never raises on missing pages: ``mark_entity_page_dirty`` will
    insert a stub row if needed.
    """
    memory.mark_entity_page_dirty(entity_id, when=when or datetime.now(UTC))


def should_regenerate(
    page: EntityPage,
    *,
    max_attempt_count: int = 5,
    backoff_after_failures: int = 3,
) -> tuple[bool, str]:
    """Decide whether the cron worker should attempt this page now.

    Returns ``(True, "")`` if the page should be regenerated, otherwise
    ``(False, reason)``. Reasons:

    - ``"clean"`` — page is not dirty.
    - ``"too_many_failures"`` — page has burned past the attempt cap;
      surfaced via CLI so the user can investigate manually.
    - ``"backoff"`` — recent failures (≥ ``backoff_after_failures``)
      suggest the LLM is unhappy; we still allow eventual retries but
      let the caller skip for one tick.
    """
    if not page.dirty:
        return False, "clean"
    if page.regen_attempt_count >= max_attempt_count:
        return False, "too_many_failures"
    if page.regen_attempt_count >= backoff_after_failures:
        # Soft hint — caller may still proceed.
        return True, "backoff"
    return True, ""


__all__ = ["mark_entity_dirty_after_promote", "should_regenerate"]
