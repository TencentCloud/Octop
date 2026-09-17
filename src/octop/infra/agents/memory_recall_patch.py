"""Persistent recall-quality patches for ``harness_memory``.

The upstream ``harness-memory`` package (PyPI) ships a recall pipeline whose
retrieval quality is poor for multi-person shared-conversation datasets like
the evaluation corpus. Three defects were found during eval work and are
patched here at startup (idempotent), so the fixes survive
``uv sync`` / redeploys instead of living only in the venv:

  1. ``router.route`` — entity hints are matched against stored aliases with
     an exact string lookup, but natural-language queries attach Chinese
     suffixes ("张小明的deadline" → hint "张小明的", stored alias "张小明").
     Result: no entity anchor is resolved, recall degrades to topical FTS
     and cross-entity topics (everyone's deadlines) drown the requested
     person's. Fix: progressively strip common suffixes before alias lookup.

  2. ``multi_source._per_token_atom_search`` — merges per-token FTS hits
     ordered by token position, so an early generic token ("李小" n-gram of
     "李小婉") outranks a later *relevant* token ("recurring"). Result:
     recall returns the entity's generic facts (age / company) instead of
     the topical memory. Fix: rank by count of matched *strong* tokens
     (full Latin words + complete Han runs + resolved anchor names), with
     n-grams contributing to recall but not to the relevance count.

  3. ``multi_source._gather_atoms`` anchor branch — when the router resolves
     an entity, its "recent atoms" fill the candidate list before FTS
     topical hits, so a query-relevant atom outside the recency window is
     truncated before rerank. Fix: run FTS first, then anchor atoms as
     fallback, and pass anchor entity names into the strong-token set so
     "张小明 + deadline" outranks someone else's "deadline".

Each patch wraps the original symbol (preserving the upstream signature and
behaviour as the fallback); ``apply_memory_recall_patch()`` is idempotent
and is invoked from ``octop.infra.server._boot_runtime`` before any agent
memory service is created.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness_memory.pipeline.recall.router import RoutingDecision

logger = logging.getLogger(__name__)

_PATCHED = False

# ── shared helpers ────────────────────────────────────────────────────────

_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_HAN_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

# Chinese possessive / copular suffixes that attach to a name in queries.
_SUFFIXES = ("的", "是", "在", "了", "与", "和")


def _strong_query_tokens(text: str) -> set[str]:
    """Full-word query tokens — Latin words + complete Han runs (no n-grams)."""
    out: set[str] = set()
    for m in _LATIN_WORD_RE.finditer(text):
        out.add(m.group(0).lower())
    for m in _HAN_RUN_RE.finditer(text):
        out.add(m.group(0))
    return out


def _alias_candidates(alias: str) -> tuple[str, ...]:
    """Ordered alias lookup candidates: exact match, then suffix-stripped."""
    out = [alias]
    if alias and not alias.isascii():
        stripped = alias
        for _ in range(3):
            if stripped and stripped[-1] in _SUFFIXES:
                stripped = stripped[:-1]
                if stripped:
                    out.append(stripped)
            else:
                break
    return tuple(out)


# ── 4. substring entity anchoring (cross-entity / conflict phrasing) ─────
#
# ``parser._entity_hints`` produces *fragmented* hints for compound
# natural-language queries: "在多位同事都提供了age的情况下，周晓东本人的age"
# yields hints like "周晓东本人的" (exact alias lookup misses "周晓东"),
# "和赵晓磊同住…王小明" yields one long blob, and "当吴晓强的…" keeps the
# leading "当". Exact-then-suffix-stripped resolution cannot recover the
# entity, so the router resolves nothing and recall degrades to topical FTS.
# Fix: also match any known entity name/alias as a *substring* of the query
# text, so the target person (王小明/周晓东/吴晓强/赵晓磊) is resolved and flows
# into the anchor branch of ``_gather_atoms`` (fixes cross-entity + conflict
# "以哪个值为准" phrasing misses).

_ENTITY_INDEX: dict[str, dict[str, str]] = {}


def _entity_index_key(memory: Any) -> str:
    """Key the entity-index cache by memory identity so daily / dev (two
    separate agents) never share one index."""
    return str(getattr(memory, "namespace", None) or id(getattr(memory, "_backend", memory)))


def _entity_index_for(memory: Any) -> dict[str, str]:
    key = _entity_index_key(memory)
    if key not in _ENTITY_INDEX:
        _ENTITY_INDEX[key] = _build_entity_index(memory)
    return _ENTITY_INDEX[key]


def _build_entity_index(memory: Any, *, limit: int = 800) -> dict[str, str]:
    """Map every entity canonical name + alias -> entity id."""
    idx: dict[str, str] = {}
    try:
        for e in memory.list_entities(limit=limit):
            names = [e.canonical_name, *(getattr(e, "aliases", None) or [])]
            for name in names:
                name = str(name).strip()
                if len(name) >= 2:
                    idx.setdefault(name, e.id)
        # The alias table may hold names not denormalized onto the entity.
        for a in memory.list_aliases(limit=limit * 2):
            al = str(getattr(a, "alias", "")).strip()
            if len(al) >= 2:
                idx.setdefault(al, a.entity_id)
    except Exception:  # noqa: BLE001
        # A bare/mock backend may lack these; fall back to an empty index.
        pass
    return idx


def _substring_entity_hits(text: str, idx: dict[str, str]) -> list[str]:
    """Entity ids whose name/alias appears as a substring of ``text``.

    De-duped by entity id, order-preserving.
    """
    hits: dict[str, str] = {}
    for name, eid in idx.items():
        if len(name) >= 2 and name in text:
            hits.setdefault(eid, name)
    return list(dict.fromkeys(hits))


# ── 1. router.route: suffix-tolerant entity resolution ────────────────────


def _patched_route(
    memory: Any,
    parsed: Any,
    *,
    thread_id: str | None = None,
) -> RoutingDecision:
    from harness_memory.pipeline.recall.router import _orig_route  # noqa: PLC0415

    # Re-resolve hints with suffix stripping: try each candidate alias in
    # order, resolve the first hit, and inject it back into the parsed
    # query so the original route() picks it up.
    resolved: list[str] = []
    for alias in parsed.entity_hints or ():
        for candidate in _alias_candidates(alias):
            try:
                entity = memory.find_entity_by_alias(candidate)
            except Exception:  # noqa: BLE001
                continue
            if entity is not None:
                resolved.append(entity.id)
                break

    # Substring anchoring: the parser's hint fragments (e.g. "当吴晓强的",
    # "周晓东本人的", "和赵晓磊同住…王小明") fail exact alias lookup, so the
    # router resolves nothing for these compound queries. Match any known
    # entity name/alias as a substring of the whole query text to recover the
    # target entity.
    try:
        for eid in _substring_entity_hits(parsed.text, _entity_index_for(memory)):
            if eid not in resolved:
                resolved.append(eid)
    except Exception:  # noqa: BLE001
        pass

    decision = _orig_route(memory, parsed, thread_id=thread_id)
    # Union our anchors (suffix + substring) with whatever the original route
    # resolved; never drop the original resolution. Only rebuild the decision
    # when we actually resolved something extra.
    union = list(dict.fromkeys(resolved + list(decision.resolved_entity_ids)))
    if union and tuple(union) != tuple(decision.resolved_entity_ids):
        from dataclasses import replace  # noqa: PLC0415

        decision = replace(decision, resolved_entity_ids=tuple(union))
    return decision


# ── 2. multi_source._per_token_atom_search: strong-token ranking ──────────


def _patched_per_token_atom_search(
    memory: Any,
    parsed: Any,
    *,
    limit: int,
    anchor_names: Sequence[str] = (),
) -> list[Any]:
    """Per-token FTS merge ranked by matched *strong* token count.

    Mirrors the upstream function but counts only strong tokens (full words
    + anchor entity names), so a hit matching "张小明" + "deadline" outranks
    a single-token "deadline" hit on a different entity.
    """
    strong = _strong_query_tokens(parsed.text)
    for name in anchor_names:
        norm = str(name).strip()
        if len(norm) >= 2:
            strong.add(norm.lower() if norm.isascii() else norm)
    seen: dict[str, dict[str, Any]] = {}
    tokens = parsed.raw_tokens or (parsed.text,)
    for token_idx, token in enumerate(tokens):
        if not str(token).strip():
            continue
        try:
            # Search deep: FTS5 rank is a global corpus score, so the
            # relevant hit for a common token (e.g. "recurring" shared by
            # many entities) can sit far past the top-N. A shallow pool
            # truncates it before our strong-token ranking can promote it.
            atoms = memory.search_atoms(token, limit=limit * 8)
        except Exception:
            continue
        is_strong = token in strong
        for atom_idx, atom in enumerate(atoms):
            entry = seen.get(atom.id)
            if entry is None:
                seen[atom.id] = {
                    "count": 1 if is_strong else 0,
                    "first": (token_idx, atom_idx),
                    "atom": atom,
                }
            elif is_strong:
                entry["count"] += 1
    ranked = sorted(
        seen.values(),
        key=lambda e: (-e["count"], e["first"][0], e["first"][1]),
    )
    return [e["atom"] for e in ranked[:limit]]


# ── 3. multi_source._gather_atoms anchor branch: FTS first + anchor names ──

# item 3: decision/cause/pitfall/experience intent reorder. The corpus stores
# "技术决策" atoms as e.g. "「X」做过一个技术决策：用 G6 而非 D3.js：因为…" and
# "踩坑/经验复用" atoms as "「X」的pitfalls有更新…" / "可复用经验…". For a query
# asking "技术决策及原因 / 为什么 / 经验复用 / 踩坑", those atoms are added as
# *anchor fillers after* the FTS "技术选型" matches and get truncated by
# `limit`. Reorder them ahead of generic selection atoms when the query shows
# that intent.
_DECISION_INTENT_RE = re.compile(
    r"技术决策|决策及原因|原因|为什么|若非|为何|经验|复用|踩|坑|规避|如何解决"
)
_DECISION_MARK_RE = re.compile(r"技术决策|而非|因为|坑|pitfall|经验|可复用|规避|决策|N\+1")


def _decision_first(atoms: list[Any]) -> list[Any]:
    """Stable-partition: decision/cause/pitfall atoms first, others after."""
    dec = [a for a in atoms if _DECISION_MARK_RE.search(getattr(a, "assertion", "") or "")]
    rest = [a for a in atoms if not _DECISION_MARK_RE.search(getattr(a, "assertion", "") or "")]
    return dec + rest


def _patched_gather_atoms(
    memory: Any,
    parsed: Any,
    *,
    limit: int,
    anchor_ids: Sequence[str] = (),
) -> list[Any]:
    """Anchor-narrowed atom gather: FTS topical hits first, anchor fillers
    after, with anchor entity names promoted into the strong-token set."""

    if anchor_ids:
        anchor_names: list[str] = []
        for eid in anchor_ids:
            ent = memory.get_entity(eid)
            if ent is not None and ent.canonical_name:
                anchor_names.append(ent.canonical_name)
        out: dict[str, Any] = {}
        for atom in _patched_per_token_atom_search(
            memory, parsed, limit=limit, anchor_names=anchor_names
        ):
            out.setdefault(atom.id, atom)
        if parsed.time_window is not None:
            for eid in anchor_ids:
                for atom in memory.search_atoms_by_time_range(
                    start=parsed.time_window.start,
                    end=parsed.time_window.end,
                    entity_id=eid,
                    limit=limit,
                ):
                    out.setdefault(atom.id, atom)
        else:
            for eid in anchor_ids:
                for atom in memory.list_atoms(entity_id=eid, limit=limit):
                    out.setdefault(atom.id, atom)
        atoms = list(out.values())
        # Reorder the WHOLE gathered set (FTS hits + anchor fillers) so the
        # decision/cause/pitfall atom is not truncated by `limit` before it
        # can be promoted ahead of generic "技术选型" atoms.
        if _DECISION_INTENT_RE.search(parsed.text or ""):
            atoms = _decision_first(atoms)
        return atoms[:limit]

    if parsed.time_window is not None:
        return list(
            memory.search_atoms_by_time_range(
                start=parsed.time_window.start,
                end=parsed.time_window.end,
                limit=limit,
            )
        )
    return _patched_per_token_atom_search(memory, parsed, limit=limit)


# ── apply ─────────────────────────────────────────────────────────────────


def apply_memory_recall_patch() -> None:
    """Install the recall-quality patches (idempotent)."""
    global _PATCHED
    if _PATCHED:
        return

    try:
        import harness_memory.pipeline.recall.multi_source as ms  # noqa: PLC0415
        import harness_memory.pipeline.recall.router as router  # noqa: PLC0415

        if not hasattr(router, "_orig_route"):
            router._orig_route = router.route
        router.route = _patched_route

        if not hasattr(ms, "_orig_per_token_atom_search"):
            ms._orig_per_token_atom_search = ms._per_token_atom_search
        ms._per_token_atom_search = _patched_per_token_atom_search

        if not hasattr(ms, "_orig_gather_atoms"):
            ms._orig_gather_atoms = ms._gather_atoms
        ms._gather_atoms = _patched_gather_atoms

        _PATCHED = True
        logger.info("memory recall patches applied (router suffix + strong-token ranking)")
    except Exception:  # noqa: BLE001
        # Never fail startup because a recall patch could not be installed —
        # upstream behaviour is the safe fallback.
        logger.warning(
            "memory recall patch installation failed; using upstream recall",
            exc_info=True,
        )
