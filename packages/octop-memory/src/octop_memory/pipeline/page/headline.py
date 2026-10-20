"""Headline shaping helpers (D32-A — independent column, hard 30-char cap).

The recall path must NOT do markdown parsing to extract a hot summary, so
we precompute the headline at write time and store it in its own column.
The LLM is asked to produce a ≤30-char headline, but we still defensively
truncate here to enforce the budget.

Single-character logic is intentional: full-width Chinese characters are
counted as 1, the same as ASCII letters. This matches what readers see
on a single line of UI; if you want byte-budgeting use ``len(s.encode())``
in the caller.
"""

from __future__ import annotations

HEADLINE_MAX_CHARS = 30
"""Hard cap on headline length (Unicode characters)."""

ELLIPSIS = "…"


def truncate_headline(text: str, *, max_chars: int = HEADLINE_MAX_CHARS) -> str:
    """Trim ``text`` to ``max_chars`` characters, appending ``…`` if cut.

    - Strips leading / trailing whitespace and collapses internal newlines
      to single spaces (headlines must be single-line).
    - Returns the empty string if input is whitespace-only or empty.
    - Never returns more than ``max_chars`` Unicode characters
      *including* the ellipsis.
    """
    if not text:
        return ""
    flattened = " ".join(text.split())
    if not flattened:
        return ""
    if len(flattened) <= max_chars:
        return flattened
    if max_chars <= 1:
        return flattened[:max_chars]
    # Reserve one slot for the ellipsis.
    return flattened[: max_chars - 1] + ELLIPSIS


def coerce_headline(candidate_headline: str | None, *, fallback: str = "") -> str:
    """Pick the best non-empty headline candidate and truncate it.

    Used by the regenerator after parsing LLM output: if the LLM emits
    an empty / whitespace-only headline we fall back to a deterministic
    derivation (typically the entity's canonical_name + first atom
    assertion). Caller passes that fallback in.
    """
    primary = (candidate_headline or "").strip()
    if primary:
        return truncate_headline(primary)
    return truncate_headline(fallback)


__all__ = ["HEADLINE_MAX_CHARS", "coerce_headline", "truncate_headline"]
