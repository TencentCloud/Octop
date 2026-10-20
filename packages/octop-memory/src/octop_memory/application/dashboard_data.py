"""Dashboard-only JSON-RPC handlers.

This module exposes read/write RPCs powering the orca dashboard
``Agent/Memory`` views. They are intentionally split from
``handlers.py`` because:

* The recall / capture / extract surface is **agent-facing** — speed
  and JSON shape are stable contracts with the OpenClaw TS shell.
* The dashboard surface is **human-facing** — broader filters, joins
  across layers (Atom ↔ Candidate for ``kind`` chips), and tolerant
  defaults that prefer "show something" over strict validation.

All handlers follow the same shape as ``Bridge`` methods:

    (params: dict[str, Any]) -> dict[str, Any]

so they can be attached straight into ``Bridge._dispatch`` and reuse
``Bridge.handle``'s exception → JSON-RPC translation. Heavy filtering
that ``Memory`` doesn't natively support (``kind`` join, ``query``
substring match, ``intensity_min`` / ``topic`` for episodes) is done
in Python after fetching a wider window — acceptable for an MVP
dashboard that runs against per-agent SQLite stores in the low
thousands of rows.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from octop_memory.domain.datetime import as_utc
from octop_memory.types import (
    AtomCard,
    JournalEntry,
)

if TYPE_CHECKING:
    from octop_memory.core import Memory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Param coercion helpers
# ---------------------------------------------------------------------------


def _opt_str(params: dict[str, Any], key: str) -> str | None:
    """Return ``params[key]`` if it's a non-empty string, else ``None``.

    Tolerant: blank strings collapse to ``None`` so the frontend can
    pass back empty filter slots without us interpreting them as
    ``status=''``.
    """
    val = params.get(key)
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip() or None
    raise ValueError(f"{key!r}: must be a string or null")


def _opt_int(params: dict[str, Any], key: str, *, minimum: int | None = None) -> int | None:
    val = params.get(key)
    if val is None or val == "":
        return None
    try:
        ivalue = int(val)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key!r}: must be an integer, got {val!r}") from exc
    if minimum is not None and ivalue < minimum:
        raise ValueError(f"{key!r}: must be >= {minimum}, got {ivalue}")
    return ivalue


def _opt_iso(params: dict[str, Any], key: str) -> datetime | None:
    val = params.get(key)
    if val is None or val == "":
        return None
    if isinstance(val, str):
        try:
            return as_utc(datetime.fromisoformat(val))
        except ValueError as exc:
            raise ValueError(f"{key!r}: invalid ISO 8601 datetime: {val!r}") from exc
    raise ValueError(f"{key!r}: must be an ISO 8601 string")


def _limit(params: dict[str, Any], default: int = 50, *, cap: int = 500) -> int:
    """Clamp ``params['limit']`` into ``[1, cap]`` with a sensible default."""
    val = _opt_int(params, "limit", minimum=1)
    if val is None:
        return default
    return min(val, cap)


def _offset(params: dict[str, Any]) -> int:
    val = _opt_int(params, "offset", minimum=0)
    return val or 0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _isoformat(value: Any) -> Any:
    """Recursively turn ``datetime`` into ISO 8601, leave others alone."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_isoformat(v) for v in value]
    if isinstance(value, dict):
        return {k: _isoformat(v) for k, v in value.items()}
    return value


def _to_jsonable(obj: Any) -> Any:
    """Convert a dataclass (or list / nested dict thereof) to JSON-safe dict.

    Uses ``dataclasses.asdict`` so we always get a deep copy (the caller
    can safely mutate without disturbing the cached row).
    """
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_to_jsonable(item) for item in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return _isoformat(asdict(obj))
    return _isoformat(obj)


def _paginate(items: list[Any], offset: int, limit: int) -> tuple[list[Any], int, bool]:
    """Slice a Python list into a (window, total_seen, has_more) tuple.

    ``total_seen`` is just ``len(items)`` — the caller already fetched
    a wide window from SQLite, so this is a true count of what we
    surveyed (NOT the count of all rows in the table). The frontend
    treats it as "≥ N", which is good enough for paging UI.
    """
    total = len(items)
    window = items[offset : offset + limit]
    has_more = offset + limit < total
    return window, total, has_more


# ---------------------------------------------------------------------------
# In-memory join helpers (Atom ↔ Candidate.candidate_type)
# ---------------------------------------------------------------------------


_IMPORTANCE_RANK = {"low": 1, "medium": 2, "high": 3}
"""Rank used for ``importance_min`` filtering: only atoms whose rank
is ≥ the supplied minimum survive."""


def _atom_kind(memory: Memory, atom: AtomCard, cache: dict[str, str | None]) -> str | None:
    """Resolve the ``candidate_type`` (acting as ``kind``) for an atom.

    AtomCard has no ``kind`` column — the type lives on the upstream
    Candidate row. We cache per request so a 50-atom page only runs
    50 candidate lookups regardless of how many filters we run on top.
    """
    cid = atom.candidate_id
    if cid in cache:
        return cache[cid]
    cand = memory.get_candidate(cid)
    kind = cand.candidate_type if cand else None
    cache[cid] = kind
    return kind


