"""CJK-aware text normalization for FTS5 indexing and querying.

FTS5's ``unicode61`` tokenizer treats CJK ideographs as token characters,
so a contiguous Han run like ``"部署方案从docker切换"`` becomes ONE giant
token — queries for ``"部署"`` or even the embedded ``"docker"`` match
nothing. The fix is to segment text into per-character CJK tokens on BOTH
sides:

- **Index side**: every FTS write goes through :func:`segment_cjk` (via the
  ``hm_cjk_seg`` SQL function registered by :func:`register_fts_functions`,
  called from the FTS-sync triggers). ``"部署方案"`` is indexed as the
  token sequence ``部 署 方 案``.
- **Query side**: :func:`fts_match_phrase` applies the same segmentation
  and wraps the result in a quoted FTS5 phrase, so ``"部署"`` becomes the
  phrase ``"部 署"`` which matches the adjacent tokens ``部``, ``署``.

The transform is deterministic, which matters for external-content FTS
tables: the ``'delete'`` command must receive byte-identical values to
what was originally inserted.

ASCII / Latin text passes through unchanged, so English-only databases
behave exactly as before (a phrase query stays a phrase query).
"""

from __future__ import annotations

import re
import sqlite3

FTS_TEXT_VERSION = "2"
"""Bump whenever :func:`segment_cjk` output changes for any input.

Stored per-namespace in the ``{ns}_meta`` table; a mismatch at backend
init triggers a full FTS trigger re-creation + index rebuild so old
databases pick up the new segmentation transparently.
"""

# CJK Unified Ideographs + Extension A + Compatibility Ideographs.
# Kana / Hangul deliberately excluded — consistent with the project's
# stated scope (pipeline/recall/budget.py uses the same narrow definition).
_CJK_CHAR_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

_SQL_FUNC_NAME = "hm_cjk_seg"


def segment_cjk(text: str | None) -> str | None:
    """Insert spaces around CJK ideographs for FTS tokenization.

    Insert spaces around every CJK ideograph so unicode61 sees each
    character as its own token. Non-CJK text is returned untouched
    (modulo the inserted spaces at CJK boundaries).

    ``None`` passes through — triggers may feed nullable columns.
    """
    if text is None:
        return None
    if not _CJK_CHAR_RE.search(text):
        return text
    return _CJK_CHAR_RE.sub(lambda m: f" {m.group(0)} ", text)


def fts_match_phrase(query: str) -> str:
    """Build a quoted FTS5 MATCH phrase.

    Build a safe FTS5 MATCH expression: segment CJK, escape embedded
    double quotes, wrap the whole thing in one quoted phrase.

    Phrase semantics are intentionally preserved from the pre-CJK-fix
    behaviour (the whole query is one phrase); per-token OR matching is
    the recall pipeline's job, which calls this once per token.
    """
    seg = segment_cjk(query) or ""
    return '"{}"'.format(seg.replace('"', '""'))


def register_fts_functions(conn: sqlite3.Connection) -> None:
    """Register ``hm_cjk_seg`` on ``conn``.

    MUST be called on every connection that writes to a table with
    FTS-sync triggers (the triggers call the function). Idempotent —
    re-registering simply replaces the function.
    """
    conn.create_function(_SQL_FUNC_NAME, 1, segment_cjk, deterministic=True)


__all__ = [
    "FTS_TEXT_VERSION",
    "fts_match_phrase",
    "register_fts_functions",
    "segment_cjk",
]
