"""Migration utilities: export / import / rename / backfill (M5).

All paths share a single record envelope so JSONL files produced by
``memory export`` are self-describing and can be replayed by
``memory import`` against any target backend / namespace.

Envelope schema::

    {
        "v": 1,                         # bump for incompatible format changes
        "table": "raw_events",          # source table (no namespace prefix)
        "data": { ... }                 # per-table dataclass row
    }

The ``v`` field lets future imports refuse incompatible dumps cleanly.

Header line is always emitted first so the reader can validate before
streaming the bulk of the data::

    {"v": 1, "table": "__header__",
     "data": {"created_at": "...", "namespace": "...", "tool_version": "..."}}
"""

from __future__ import annotations

EXPORT_VERSION = 1
"""On-disk format version. Bump when changing the envelope or any
table's column set in a way that breaks round-trip import."""

# Tables included in a full export (in order — import respects this so
# foreign-key-like references resolve in dependency order: raw events
# before atoms-that-cite-them, entities before atoms-that-belong-to-them
# before pages-that-summarize-entities, etc.).
EXPORT_TABLES: tuple[str, ...] = (
    "raw_events",
    "candidates",
    "entities",
    "atoms",
    "aliases",
    "entity_pages",
    "thread_active_entities",
    "journal",
)

__all__ = ["EXPORT_TABLES", "EXPORT_VERSION"]