def _matches_query(text_fragments: list[str], query: str | None) -> bool:
    if not query:
        return True
    needle = query.lower()
    return any(needle in (fragment or "").lower() for fragment in text_fragments)


# ---------------------------------------------------------------------------
# RPC: list_atoms
# ---------------------------------------------------------------------------


def list_atoms(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """List atoms with rich filters (kind / importance_min / query).

    Params (all optional unless noted)::

        entity_id?: str
        candidate_type?: "Fact" | "Decision" | "Task" | "Preference" | "ConflictCandidate"
        importance_min?: "low" | "medium" | "high"
        include_deprecated?: bool      (default false)
        query?: str                    (substring over assertion + verbatim_quote + search_terms)
        order_by?: "created_at" | "occurred_at" | "importance"   (default "created_at")
        order?: "asc" | "desc"          (default "desc")
        offset?: int                    (default 0)
        limit?: int                     (default 50, cap 500)

    Returns ``{items, total, has_more}`` where ``items`` are
    JSON-serializable AtomCard dicts (datetime → ISO 8601).
    """
    entity_id = _opt_str(params, "entity_id")
    candidate_type = _opt_str(params, "candidate_type")
    importance_min = _opt_str(params, "importance_min")
    include_deprecated = bool(params.get("include_deprecated", False))
    query = _opt_str(params, "query")
    order_by = _opt_str(params, "order_by") or "created_at"
    order = (_opt_str(params, "order") or "desc").lower()
    if order not in {"asc", "desc"}:
        raise ValueError("'order': must be 'asc' or 'desc'")
    if order_by not in {"created_at", "occurred_at", "importance"}:
        raise ValueError("'order_by': must be 'created_at' / 'occurred_at' / 'importance'")
    offset = _offset(params)
    limit = _limit(params)

    # Pull a wide window — Memory.list_atoms doesn't paginate yet, and
    # for MVP the per-agent atom count is in the low thousands. We
    # filter / sort in Python.
    atoms = memory.list_atoms(
        entity_id=entity_id,
        importance=None,  # we filter via importance_min below
        include_deprecated=include_deprecated,
        limit=10_000,
    )

    kind_cache: dict[str, str | None] = {}

    if importance_min is not None:
        threshold = _IMPORTANCE_RANK.get(importance_min)
        if threshold is None:
            raise ValueError("'importance_min': must be 'low' / 'medium' / 'high'")
        atoms = [a for a in atoms if _IMPORTANCE_RANK.get(a.importance, 0) >= threshold]

    if candidate_type is not None:
        atoms = [a for a in atoms if _atom_kind(memory, a, kind_cache) == candidate_type]

    if query is not None:
        atoms = [
            a
            for a in atoms
            if _matches_query(
                [a.assertion, a.verbatim_quote, " ".join(a.search_terms or [])],
                query,
            )
        ]

    # Stable, deterministic ordering:
    reverse = order == "desc"
    if order_by == "importance":
        atoms.sort(
            key=lambda a: (
                _IMPORTANCE_RANK.get(a.importance, 0),
                a.created_at,
            ),
            reverse=reverse,
        )
    elif order_by == "occurred_at":
        atoms.sort(key=lambda a: a.occurred_at, reverse=reverse)
    else:
        atoms.sort(key=lambda a: a.created_at, reverse=reverse)

    window, total, has_more = _paginate(atoms, offset, limit)

    # Enrich each atom with its kind so the frontend doesn't need a
    # second roundtrip for the chip rendering.
    out: list[dict[str, Any]] = []
    for atom in window:
        payload = _to_jsonable(atom)
        payload["kind"] = _atom_kind(memory, atom, kind_cache)
        out.append(payload)

    return {"items": out, "total": total, "has_more": has_more}


# ---------------------------------------------------------------------------
# RPC: list_raw_events
# ---------------------------------------------------------------------------


_RAW_EVENT_TYPES = {
    "user_message",
    "assistant_message",
    "tool_call",
    "tool_result",
    "host_memory_write",
    "session_start",
    "session_end",
    "compaction",
    "manual",
}


def list_raw_events(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """List L0 raw events — the captured conversation material.

    L0 is the evidence layer the distillation pipeline reads. Surfacing
    it lets users see that material is being captured even before atoms
    have been distilled.

    Params (all optional)::

        session_id?: str
        thread_id?: str
        event_type?: one of RawEventType
        query?: str                    (substring over content)
        offset?: int                   (default 0)
        limit?: int                    (default 50, cap 500)

    Returns ``{items, total, has_more}`` where ``items`` are
    JSON-serializable RawEvent dicts ordered by timestamp DESC.
    """
    session_id = _opt_str(params, "session_id")
    thread_id = _opt_str(params, "thread_id")
    event_type = _opt_str(params, "event_type")
    query = _opt_str(params, "query")
    offset = _offset(params)
    limit = _limit(params)

    if event_type is not None and event_type not in _RAW_EVENT_TYPES:
        raise ValueError("'event_type': not a valid raw event type")

    # Memory.list_raw already orders by timestamp DESC and pushes the
    # structured filters into SQL; we pull a wide window and do the
    # substring ``query`` filter in Python (content isn't indexed here
    # — recall's FTS path is the searchable surface).
    events = memory.list_raw(
        session_id=session_id,
        thread_id=thread_id,
        event_type=event_type,  # type: ignore[arg-type]
        limit=10_000,
    )

    if query is not None:
        events = [e for e in events if _matches_query([e.content], query)]

    window, total, has_more = _paginate(events, offset, limit)
    return {"items": [_to_jsonable(e) for e in window], "total": total, "has_more": has_more}


# ---------------------------------------------------------------------------
# RPC: list_entities
# ---------------------------------------------------------------------------


def list_entities(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """List entities with optional ``entity_type`` / ``query`` filters.

    Params::

        entity_type?: "User" | "Person" | "Project" | "Decision" | "Task" | "Fact"
        query?: str        (substring over canonical_name + aliases)
        order_by?: "atom_count" | "canonical_name" | "last_promoted_at"
        order?: "asc" | "desc"
        offset?: int
        limit?: int

    Returns ``{items, total, has_more}``.
    """
    entity_type = _opt_str(params, "entity_type")
    query = _opt_str(params, "query")
    order_by = _opt_str(params, "order_by") or "atom_count"
    order = (_opt_str(params, "order") or "desc").lower()
    if order not in {"asc", "desc"}:
        raise ValueError("'order': must be 'asc' or 'desc'")
    if order_by not in {"atom_count", "canonical_name", "last_promoted_at"}:
        raise ValueError("'order_by': must be 'atom_count' / 'canonical_name' / 'last_promoted_at'")
    offset = _offset(params)
    limit = _limit(params)

    entities = memory.list_entities(entity_type=entity_type, limit=10_000)  # type: ignore[arg-type]

    if query is not None:
        needle = query.lower()
        entities = [
            e
            for e in entities
            if needle in e.canonical_name.lower() or any(needle in (a or "").lower() for a in e.aliases or [])
        ]

    reverse = order == "desc"
    if order_by == "atom_count":
        entities.sort(key=lambda e: (e.atom_count, e.canonical_name.lower()), reverse=reverse)
    elif order_by == "canonical_name":
        entities.sort(key=lambda e: e.canonical_name.lower(), reverse=reverse)
    else:  # last_promoted_at
        # ``None`` sorts as the epoch so freshly-created entities stay
        # at the bottom of "desc" rather than crashing on comparison.
        entities.sort(
            key=lambda e: e.last_promoted_at or datetime.min.replace(tzinfo=UTC),
            reverse=reverse,
        )

    window, total, has_more = _paginate(entities, offset, limit)
    return {
        "items": [_to_jsonable(e) for e in window],
        "total": total,
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# RPC: list_episodes
# ---------------------------------------------------------------------------


def list_episodes(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """List episodes with emotion / intensity / date / topic / query filters.

    Params::

        emotion?: str
        intensity_min?: int (1..5)
        date_from?: ISO datetime
        date_to?:   ISO datetime
        topic?: str         (exact match against any element of episode.topics)
        query?: str         (substring over summary + verbatim_quote + people + topics)
        offset?: int
        limit?: int

    Returns ``{items, total, has_more}`` ordered by ``occurred_at`` desc.
    """
    emotion = _opt_str(params, "emotion")
    intensity_min = _opt_int(params, "intensity_min", minimum=1)
    date_from = _opt_iso(params, "date_from")
    date_to = _opt_iso(params, "date_to")
    topic = _opt_str(params, "topic")
    query = _opt_str(params, "query")
    offset = _offset(params)
    limit = _limit(params)

    episodes = memory.list_episodes(
        emotion=emotion,
        after=date_from,
        before=date_to,
        limit=10_000,
    )

    if intensity_min is not None:
        episodes = [ep for ep in episodes if ep.intensity >= intensity_min]
    if topic is not None:
        episodes = [ep for ep in episodes if topic in (ep.topics or [])]
    if query is not None:
        episodes = [
            ep
            for ep in episodes
            if _matches_query(
                [
                    ep.summary,
                    ep.verbatim_quote,
                    " ".join(ep.people or []),
                    " ".join(ep.topics or []),
                ],
                query,
            )
        ]

    episodes.sort(key=lambda ep: as_utc(ep.occurred_at), reverse=True)
    window, total, has_more = _paginate(episodes, offset, limit)
    return {
        "items": [_to_jsonable(ep) for ep in window],
        "total": total,
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# RPC: list_journal
# ---------------------------------------------------------------------------


_TARGET_TYPE_TO_FIELD = {
    "atom": "target_atom_id",
    "entity": "target_entity_id",
    "candidate": "target_candidate_id",
}

# Max length for the human-readable ``target_summary`` attached to each
# journal entry (so the dashboard can show *which* memory was acted on,
# not just "one memory"). Longer assertions get truncated with an ellipsis.
_JOURNAL_SUMMARY_MAXLEN = 40


def _journal_target_summary(
    memory: Memory,
    entry: Any,
    atom_cache: dict[str, str | None],
    cand_cache: dict[str, str | None],
    ent_cache: dict[str, str | None],
) -> str | None:
    """Resolve a short human-readable label for a journal entry's target.

    Precedence: atom assertion → candidate assertion → entity name.
    Per-request caches avoid refetching the same id across entries.
    """
    text: str | None = None

    aid = entry.target_atom_id
    if aid is not None:
        if aid not in atom_cache:
            atom = memory.get_atom(aid)
            atom_cache[aid] = atom.assertion if atom else None
        text = atom_cache[aid]

    cid = entry.target_candidate_id
    if not text and cid is not None:
        if cid not in cand_cache:
            cand = memory.get_candidate(cid)
            cand_cache[cid] = cand.assertion if cand else None
        text = cand_cache[cid]

    eid = entry.target_entity_id
    if not text and eid is not None:
        if eid not in ent_cache:
            ent = memory.get_entity(eid)
            ent_cache[eid] = ent.canonical_name if ent else None
        text = ent_cache[eid]

    if not text:
        return None
    text = text.strip()
    if len(text) > _JOURNAL_SUMMARY_MAXLEN:
        text = text[: _JOURNAL_SUMMARY_MAXLEN - 1] + "…"
    return text


def list_journal(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """List journal entries with action / target / actor / time filters.

    Params::

        action?: JournalAction literal
        target_type?: "atom" | "entity" | "candidate"
            Used in tandem with target_type to require non-null target_*_id.
        actor?: "auto" | "user" | "rule"
        time_from?: ISO datetime
        time_to?:   ISO datetime
        target_entity_id?: str
        target_atom_id?: str
        target_candidate_id?: str
        offset?: int
        limit?: int

    Returns ``{items, total, has_more}`` ordered by timestamp desc.
    """
    action = _opt_str(params, "action")
    target_type = _opt_str(params, "target_type")
    actor = _opt_str(params, "actor")
    time_from = _opt_iso(params, "time_from")
    time_to = _opt_iso(params, "time_to")
    target_entity_id = _opt_str(params, "target_entity_id")
    target_atom_id = _opt_str(params, "target_atom_id")
    target_candidate_id = _opt_str(params, "target_candidate_id")
    offset = _offset(params)
    limit = _limit(params)

    if target_type is not None and target_type not in _TARGET_TYPE_TO_FIELD:
        raise ValueError("'target_type': must be 'atom' / 'entity' / 'candidate'")

    entries = memory.list_journal(
        action=action,  # type: ignore[arg-type]
        target_entity_id=target_entity_id,
        target_atom_id=target_atom_id,
        target_candidate_id=target_candidate_id,
        after=time_from,
        before=time_to,
        limit=10_000,
    )

    if actor is not None:
        entries = [e for e in entries if e.actor == actor]
    if target_type is not None:
        attr = _TARGET_TYPE_TO_FIELD[target_type]
        entries = [e for e in entries if getattr(e, attr) is not None]

    # ``Memory.list_journal`` returns oldest-first; UI wants newest-first.
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    window, total, has_more = _paginate(entries, offset, limit)

    # Enrich each entry with a short ``target_summary`` so the dashboard can
    # show *which* memory was acted on (e.g. the promoted assertion), not just
    # a generic "one memory" placeholder. Caches keep this to one lookup per
    # distinct id.
    atom_cache: dict[str, str | None] = {}
    cand_cache: dict[str, str | None] = {}
    ent_cache: dict[str, str | None] = {}
    items: list[dict[str, Any]] = []
    for entry in window:
        payload = _to_jsonable(entry)
        payload["target_summary"] = _journal_target_summary(memory, entry, atom_cache, cand_cache, ent_cache)
        items.append(payload)

    return {"items": items, "total": total, "has_more": has_more}


# ---------------------------------------------------------------------------
# RPC: list_candidates
# ---------------------------------------------------------------------------


_VALID_CANDIDATE_STATUSES = {
    "pending",
    "needs_review",
    "conflict",
    "promoted",
    "rejected",
}


def list_candidates(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """List Candidates with status / type / query filters.

    Powers the dashboard's "Candidate Review" inbox where the user
    promotes / rejects pending L1 rows. When ``status`` is omitted the
    bridge returns **all** statuses (pending + needs_review + conflict +
    promoted + rejected) so the dashboard's "All" filter works as
    advertised. Callers that only want the work queue must pass
    ``status="pending"`` explicitly (the dashboard does this on mount).

    Params (all optional)::

        status?: "pending" | "needs_review" | "conflict" | "promoted" | "rejected"
            (default: no filter — returns all statuses)
        candidate_type?: "Fact" | "Decision" | "Task" | "Preference" | "ConflictCandidate"
        session_id?: str
        target_entity_id?: str
        time_from?: ISO datetime
        time_to?:   ISO datetime
        query?: str    (substring over assertion / verbatim_quote / title)
        offset?: int
        limit?:  int

    Returns ``{items, total, has_more}`` newest-first by ``created_at``.
    """
    status = _opt_str(params, "status")
    if status is not None and status not in _VALID_CANDIDATE_STATUSES:
        raise ValueError("'status': must be one of " + ", ".join(sorted(_VALID_CANDIDATE_STATUSES)))

    candidate_type = _opt_str(params, "candidate_type")
    session_id = _opt_str(params, "session_id")
    target_entity_id = _opt_str(params, "target_entity_id")
    time_from = _opt_iso(params, "time_from")
    time_to = _opt_iso(params, "time_to")
    query = _opt_str(params, "query")
    offset = _offset(params)
    limit = _limit(params)

    rows = memory.list_candidates(
        status=status,  # type: ignore[arg-type]
        session_id=session_id,
        target_entity_id=target_entity_id,
        after=time_from,
        before=time_to,
        limit=10_000,
    )

    if candidate_type is not None:
        rows = [c for c in rows if c.candidate_type == candidate_type]
    if query is not None:
        rows = [
            c
            for c in rows
            if _matches_query(
                [c.assertion, c.verbatim_quote, c.title],
                query,
            )
        ]

    rows.sort(key=lambda c: c.created_at, reverse=True)
    window, total, has_more = _paginate(rows, offset, limit)
    return {
        "items": [_to_jsonable(c) for c in window],
        "total": total,
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# RPC: get_raw_event / get_candidate (single-row fetches for cross-layer drawer)
# ---------------------------------------------------------------------------


def get_raw_event(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one RawEvent by id, raising if not found."""
    event_id = _opt_str(params, "event_id") or _opt_str(params, "id")
    if event_id is None:
        raise ValueError("'event_id': required")
    row = memory.get_raw(event_id)
    if row is None:
        raise _NotFoundError(f"raw event {event_id!r} not found")
    return _to_jsonable(row)  # type: ignore[no-any-return]


def get_candidate(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one Candidate by id."""
    cand_id = _opt_str(params, "candidate_id") or _opt_str(params, "id")
    if cand_id is None:
        raise ValueError("'candidate_id': required")
    row = memory.get_candidate(cand_id)
    if row is None:
        raise _NotFoundError(f"candidate {cand_id!r} not found")
    return _to_jsonable(row)  # type: ignore[no-any-return]


def get_atom(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one AtomCard by id, enriched with its candidate ``kind``."""
    atom_id = _opt_str(params, "atom_id") or _opt_str(params, "id")
    if atom_id is None:
        raise ValueError("'atom_id': required")
    atom = memory.get_atom(atom_id)
    if atom is None:
        raise _NotFoundError(f"atom {atom_id!r} not found")
    payload = _to_jsonable(atom)
    cand = memory.get_candidate(atom.candidate_id)
    payload["kind"] = cand.candidate_type if cand else None
    return payload  # type: ignore[no-any-return]


def get_entity(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one Entity (+ inlined ``page`` if it has been generated).

    Returning the page inline saves the frontend a second roundtrip
    when the user just wants to read the long-form summary; for
    fresh entities without a regen yet the field is ``None``.
    """
    entity_id = _opt_str(params, "entity_id") or _opt_str(params, "id")
    if entity_id is None:
        raise ValueError("'entity_id': required")
    entity = memory.get_entity(entity_id)
    if entity is None:
        raise _NotFoundError(f"entity {entity_id!r} not found")
    payload = _to_jsonable(entity)
    page = memory.get_entity_page(entity_id)
    payload["page"] = _to_jsonable(page) if page is not None else None
    return payload  # type: ignore[no-any-return]


def get_episode(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one Episode by id."""
    episode_id = _opt_str(params, "episode_id") or _opt_str(params, "id")
    if episode_id is None:
        raise ValueError("'episode_id': required")
    ep = memory.get_episode(episode_id)
    if ep is None:
        raise _NotFoundError(f"episode {episode_id!r} not found")
    return _to_jsonable(ep)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# RPC: stats_*
# ---------------------------------------------------------------------------


def stats_counts(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Return scalar counts for the Overview dashboard.

    ``backend.count_stats()`` only carries ``raw_events / atoms /
    entities / dirty_pages``; we top it up with episode count,
    pending-candidate count, 7-day deltas computed from
    ``created_at`` (atoms / entities / episodes), and
    ``last_extract_run`` (latest extract summary from meta, or
    ``None`` if extract has never run).
    """
    _ = params
    # Widened: count_stats() is int-valued, but last_extract_run adds a dict.
    base: dict[str, Any] = dict(memory.backend.count_stats())
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=7)

    episodes = memory.list_episodes(limit=10_000)
    base["episodes"] = len(episodes)

    pending = memory.list_candidates(status="pending", limit=10_000)
    base["candidates_pending"] = len(pending)

    # 7-day deltas — list_atoms / list_entities don't accept date
    # filters yet, so we re-pull and count in Python.
    base["atoms_delta_7d"] = sum(
        1 for a in memory.list_atoms(include_deprecated=True, limit=10_000) if a.created_at >= cutoff
    )
    base["entities_delta_7d"] = sum(1 for e in memory.list_entities(limit=10_000) if e.created_at >= cutoff)
    base["episodes_delta_7d"] = sum(1 for ep in episodes if ep.created_at >= cutoff)
    base["last_extract_run"] = memory.get_last_extract_run()

    return base


def stats_growth(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Return per-day counts for the Overview growth chart.

    Params::

        days?: int (default 7, cap 90)

    Returns ``{series: [{date, atoms, episodes, entities, turns}]}``
    where each entry is the *creation count* on that UTC date —
    ``turns`` counts ``user_message`` raw events (one user utterance
    per turn). The aggregate cumulative line is left to the frontend
    to plot if it wants by ``cumsum``-ing.
    """
    days = _opt_int(params, "days", minimum=1) or 7
    days = min(days, 90)
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=days - 1)
    cutoff = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)

    atom_buckets: Counter[str] = Counter()
    episode_buckets: Counter[str] = Counter()
    entity_buckets: Counter[str] = Counter()
    turn_buckets: Counter[str] = Counter()

    for a in memory.list_atoms(include_deprecated=True, limit=10_000):
        if a.created_at >= cutoff:
            atom_buckets[a.created_at.date().isoformat()] += 1
    for ep in memory.list_episodes(limit=10_000):
        if ep.created_at >= cutoff:
            episode_buckets[ep.created_at.date().isoformat()] += 1
    for e in memory.list_entities(limit=10_000):
        if e.created_at >= cutoff:
            entity_buckets[e.created_at.date().isoformat()] += 1
    for evt in memory.list_raw(event_type="user_message", after=cutoff, limit=10_000):
        turn_buckets[evt.timestamp.date().isoformat()] += 1

    series: list[dict[str, Any]] = []
    for offset_days in range(days):
        d = (start_date + timedelta(days=offset_days)).isoformat()
        series.append(
            {
                "date": d,
                "atoms": atom_buckets.get(d, 0),
                "episodes": episode_buckets.get(d, 0),
                "entities": entity_buckets.get(d, 0),
                "turns": turn_buckets.get(d, 0),
            }
        )
    return {"series": series}


def stats_atom_kinds(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Return ``[{kind, count}]`` for the Atom-types pie chart.

    AtomCard has no ``kind`` of its own — we read the upstream
    candidate's ``candidate_type``. Atoms whose candidate row is
    missing (e.g. deleted by GC) bucket under ``"unknown"``.
    """
    _ = params
    counts: Counter[str] = Counter()
    for atom in memory.list_atoms(include_deprecated=False, limit=10_000):
        cand = memory.get_candidate(atom.candidate_id)
        kind = cand.candidate_type if cand else "unknown"
        counts[kind] += 1
    return {"series": [{"kind": k, "count": v} for k, v in counts.most_common()]}


def recent_journal(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Return the latest N journal entries (newest-first) for the Overview."""
    limit = _limit(params, default=5, cap=100)
    entries = memory.list_journal(limit=10_000)
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return {"items": [_to_jsonable(e) for e in entries[:limit]]}


# ---------------------------------------------------------------------------
# RPC: write actions (promote / reject candidate, deprecate atom)
# ---------------------------------------------------------------------------


def promote_candidate(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Promote or user-approve a single candidate.

    ``pending`` rows go through the automatic 5-check worker (may still
    land as merge / conflict / needs_review). ``needs_review`` and
    ``conflict`` rows are a human decision from the dashboard: force
    write the atom, and on conflict supersede the live contradictory
    atom so both sides are not recalled.
    """
    from octop_memory.pipeline.promotion import PromotionResult, PromotionWorker

    cand_id = _opt_str(params, "candidate_id") or _opt_str(params, "id")
    if cand_id is None:
        raise ValueError("'candidate_id': required")
    cand = memory.get_candidate(cand_id)
    if cand is None:
        raise _NotFoundError(f"candidate {cand_id!r} not found")
    if cand.status not in {"pending", "needs_review", "conflict"}:
        raise ValueError(f"candidate {cand_id!r} cannot be promoted (current status={cand.status!r})")
    if cand.payload.get("manual_revision") and "manual_documents" in params:
        from octop_memory.domain.retention import manual_documents_revision

        documents = params["manual_documents"]
        if not isinstance(documents, dict) or any(not isinstance(v, str) for v in documents.values()):
            raise ValueError("manual_documents must map filenames to text")
        if manual_documents_revision(documents) != cand.payload["manual_revision"]:
            raise ValueError("The manual document changed; review the current version before approving")
    if cand.status == "pending":
        result = memory.promote_candidates([cand])
    else:
        decision = PromotionWorker(memory).approve(cand)
        result = PromotionResult(decisions=[decision])
    return {
        "promoted": result.promoted,
        "merged": result.merged,
        "conflicts": result.conflicts,
        "needs_review": result.needs_review,
        "dropped": result.dropped,
        "llm_calls": result.llm_calls,
    }


def reject_candidate(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Mark a candidate ``rejected`` and append a journal entry.

    Soft action — the candidate row stays for audit; it just no longer
    surfaces in the "pending" badge or the candidate inbox.
    """
    cand_id = _opt_str(params, "candidate_id") or _opt_str(params, "id")
    if cand_id is None:
        raise ValueError("'candidate_id': required")
    reason = _opt_str(params, "reason")
    actor = _opt_str(params, "actor") or "user"
    if actor not in {"user", "auto", "rule"}:
        raise ValueError("'actor': must be 'user' / 'auto' / 'rule'")

    cand = memory.get_candidate(cand_id)
    if cand is None:
        raise _NotFoundError(f"candidate {cand_id!r} not found")
    if cand.status not in {"pending", "needs_review", "conflict"}:
        raise ValueError(f"candidate {cand_id!r} cannot be rejected (current status={cand.status!r})")

    now = datetime.now(UTC)
    updated = memory.update_candidate_status(
        cand_id,
        status="rejected",
        decided_by=actor,
        decided_at=now,
    )
    if not updated:
        raise _NotFoundError(f"candidate {cand_id!r} could not be updated")

    memory.append_journal(
        JournalEntry(
            id=str(uuid.uuid4()),
            timestamp=now,
            action="reject",
            actor=actor,  # type: ignore[arg-type]
            target_candidate_id=cand_id,
            target_entity_id=cand.target_entity_id,
            before={"status": cand.status, "assertion": cand.assertion},
            after={"status": "rejected"},
            note=reason or "Rejected via dashboard.",
        )
    )
    return {"candidate_id": cand_id, "status": "rejected"}


def deprecate_atom(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Soft-deprecate an atom. Wraps :meth:`Memory.deprecate_atom`."""
    atom_id = _opt_str(params, "atom_id") or _opt_str(params, "id")
    if atom_id is None:
        raise ValueError("'atom_id': required")
    note = _opt_str(params, "reason") or _opt_str(params, "note") or ""
    actor_in = _opt_str(params, "actor") or "user"
    if actor_in not in {"user", "auto", "rule"}:
        raise ValueError("'actor': must be 'user' / 'auto' / 'rule'")
    ok = memory.deprecate_atom(atom_id, actor=actor_in, note=note)  # type: ignore[arg-type]
    if not ok:
        # Either unknown id or already deprecated — surface as not-found
        # so the dashboard renders a clean error rather than a silent
        # no-op.
        raise _NotFoundError(f"atom {atom_id!r} not found or already deprecated")
    return {"atom_id": atom_id, "status": "deprecated"}


def _serialize_atom(memory: Memory, atom: AtomCard) -> dict[str, Any]:
    payload = _to_jsonable(atom)
    payload["kind"] = _atom_kind(memory, atom, {})
    return payload  # type: ignore[no-any-return]


def create_atom(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Manually create an atom (and optionally its entity)."""
    assertion = _opt_str(params, "assertion")
    if assertion is None:
        raise ValueError("'assertion': required")
    entity_id = _opt_str(params, "entity_id")
    entity_name = _opt_str(params, "entity_name")
    entity_type = _opt_str(params, "entity_type") or "Fact"
    kind = _opt_str(params, "kind") or _opt_str(params, "candidate_type") or "Fact"
    importance = _opt_str(params, "importance") or "medium"
    confidence = _opt_str(params, "confidence") or "high"
    note = _opt_str(params, "reason") or _opt_str(params, "note") or ""
    actor_in = _opt_str(params, "actor") or "user"
    if actor_in not in {"user", "auto", "rule"}:
        raise ValueError("'actor': must be 'user' / 'auto' / 'rule'")
    try:
        atom, entity, created_entity = memory.create_atom(
            assertion,
            entity_id=entity_id,
            entity_name=entity_name,
            entity_type=entity_type,  # type: ignore[arg-type]
            kind=kind,  # type: ignore[arg-type]
            importance=importance,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            actor=actor_in,  # type: ignore[arg-type]
            note=note,
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise _NotFoundError(message) from exc
        raise
    return {
        "atom": _serialize_atom(memory, atom),
        "entity": _to_jsonable(entity),
        "created_entity": created_entity,
        "status": "created",
    }


def replace_atom(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Replace a live atom's assertion by creating a successor."""
    atom_id = _opt_str(params, "atom_id") or _opt_str(params, "id")
    if atom_id is None:
        raise ValueError("'atom_id': required")
    assertion = _opt_str(params, "assertion")
    if assertion is None:
        raise ValueError("'assertion': required")
    note = _opt_str(params, "reason") or _opt_str(params, "note") or ""
    actor_in = _opt_str(params, "actor") or "user"
    if actor_in not in {"user", "auto", "rule"}:
        raise ValueError("'actor': must be 'user' / 'auto' / 'rule'")
    try:
        atom = memory.replace_atom(atom_id, assertion=assertion, actor=actor_in, note=note)  # type: ignore[arg-type]
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise _NotFoundError(message) from exc
        raise
    if atom is None:
        raise _NotFoundError(f"atom {atom_id!r} not found or already deprecated")
    return {
        "old_atom_id": atom_id,
        "atom": _serialize_atom(memory, atom),
        "status": "replaced" if atom.id != atom_id else "unchanged",
    }


# ---------------------------------------------------------------------------
# RPC: terminal_* (convenience wrappers for the End-User aggregator page)
# ---------------------------------------------------------------------------


_TERMINAL_PREFERENCE_KINDS = {"Preference"}
_TERMINAL_TASK_KINDS = {"Task"}
_TERMINAL_TOLD_KINDS = {"Fact", "Decision"}


def _terminal_atoms_by_kinds(
    memory: Memory,
    *,
    kinds: set[str],
    limit: int,
    recent_days: int | None = None,
) -> list[dict[str, Any]]:
    """Shared helper for the terminal_* atom buckets.

    ``recent_days`` lets us implement "current_focus = task within
    the last 7 days" without inventing a new RPC.
    """
    cutoff: datetime | None = None
    if recent_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=recent_days)

    atoms = memory.list_atoms(include_deprecated=False, limit=10_000)
    kind_cache: dict[str, str | None] = {}
    out: list[dict[str, Any]] = []
    for atom in atoms:
        if cutoff is not None and atom.created_at < cutoff:
            continue
        kind = _atom_kind(memory, atom, kind_cache)
        if kind not in kinds:
            continue
        payload = _to_jsonable(atom)
        payload["kind"] = kind
        out.append(payload)

    out.sort(
        key=lambda p: (
            _IMPORTANCE_RANK.get(p.get("importance", "low"), 0),
            p.get("created_at") or "",
        ),
        reverse=True,
    )
    return out[:limit]


def terminal_about_me(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """About-You card: highest-importance ``Preference`` atoms."""
    limit = _limit(params, default=5, cap=20)
    items = _terminal_atoms_by_kinds(memory, kinds=_TERMINAL_PREFERENCE_KINDS, limit=limit)
    return {"items": items}


def terminal_current_focus(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Current-Focus card: ``Task`` atoms touched in the last 7 days."""
    limit = _limit(params, default=5, cap=20)
    items = _terminal_atoms_by_kinds(memory, kinds=_TERMINAL_TASK_KINDS, limit=limit, recent_days=7)
    return {"items": items}


def terminal_things_you_told_me(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Things-You-Told-Me card: ``Fact`` and ``Decision`` atoms."""
    limit = _limit(params, default=5, cap=20)
    items = _terminal_atoms_by_kinds(memory, kinds=_TERMINAL_TOLD_KINDS, limit=limit)
    return {"items": items}


def terminal_recent_stories(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """Recent-Stories card: latest episodes ordered by ``occurred_at``."""
    limit = _limit(params, default=5, cap=20)
    episodes = memory.list_episodes(limit=10_000)
    episodes.sort(key=lambda ep: as_utc(ep.occurred_at), reverse=True)
    return {"items": [_to_jsonable(ep) for ep in episodes[:limit]]}


def terminal_entities(memory: Memory, params: dict[str, Any]) -> dict[str, Any]:
    """People/Things card: top entities by atom_count."""
    limit = _limit(params, default=5, cap=20)
    entities = memory.list_entities(limit=10_000)
    entities.sort(key=lambda e: (e.atom_count, e.canonical_name.lower()), reverse=True)
    return {"items": [_to_jsonable(e) for e in entities[:limit]]}


# ---------------------------------------------------------------------------
# Public wiring helper
# ---------------------------------------------------------------------------


class _NotFoundError(Exception):
    """Raised when a single-row fetch can't find its target.

    Imported by ``Bridge.handle`` to translate into ``ERR_PATH_NOT_FOUND``.
    Kept module-private so external callers always go through the JSON-RPC
    surface.
    """


def build_dispatch(memory: Memory) -> dict[str, Any]:
    """Return the ``method_name → handler(params)`` table for the Bridge.

    The returned mapping is ready to be ``dict.update``-merged into
    ``Bridge._dispatch``. Each value is a 1-arg callable (params dict)
    that closes over the supplied ``memory`` instance — keeping the
    Bridge's existing ``handler(params)`` signature unchanged.
    """

    def _bind(fn: Any) -> Any:
        def handler(params: dict[str, Any]) -> Any:
            return fn(memory, params)

        handler.__name__ = fn.__name__
        handler.__qualname__ = f"build_dispatch.<locals>.{fn.__name__}"
        return handler

    methods: dict[str, Any] = {
        "list_atoms": list_atoms,
        "list_raw_events": list_raw_events,
        "list_entities": list_entities,
        "list_episodes": list_episodes,
        "list_journal": list_journal,
        "list_candidates": list_candidates,
        "get_atom": get_atom,
        "get_entity": get_entity,
        "get_episode": get_episode,
        "get_raw_event": get_raw_event,
        "get_candidate": get_candidate,
        "stats_counts": stats_counts,
        "stats_growth": stats_growth,
        "stats_atom_kinds": stats_atom_kinds,
        "recent_journal": recent_journal,
        "promote_candidate": promote_candidate,
        "reject_candidate": reject_candidate,
        "deprecate_atom": deprecate_atom,
        "create_atom": create_atom,
        "replace_atom": replace_atom,
        "terminal_about_me": terminal_about_me,
        "terminal_current_focus": terminal_current_focus,
        "terminal_things_you_told_me": terminal_things_you_told_me,
        "terminal_recent_stories": terminal_recent_stories,
        "terminal_entities": terminal_entities,
    }
    return {name: _bind(fn) for name, fn in methods.items()}


__all__ = [
    "build_dispatch",
    "create_atom",
    "deprecate_atom",
    "get_atom",
    "get_candidate",
    "get_entity",
    "get_episode",
    "get_raw_event",
    "list_atoms",
    "list_candidates",
    "list_entities",
    "list_episodes",
    "list_journal",
    "list_raw_events",
    "promote_candidate",
    "recent_journal",
    "reject_candidate",
    "replace_atom",
    "stats_atom_kinds",
    "stats_counts",
    "stats_growth",
    "terminal_about_me",
    "terminal_current_focus",
    "terminal_entities",
    "terminal_recent_stories",
    "terminal_things_you_told_me",
]
