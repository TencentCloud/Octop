"""Source-based retention rules shared by capture, extraction and recall.

401/timeout keywords do not identify a source: users may discuss these normally.
Only an explicit host marker identifies synthetic output.
User/manual events always remain eligible, even when they quote that envelope.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable

from octop_memory.types import Candidate, RawEvent

MANUAL_DOCUMENTS_META_KEY = "manual_documents/v1"
MANUAL_DOCUMENTS_RECALL_KEY = "manual_documents/recall/v1"


def manual_documents_revision(documents: dict[str, str]) -> str:
    """Revision of the two authoritative documents, including absent files."""
    canonical = {name: documents.get(name, "") for name in ("USER.md", "MEMORY.md")}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_manual_fact(text: str) -> str:
    """Remove Markdown bullet/formatting whitespace while preserving factual values."""
    text = re.sub(r"^\s*[-+*]\s+", "", text)
    return " ".join(text.replace("**", "").replace("`", "").split())


def is_runtime_error(event: RawEvent) -> bool:
    """Identify synthetic assistant failures without filtering user error reports."""
    if event.event_type != "assistant_message" or event.payload.get("role") == "user":
        return False
    return event.payload.get("octop_runtime_error") is True


def is_runtime_error_candidate(candidate: Candidate, get_raw: Callable[[str], RawEvent | None]) -> bool:
    """True only for automatic candidates demonstrably based on runtime failures.

    User approvals and manual saves are protected by provenance, never phrases.
    Every cited source must be explicitly marked; mixed, missing or unmarked
    evidence is ineligible for automatic retirement.
    """
    if candidate.decided_by == "user" or candidate.extractor_version.startswith("manual/"):
        return False
    events = {key: get_raw(key) for key in set([*candidate.raw_event_ids, candidate.quote_event_id]) if key}
    return bool(events) and all(event is not None and is_runtime_error(event) for event in events.values())
