"""D51-C path projection: virtual ``path`` strings ↔ SQLite rows.

OpenClaw's ``memory_get(path, from, lines)`` is shaped for a file-backed
memory store. Our storage is SQLite. To bridge the gap we project rows
onto a *virtual* file tree and parse the path on the way back:

Virtual paths (SQLite-backed)::

    atom/<atom_id>.md            → AtomCard
    page/<entity_id>.md          → EntityPage (long-form summary)
    raw/<YYYY-MM-DD>/<id>.md     → RawEvent (date taken from event.timestamp)

Real-file paths (D51-C — host-written; indexed and served by
``HostFilesIndex`` when the bridge receives ``--host-files-root``)::

    MEMORY.md                    → root long-term file
    USER.md                      → root user-profile memory file
    memory/<YYYY-MM-DD>.md       → daily file (compaction silent turn target)
    memory/<YYYY-MM-DD>-<slug>.md → slugged daily variant (session-memory hook)
    DREAMS.md                    → optional dream diary
    topics/<name>.md             → allowlisted topical memory file

This module is intentionally pure: no SQLite, no I/O — it only does
parsing, formatting, and rendering. The bridge handlers wire it to the
backend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from octop_memory.types import AtomCard, EntityPage, RawEvent

# ---------------------------------------------------------------------------
# Path kinds
# ---------------------------------------------------------------------------

PathKind = Literal["atom", "page", "raw", "host_root", "host_daily", "host_dreams", "host_file"]
"""Discriminator for parsed paths.

``host_*`` are real files written by the OpenClaw host (compaction
silent turn / user edits). ``atom``/``page``/``raw`` are virtual.
"""

MIN_PATH_PARTS = 2
"""Minimum number of path segments for a valid host markdown path (e.g. 'memory/2024-01-01.md')."""


@dataclass(frozen=True)
class PathRef:
    """Parsed virtual or real-file path.

    Fields are sparse: only the ones relevant for the kind are set.
    For example a ``raw`` ref has ``id`` and ``date`` set; a ``host_root``
    ref has only ``filename`` set (e.g. ``"MEMORY.md"``).
    """

    kind: PathKind
    raw_path: str
    """The path as the agent gave it; preserved for error messages."""

    id: str | None = None
    """``atom_id`` for atom refs / ``entity_id`` for page refs / ``event_id`` for raw refs."""

    date: str | None = None
    """``YYYY-MM-DD`` for raw refs and host_daily refs."""

    filename: str | None = None
    """For host file refs (``MEMORY.md`` / ``USER.md`` / ``topics/foo.md``)."""

    slug: str | None = None
    """Optional slug for ``memory/YYYY-MM-DD-<slug>.md`` variants."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# id alphabet: alphanumerics + underscore + hyphen. Atoms / events use uuid-ish
# ids, entities use canonical names — both are safe under [A-Za-z0-9_-].
_ID_RE = r"[A-Za-z0-9_\-]+"
_DATE_RE = r"\d{4}-\d{2}-\d{2}"

_ATOM_RE = re.compile(rf"^atom/({_ID_RE})\.md$")
_PAGE_RE = re.compile(rf"^page/({_ID_RE})\.md$")
_RAW_RE = re.compile(rf"^raw/({_DATE_RE})/({_ID_RE})\.md$")
_HOST_DAILY_RE = re.compile(rf"^memory/({_DATE_RE})(?:-({_ID_RE}))?\.md$")


class PathError(ValueError):
    """Raised when a path string can't be parsed into any known kind.

    Subclassing :class:`ValueError` keeps it palatable for JSON-RPC
    error mapping (we surface the message to the agent).
    """


