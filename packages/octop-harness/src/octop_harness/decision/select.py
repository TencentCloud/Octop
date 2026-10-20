"""Pure helpers for shortlisting catalog items and applying a confidence cutoff."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
_SHORTLIST_LIMIT = 16


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    description: str = ""


def query_tokens(text: str) -> set[str]:
    """Tokens used to compare a user message with catalog blurbs.

    Latin words need two characters. Each CJK character counts on its own.
    """
    out: set[str] = set()
    for token in _TOKEN_RE.findall(text or ""):
        if "\u4e00" <= token[0] <= "\u9fff":
            out.update(ch for ch in token if "\u4e00" <= ch <= "\u9fff")
        elif len(token) >= 2:
            out.add(token.lower())
    return out


def lexical_shortlist(
    items: list[Candidate],
    query: str,
    *,
    limit: int = _SHORTLIST_LIMIT,
) -> list[Candidate] | None:
    """Return the items to score, or ``None`` when the query matches nothing.

    Lists that already fit in ``limit`` are returned as-is. A longer list is
    cut to the overlapping items. No overlap means the caller should leave the
    catalog alone instead of hiding it behind an arbitrary slice.
    """
    if len(items) <= limit:
        return items
    tokens = query_tokens(query)
    if not tokens:
        return None
    scored: list[tuple[int, Candidate]] = []
    for item in items:
        haystack = f"{item.label} {item.description}".lower()
        score = sum(1 for token in tokens if token in haystack)
        if score:
            scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]


def keep_confident(
    probabilities: dict[str, float],
    ids: list[str],
    *,
    threshold: float,
    limit: int,
    slack: float = 0.0,
) -> list[str] | None:
    """Ids at or above ``threshold``, highest first.

    ``slack`` also keeps the next scores down to ``threshold - slack``, so a
    near miss is not thrown away while the list is still short. ``None`` means
    nothing cleared that floor and the caller should keep the original catalog.
    """
    ranked = sorted(((probabilities.get(item_id, 0.0), item_id) for item_id in ids), reverse=True)
    chosen = [item_id for probability, item_id in ranked if probability >= threshold]
    if slack > 0 and len(chosen) < limit:
        floor = threshold - slack
        for probability, item_id in ranked:
            if probability >= threshold or probability < floor:
                continue
            chosen.append(item_id)
            if len(chosen) >= limit:
                break
    if not chosen:
        return None
    return chosen[:limit]
