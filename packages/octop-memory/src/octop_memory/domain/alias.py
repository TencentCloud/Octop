"""Alias normalization helpers.

Pulled into its own module because both ``checks.py`` and future review
CLIs need the same normalization rule, and the rule is a quiet load-bearing
piece of the dedup story (entity match correctness depends on every caller
agreeing on what "same string" means).

Normalization (single, fixed scheme — D31 deliberately keeps it simple
and language-agnostic; M3 may layer transliteration on top):

1. Unicode NFKC fold (full-width → half-width, ligatures → letters)
2. Lowercase
3. Collapse internal whitespace runs to a single space
4. Strip leading/trailing whitespace

We do NOT strip punctuation: "GPT-4" and "GPT 4" SHOULD remain different
aliases. If the user wants them merged, they merge them explicitly via
``memory candidate review``.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_alias(value: str) -> str:
    """Apply the canonical alias-normalization scheme.

    Empty-string-in / empty-string-out is allowed (caller decides whether
    to skip). The function is total: any input string maps to some output
    string with no exceptions.
    """
    if not value:
        return ""
    nfkc = unicodedata.normalize("NFKC", value)
    lowered = nfkc.casefold()
    return _WHITESPACE_RE.sub(" ", lowered).strip()


__all__ = ["normalize_alias"]