def parse_path(path: str) -> PathRef:
    """Parse an agent-supplied path string into a typed :class:`PathRef`.

    Raises :class:`PathError` for unknown shapes — the bridge surfaces
    this to the agent as a normal tool error so it can recover (e.g.
    fall back to ``memory_search``).
    """
    if not path or path.strip() != path:
        raise PathError(f"path must be non-empty and unpadded: {path!r}")

    # Most-specific patterns first.
    if m := _RAW_RE.match(path):
        return PathRef(kind="raw", raw_path=path, date=m.group(1), id=m.group(2))
    if m := _ATOM_RE.match(path):
        return PathRef(kind="atom", raw_path=path, id=m.group(1))
    if m := _PAGE_RE.match(path):
        return PathRef(kind="page", raw_path=path, id=m.group(1))
    if m := _HOST_DAILY_RE.match(path):
        date = m.group(1)
        slug = m.group(2)
        return PathRef(
            kind="host_daily",
            raw_path=path,
            date=date,
            slug=slug,
            filename=path,
        )
    if path == "MEMORY.md":
        return PathRef(kind="host_root", raw_path=path, filename=path)
    if path == "USER.md":
        return PathRef(kind="host_root", raw_path=path, filename=path)
    if path == "DREAMS.md":
        return PathRef(kind="host_dreams", raw_path=path, filename=path)
    if _is_safe_host_markdown_path(path):
        return PathRef(kind="host_file", raw_path=path, filename=path)

    raise PathError(
        f"unknown path shape: {path!r}; expected one of "
        "atom/<id>.md, page/<entity_id>.md, raw/<YYYY-MM-DD>/<id>.md, "
        "memory/<YYYY-MM-DD>.md, MEMORY.md, USER.md, DREAMS.md, or an indexed relative .md host file"
    )


def _is_safe_host_markdown_path(path: str) -> bool:
    """Return true for relative markdown paths that cannot escape the host index."""
    if not path.endswith(".md") or path.startswith("/") or "\\" in path:
        return False
    parts = path.split("/")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        return False
    return len(parts) >= MIN_PATH_PARTS


# ---------------------------------------------------------------------------
# Formatting (row → path)
# ---------------------------------------------------------------------------


def atom_to_path(atom: AtomCard) -> str:
    return f"atom/{atom.id}.md"


def page_to_path(page: EntityPage) -> str:
    return f"page/{page.entity_id}.md"


def raw_to_path(event: RawEvent) -> str:
    """Format a :class:`RawEvent` as a virtual path.

    Date is derived from ``event.timestamp`` in UTC (we don't carry a
    user timezone yet — host_daily files do, but that's the host's job).
    """
    date = event.timestamp.strftime("%Y-%m-%d")
    return f"raw/{date}/{event.id}.md"


# ---------------------------------------------------------------------------
# Rendering (row → markdown body)
# ---------------------------------------------------------------------------

# Each renderer returns a self-contained markdown document with a YAML
# front-matter block of provenance metadata + a body. The agent gets
# enough context to cite (`Source: <path>#L<n>`) without seeing internal
# fields it shouldn't reason about (e.g. ``superseded_by`` chains).


