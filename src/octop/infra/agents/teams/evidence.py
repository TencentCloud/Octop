"""B3 evidence-anchor judge — three-level verdict + weak-evidence ratchet.

Read-side and pure: this module only ever *reads* anchor target files and the
fragment baseline that ships beside it (PLAN §2.2 / §4.3, invariant I3).

Verbatim contract (``team/2026-09-30-020000/PLAN.md``):

* ``ANCHOR_RE`` / ``TOKEN_SPLIT`` / ``TOKEN_MIN_LENGTH`` / ``BASELINE_FILE`` /
  ``FENCE`` are the frozen literals of §2.2 (R12–R14).
* ``EXACT`` (the whole anchor occurs verbatim in the target file body) is the
  only green verdict; ``FRAGMENT_ONLY`` (some token of length >= 2 occurs
  verbatim) is weak evidence and is ratcheted against the baseline; anything
  else is ``MISSING`` (§4.2).
* ``ratchet_codes`` is the single source of truth for the two code names (§2.2,
  decision D-5): callers must not re-derive them.

Matching is verbatim substring matching — no case folding, no regex, no fuzzy or
edit-distance matching, no word boundaries, no cross-line matching (§4.2). CJK
anchors match as substrings too: a deliberate "rather over-count than zero-hit"
stance (SPEC B3.6 / R9).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

ANCHOR_RE = re.compile(
    r"(?P<path>[^\s·]+)\s*·\s*(?P<anchor>.+?)\s*(?:@\s*(?P<line>\d+(?:-\d+)?)\s*)?$"
)
TOKEN_SPLIT = re.compile(r"[\s,，、/|·（）()]+")
TOKEN_MIN_LENGTH = 2
BASELINE_FILE = "evidence_fragment_baseline.json"
FENCE = "```"

EVIDENCE_ANCHOR_MISSING = "EVIDENCE_ANCHOR_MISSING"
EVIDENCE_FRAGMENT_RATCHET = "EVIDENCE_FRAGMENT_RATCHET"

# P3 (§4.1): an anchor that embeds a line number is not in canonical form
# (``<path> · <anchor> @ <line>``) and is rejected outright.
_EMBEDDED_RANGE_RE = re.compile(
    r"(?:(?<![A-Za-z0-9])(?:[Ll]|lines?)\s*(?<!\d)\d+(?:\s*-\s*[Ll]?\d+)?(?!\d)"
    r"|(?<!\d)\d+(?:\s*-\s*\d+)?\s*(?:行|lines?))"
)
# A bracketed **1–3 digit** number is a line reference; four digits are a year
# (``（2026-09-30）``), so the date form stays released.
_EMBEDDED_PAREN_LINE_RE = re.compile(r"[（(]\s*\d{1,3}(?:\s*-\s*\d{1,3})?\s*[)）]")


class Verdict(StrEnum):
    """§2.2: ``EXACT`` is the only green verdict."""

    EXACT = "EXACT"
    FRAGMENT_ONLY = "FRAGMENT_ONLY"
    MISSING = "MISSING"


@dataclass(frozen=True)
class AnchorHit:
    """One extracted anchor and its verdict."""

    path: str
    anchor: str
    line: str | None
    verdict: str
    reason: str


@dataclass(frozen=True)
class EvidenceReport:
    """§2.2: frozen value object, so ``f(x) == f(x)`` is assertable."""

    hits: tuple[AnchorHit, ...]
    exact: int
    fragment_only: int
    missing: int
    baseline: int
    codes: tuple[str, ...]
    details: tuple[str, ...]


def ratchet_codes(fragment_only: int, missing: int, baseline: int | None) -> tuple[str, ...]:
    """Map the two counters onto the two evidence codes — the only such source.

    ``missing >= 1`` ⇒ ``EVIDENCE_ANCHOR_MISSING``; ``fragment_only > (baseline
    or 0)`` ⇒ ``EVIDENCE_FRAGMENT_RATCHET`` (§2.2 / §4.3). A missing or ``None``
    baseline counts as 0, so the first weak evidence is red (fail-closed, I7).
    """
    codes: list[str] = []
    if missing >= 1:
        codes.append(EVIDENCE_ANCHOR_MISSING)
    if fragment_only > (baseline or 0):
        codes.append(EVIDENCE_FRAGMENT_RATCHET)
    return tuple(codes)


def _baseline_path() -> Path:
    """The ratchet baseline lives next to this module (PLAN §4.3, decision D-4)."""
    return Path(__file__).parent / BASELINE_FILE


def load_baseline(root: str | Path, run_id: str | None = None) -> int:
    """Read the weak-evidence ratchet baseline; anything missing/broken ⇒ 0.

    Lookup order is ``runs[run_id]`` → ``default`` → ``0`` (§4.3). A missing file,
    unreadable file, malformed JSON, non-object JSON or a non-integer value all
    fail closed to 0 (I7).

    ``root`` is kept for the frozen call-site signature (§2.2, used by ``anchors``
    to resolve anchor paths); the baseline location itself is pinned by §4.3 to
    ``evidence_fragment_baseline.json`` beside this module, because the ratchet
    travels with the code (D-4) rather than with the judged workspace.
    """
    try:
        raw: object = json.loads(_baseline_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(raw, dict):
        return 0
    if run_id is not None:
        runs = raw.get("runs")
        if isinstance(runs, dict):
            value = runs.get(run_id)
            if isinstance(value, int) and not isinstance(value, bool):
                return int(value)
    default = raw.get("default")
    if isinstance(default, int) and not isinstance(default, bool):
        return int(default)
    return 0


def _anchor_lines(text: str) -> list[tuple[int, str]]:
    """Yield ``(lineno, line)`` for every line that takes part in the verdict.

    P2 (§4.1 / R13): the *inside* of a paired ``` fence is skipped entirely; an
    unclosed fence exempts nothing, so every following line is still judged
    (fail-closed).
    """
    lines = text.splitlines()
    fence_lines = [index for index, line in enumerate(lines) if FENCE in line]
    skipped: set[int] = set()
    for opened, closed in zip(fence_lines[::2], fence_lines[1::2], strict=False):
        skipped.update(range(opened, closed + 1))
    return [(index + 1, line) for index, line in enumerate(lines) if index not in skipped]


def _classify(root: Path, path: str, anchor: str, line: str | None) -> AnchorHit:
    """Apply the P1–P4 hard rejects, then the three-level verdict (§4.1–§4.2)."""

    def hit(verdict: Verdict, reason: str) -> AnchorHit:
        return AnchorHit(path=path, anchor=anchor, line=line, verdict=verdict, reason=reason)

    if "/" not in path:
        return hit(Verdict.MISSING, "bare filename (path must contain a directory)")
    if not anchor:
        return hit(Verdict.MISSING, "empty anchor")
    if _EMBEDDED_RANGE_RE.search(anchor) or _EMBEDDED_PAREN_LINE_RE.search(anchor):
        return hit(Verdict.MISSING, "anchor embeds a line number")
    target = root / path
    try:
        resolved = target.resolve(strict=False)
        resolved_root = root.resolve()
    except (OSError, RuntimeError):
        return hit(Verdict.MISSING, "path cannot be resolved")
    if not resolved.is_relative_to(resolved_root):
        return hit(Verdict.MISSING, "path escapes root")
    if not target.is_file():
        reason = "path is not a file" if target.exists() else "path not found under root"
        return hit(Verdict.MISSING, reason)
    try:
        target_text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return hit(Verdict.MISSING, "path is not readable as utf-8 text")
    if anchor in target_text:
        return hit(Verdict.EXACT, "verbatim hit")
    for token in TOKEN_SPLIT.split(anchor):
        if len(token) >= TOKEN_MIN_LENGTH and token in target_text:
            return hit(Verdict.FRAGMENT_ONLY, f"token={token}")
    return hit(Verdict.MISSING, "no token hit")


def anchors(text: str, root: str | Path, baseline: int | None) -> EvidenceReport:
    """Judge every anchor in ``text`` against the files under ``root``.

    ``text`` is the artifact body (batch B: the ``REVIEW-SPEC.md`` snapshot) and
    ``root`` is the workspace root real path, read-only (§2.2). Counters are per
    anchor; ``ANCHOR_RE`` is ``$``-anchored, so each line yields at most one
    anchor. ``baseline`` is the already-resolved baseline (§4.3); ``None`` means 0.
    """
    root_path = Path(root)
    hits: list[AnchorHit] = []
    for _lineno, line in _anchor_lines(text):
        match = ANCHOR_RE.search(line)
        if match is None:
            continue
        hits.append(
            _classify(
                root_path,
                match.group("path"),
                match.group("anchor").strip("`"),
                match.group("line"),
            )
        )
    exact = sum(1 for hit in hits if hit.verdict == Verdict.EXACT)
    fragment_only = sum(1 for hit in hits if hit.verdict == Verdict.FRAGMENT_ONLY)
    missing = sum(1 for hit in hits if hit.verdict == Verdict.MISSING)
    return EvidenceReport(
        hits=tuple(hits),
        exact=exact,
        fragment_only=fragment_only,
        missing=missing,
        baseline=baseline or 0,
        codes=ratchet_codes(fragment_only, missing, baseline),
        details=tuple(
            f"{item.path} · {item.anchor} · {item.verdict} · {item.reason}" for item in hits
        ),
    )
