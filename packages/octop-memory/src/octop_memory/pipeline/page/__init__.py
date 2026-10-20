"""M3 EntityPage layer (D32-D37 contract).

Public surface:

- :func:`regenerate_page` / :func:`regenerate_dirty` — drive the LLM
  rewrite of one or many pages (D33-B async cron).
- :func:`mark_entity_dirty_after_promote` — PromotionWorker hook.
- :func:`extract_user_notes` / :func:`merge_user_notes` — D34-A user
  notes preservation primitives.
- :func:`truncate_headline` — D32-A 30-char hard cap helper.
- :data:`PAGE_REGEN_VERSION` — version tag persisted on journal rows.

The ``PageRegen*`` result dataclasses live alongside the regenerator.
"""

from __future__ import annotations

from octop_memory.pipeline.page.headline import HEADLINE_MAX_CHARS, coerce_headline, truncate_headline
from octop_memory.pipeline.page.prompts import PAGE_REGEN_VERSION, render_page_regen_prompt
from octop_memory.pipeline.page.regenerator import (
    DEFAULT_MAX_ATOMS_PER_REGEN,
    PageRegenBatchResult,
    PageRegenResult,
    regenerate_dirty,
    regenerate_page,
)
from octop_memory.pipeline.page.trigger import mark_entity_dirty_after_promote, should_regenerate
from octop_memory.pipeline.page.user_notes import (
    USER_NOTES_HEADING,
    detect_dropped_notes,
    extract_user_notes,
    has_user_notes,
    merge_user_notes,
)

__all__ = [
    "DEFAULT_MAX_ATOMS_PER_REGEN",
    "HEADLINE_MAX_CHARS",
    "PAGE_REGEN_VERSION",
    "USER_NOTES_HEADING",
    "PageRegenBatchResult",
    "PageRegenResult",
    "coerce_headline",
    "detect_dropped_notes",
    "extract_user_notes",
    "has_user_notes",
    "mark_entity_dirty_after_promote",
    "merge_user_notes",
    "regenerate_dirty",
    "regenerate_page",
    "render_page_regen_prompt",
    "should_regenerate",
    "truncate_headline",
]