def render_atom_md(atom: AtomCard) -> str:
    """Render an :class:`AtomCard` as a self-contained markdown doc.

    Front-matter exposes id / entity / importance / confidence + the
    raw event id of the verbatim quote. Body has the assertion +
    (when distinct) the verbatim quote in a blockquote.
    """
    lines: list[str] = [
        "---",
        f"id: {atom.id}",
        f"entity_id: {atom.entity_id}",
        f"importance: {atom.importance}",
        f"confidence: {atom.confidence}",
        f"occurred_at: {atom.occurred_at.isoformat()}",
        f"quote_event_id: {atom.quote_event_id}",
        "---",
        "",
        f"# {atom.assertion}",
        "",
    ]
    if atom.verbatim_quote and atom.verbatim_quote.strip() != atom.assertion.strip():
        lines.append(f"> {atom.verbatim_quote}")
        lines.append("")
    if atom.search_terms:
        lines.append(f"_search terms: {', '.join(atom.search_terms)}_")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_page_md(page: EntityPage) -> str:
    """Render an :class:`EntityPage` markdown body with front-matter.

    The page's ``summary_markdown`` may itself be empty (for brand-new
    dirty entities); we still emit the front-matter so the agent can
    distinguish "no summary yet" from "no such page".
    """
    lines: list[str] = [
        "---",
        f"entity_id: {page.entity_id}",
        f"version: {page.summary_version}",
        f"dirty: {str(page.dirty).lower()}",
        f"updated_at: {page.updated_at.isoformat()}",
        "---",
        "",
    ]
    headline = (page.headline or "").strip()
    if headline:
        lines.append(f"# {headline}")
        lines.append("")
    body = (page.summary_markdown or "").strip()
    if body:
        lines.append(body)
    else:
        lines.append("_(empty page — pending regeneration)_")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_raw_md(event: RawEvent) -> str:
    """Render a :class:`RawEvent` markdown view.

    Body is verbatim ``content``. Front-matter exposes role / event
    type / session ids so the agent can cite the right turn.
    """
    role = event.payload.get("role") if isinstance(event.payload, dict) else None
    role_str = role if isinstance(role, str) and role else event.event_type
    lines: list[str] = [
        "---",
        f"id: {event.id}",
        f"event_type: {event.event_type}",
        f"role: {role_str}",
        f"timestamp: {event.timestamp.isoformat()}",
    ]
    if event.session_id:
        lines.append(f"session_id: {event.session_id}")
    if event.thread_id:
        lines.append(f"thread_id: {event.thread_id}")
    lines.append("---")
    lines.append("")
    lines.append(event.content)
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Line slicing
# ---------------------------------------------------------------------------


def slice_lines(text: str, *, from_line: int | None = None, lines: int | None = None) -> str:
    """Return a 1-indexed line range of ``text``.

    ``from_line`` defaults to 1 (first line). ``lines`` defaults to no
    limit. Both correspond to the ``from`` / ``lines`` parameters of
    OpenClaw's ``memory_get`` schema (both ``integer >= 1``).

    Out-of-range slicing is graceful: if ``from_line`` exceeds the
    document length, we return an empty string rather than raising —
    the agent can re-read with a smaller offset.
    """
    if from_line is not None and from_line < 1:
        raise ValueError(f"from_line must be >= 1, got {from_line!r}")
    if lines is not None and lines < 1:
        raise ValueError(f"lines must be >= 1, got {lines!r}")

    body_lines = text.splitlines()
    start = (from_line or 1) - 1
    if start >= len(body_lines):
        return ""
    end = len(body_lines) if lines is None else min(start + lines, len(body_lines))
    return "\n".join(body_lines[start:end])


# ---------------------------------------------------------------------------
# Continuation hint
# ---------------------------------------------------------------------------


def excerpt_metadata(
    *,
    full_text: str,
    from_line: int | None,
    lines: int | None,
) -> dict[str, Any]:
    """Build the bookkeeping dict the agent expects alongside an excerpt.

    Mirrors the ``memory_get`` semantics the official ``memory-core``
    tool surfaces: when the requested slice doesn't cover the whole
    document, we return ``truncated: true`` plus a ``continuation``
    pointer so the agent can call again with a higher ``from``.
    """
    total = len(full_text.splitlines())
    start = from_line or 1
    end = total if lines is None else min(start + lines - 1, total)
    truncated = end < total or start > 1
    out: dict[str, Any] = {
        "total_lines": total,
        "from_line": start,
        "to_line": max(start - 1, end),
        "truncated": truncated,
    }
    if end < total:
        out["continuation"] = {"from": end + 1}
    return out


__all__ = [
    "PathError",
    "PathKind",
    "PathRef",
    "atom_to_path",
    "excerpt_metadata",
    "page_to_path",
    "parse_path",
    "raw_to_path",
    "render_atom_md",
    "render_page_md",
    "render_raw_md",
    "slice_lines",
]


# Suppress unused import warning at module level — datetime is referenced
# by docstring examples only; left out of the public re-export.
_ = datetime
