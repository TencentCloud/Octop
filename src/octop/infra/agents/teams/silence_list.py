"""Machine-check the ``REVIEW-SPEC.md`` silence list — «沉默不得作为通过理由».

``templates/run/REVIEW-SPEC.md`` asks the reviewer to register, one row at a time, every
open question the SPEC left undefined, together with the ruling it proposes. The template
itself is only **text**; this module is the machine-judgeable half: it reads that text and
says whether the list is *there*, *complete*, and *legal* (PLAN §2.1 R1–R6, §2.4).

Two codes, mutually exclusive by construction:

``SILENCE_LIST_MISSING``
    No ``沉默清单`` section at all, **or** a section with no table data row (empty body,
    heading only, header row only). An empty section is worth exactly as much as no
    section — that equivalence is the point of R2.

``SILENCE_LIST_INCOMPLETE``
    A section with data rows, but at least one row leaves a required column empty, or its
    ``建议裁定`` does not start with ``允许`` / ``禁止``, or the table carries more than
    ``MAX_ROWS`` rows.

**Purity (hard constraint).** ``missing`` neither writes nor reads the filesystem: the
caller hands in the artifact's text and gets a frozen value object back. The input is read
as **text lines** — no HTML, no rich-text, no Markdown library — so the judgement can be
reproduced by hand with the same line numbers the report prints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: R1 — a section heading whose text starts with 沉默清单, at any level 1–6.
SILENCE_HEADING_RE = re.compile(r"^#{1,6}\s*沉默清单")
#: R3 — the three columns, verbatim, in the order the template declares them.
REQUIRED_COLUMNS: tuple[str, ...] = ("建议裁定", "依据", "风险")
#: R4 — a legal ruling must **start** with one of these; prefix match, not equality.
ALLOWED_VERDICT_PREFIXES: tuple[str, ...] = ("允许", "禁止")
#: R5 — 50 rows is green, 51 is red.
MAX_ROWS = 50

CODE_MISSING = "SILENCE_LIST_MISSING"
CODE_INCOMPLETE = "SILENCE_LIST_INCOMPLETE"

_HEADING_RE = re.compile(r"^#{1,6}\s")
_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")


@dataclass(frozen=True)
class SilenceReport:
    """Verdict of one ``REVIEW-SPEC.md`` body. Frozen ⇒ comparable and hashable."""

    missing: tuple[str, ...]
    incomplete: tuple[str, ...]
    rows: int
    #: One entry per finding: ``"L<行号> · <列名>"`` / ``"L<行号> · verdict · invalid
    #: verdict"`` / ``"rows · too many rows"`` (PLAN §2.4).
    details: tuple[str, ...]


def _cells(line: str) -> list[str]:
    """Split one table line into trimmed cells; outer pipes are dropped."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _section_end(lines: list[str], start: int, level: int) -> int:
    """R1 — index of the next heading of the same or higher level (else end of text)."""
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if _HEADING_RE.match(line) and len(line) - len(line.lstrip("#")) <= level:
            return index
    return len(lines)


def _row_indices(lines: list[str], low: int, high: int) -> tuple[int, int, list[int]]:
    """Locate the section's first table: ``(header index, first data row, data rows)``.

    Returns ``(-1, -1, [])`` when the section carries no table at all.
    """
    header = -1
    for index in range(low, high):
        if lines[index].strip().startswith("|"):
            header = index
            break
    if header < 0:
        return -1, -1, []
    first = header + 1
    if first < high and _SEPARATOR_RE.match(lines[first].strip()):
        first += 1
    rows: list[int] = []
    index = first
    while index < high and lines[index].strip().startswith("|"):
        rows.append(index)
        index += 1
    return header, first, rows


def _judge(lines: list[str], low: int, high: int) -> SilenceReport:
    header, _first, rows = _row_indices(lines, low, high)
    if header < 0 or not rows:
        # R2/R3 — no section body worth judging: empty ≡ absent.
        return SilenceReport(missing=(CODE_MISSING,), incomplete=(), rows=0, details=())
    column_of = {name: index for index, name in enumerate(_cells(lines[header]))}
    details: list[str] = []
    for index in rows:
        cells = _cells(lines[index])
        number = index + 1
        for name in REQUIRED_COLUMNS:
            position = column_of.get(name)
            value = cells[position] if position is not None and position < len(cells) else ""
            if not value:
                details.append(f"L{number} · {name}")
        position = column_of.get("建议裁定")
        verdict = cells[position] if position is not None and position < len(cells) else ""
        if verdict and not verdict.startswith(ALLOWED_VERDICT_PREFIXES):
            details.append(f"L{number} · verdict · invalid verdict")
    if len(rows) > MAX_ROWS:
        details.append("rows · too many rows")
    incomplete = (CODE_INCOMPLETE,) if details else ()
    return SilenceReport(missing=(), incomplete=incomplete, rows=len(rows), details=tuple(details))


def missing(text: str) -> SilenceReport:
    """Judge one artifact body. Pure: no I/O, no clock, no global state."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if SILENCE_HEADING_RE.match(line):
            level = len(line) - len(line.lstrip("#"))
            return _judge(lines, index + 1, _section_end(lines, index, level))
    return SilenceReport(missing=(CODE_MISSING,), incomplete=(), rows=0, details=())
