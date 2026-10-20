"""User-notes section parsing & merging (D34-A — explicit ``## My Notes`` heading).

Decision rationale:

The LLM regenerator is asked to NOT modify any text under a top-level
``## My Notes`` heading. We rely on a literal heading match rather than
a fuzzy diff because fuzzy diffs of LLM-rewritten markdown are unreliable
and create silent data loss.

Public API:

- :func:`extract_user_notes` — pull the ``## My Notes`` block out of a
  markdown body, return ``(body_without_notes, notes_block)``.
- :func:`merge_user_notes` — splice a saved notes block into a freshly
  generated summary at the bottom; if the LLM accidentally already
  emitted its own ``## My Notes`` we DROP the LLM version (the user
  edit always wins) before splicing.
- :func:`detect_dropped_notes` — sanity check: did the LLM lose a notes
  block that was present in the previous version? Used post-hoc by the
  regenerator to refuse the change (D35-A: keep old version on failure).

The notes block is identified by *exact* heading match
``^## My Notes\\s*$``. That ASCII heading text is the contract; if a
non-English locale wants a different label, the host app can change
this constant — but it MUST be a single project-wide constant, not a
user-tunable string, so the LLM prompt and parser stay in lockstep.
"""

from __future__ import annotations

import re

USER_NOTES_HEADING = "## My Notes"
"""Exact markdown heading text that marks the user-editable section."""

# Match a line that is exactly ``## My Notes`` (with optional trailing
# whitespace), case-sensitive. We do not allow ``##  My Notes`` (extra
# space) so the contract stays tight.
_HEADING_RE = re.compile(r"(?m)^##\s+My Notes\s*$")


def extract_user_notes(markdown: str) -> tuple[str, str]:
    """Split a markdown body into (everything-before-notes, notes-block).

    The notes block runs from the ``## My Notes`` heading line through
    the end of the document (we intentionally do NOT stop at the next
    ``##`` heading — once the user opens a notes section, everything
    they wrote until EOF is theirs).

    If no notes heading is present, returns ``(markdown, "")``.
    """
    if not markdown:
        return "", ""
    match = _HEADING_RE.search(markdown)
    if match is None:
        return markdown, ""
    head = markdown[: match.start()].rstrip()
    notes = markdown[match.start() :].rstrip()
    return head, notes


def has_user_notes(markdown: str) -> bool:
    """``True`` iff ``markdown`` contains a ``## My Notes`` heading."""
    return _HEADING_RE.search(markdown or "") is not None


def merge_user_notes(generated_body: str, preserved_notes: str) -> str:
    """Splice ``preserved_notes`` into ``generated_body``.

    - If ``preserved_notes`` is empty, return ``generated_body`` unchanged.
    - If ``generated_body`` already contains a ``## My Notes`` block, we
      DROP that LLM-emitted version (the LLM is forbidden to write into
      the notes section; this is defensive normalization).
    - The preserved block is appended with one blank line separator.
    """
    body = generated_body or ""
    if not preserved_notes:
        return body.rstrip()

    cleaned_body, _llm_notes = extract_user_notes(body)
    cleaned_body = cleaned_body.rstrip()

    if not cleaned_body:
        return preserved_notes.rstrip()
    return f"{cleaned_body}\n\n{preserved_notes.rstrip()}"


def detect_dropped_notes(*, before: str, after: str) -> bool:
    """Return ``True`` if ``before`` had a notes block but ``after`` doesn't.

    Used by the regenerator as a post-merge sanity check. If the splice
    has already happened correctly this should always be ``False``;
    seeing ``True`` indicates a bug or a malicious LLM output and the
    caller MUST refuse the regen (keep the old summary, log the failure).
    """
    return has_user_notes(before) and not has_user_notes(after)


__all__ = [
    "USER_NOTES_HEADING",
    "detect_dropped_notes",
    "extract_user_notes",
    "has_user_notes",
    "merge_user_notes",
]
