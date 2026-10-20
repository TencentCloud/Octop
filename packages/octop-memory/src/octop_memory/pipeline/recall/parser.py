"""Query parser — extract entity hints + time hints + topic from raw text (M4.1).

Used by :mod:`octop_memory.pipeline.recall.router` to decide which sources to
hit. Pure-Python heuristics, no LLM.

Coverage:

- **Entity hints** — Match the query against known canonical names and
  aliases via :func:`octop_memory.domain.alias.normalize_alias`
  (lowercased Latin / Han fragments). Multi-word names that appear
  as substrings in the query also count.
- **Time hints** — Recognise both English and Chinese relative time
  expressions ("yesterday", "上次", "上周", "刚才", ISO-8601 dates,
  etc.) and convert them to a ``[start, end]`` UTC window relative
  to a caller-supplied ``now`` so unit tests can pin time.
- **Co-reference markers** — flags like "那个", "this one", "前面那个"
  are surfaced so the router knows to consult the active-entity stack.

The parser is intentionally additive: any query gets at least one
output field set. A query with no hints → ``ParsedQuery(text=...)``
which the router falls back to topical FTS on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from octop_memory.domain.alias import normalize_alias

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeWindow:
    """Half-open ``[start, end)`` window in UTC. Either bound may be ``None``."""

    start: datetime | None
    end: datetime | None
    label: str  # human-readable tag like "yesterday", "last week", or a CJK equivalent


@dataclass(frozen=True)
class ParsedQuery:
    """Structured view of a recall query.

    All fields are optional / additive; a "topical" query with no entity
    or time hints just has ``text`` and empty hint lists.
    """

    text: str
    """The raw query text, stripped of leading / trailing whitespace."""

    entity_hints: tuple[str, ...] = ()
    """Normalized strings to match against entity aliases. The router
    feeds these to ``find_entity_by_alias`` one at a time."""

    time_window: TimeWindow | None = None
    """If the query mentioned a relative or absolute time, the resolved
    UTC window. ``None`` means no time filter."""

    has_coreference: bool = False
    """``True`` if a pronoun-like marker is present and the router should
    consult the thread active-entity stack."""

    raw_tokens: tuple[str, ...] = field(default_factory=tuple)
    """Lowercased word-tokens (for FTS rendering / debug)."""


# ---------------------------------------------------------------------------
# Co-reference markers
# ---------------------------------------------------------------------------

# Chinese markers are matched via substring (Chinese has no word
# breaks); order longer phrases first so debugging output points at
# the most specific marker.
_COREFERENCE_MARKERS_CJK: tuple[str, ...] = (
    "前面那个",
    "刚才那",
    "刚刚那",
    "上次那",
    "那个",
    "这个",
)

# English markers MUST be word-bounded: a substring match on "it"
# flags "github" / "items" and pollutes recall with whatever entity
# happens to sit on top of the thread's active stack.
_COREFERENCE_MARKERS_EN_RE = re.compile(
    r"\b(?:this one|that one|the one|it)\b",
    re.IGNORECASE,
)


def _has_coreference(query: str) -> bool:
    if any(marker in query for marker in _COREFERENCE_MARKERS_CJK):
        return True
    return _COREFERENCE_MARKERS_EN_RE.search(query) is not None


# ---------------------------------------------------------------------------
# Time hint parser
# ---------------------------------------------------------------------------

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _parse_time_window(query: str, *, now: datetime) -> TimeWindow | None:
    """Detect the *first* recognised time hint and return its window.

    We deliberately stop at the first match — chains like "yesterday's
    last-week meeting" are too ambiguous to disambiguate without an LLM.
    """
    lc = query.lower()
    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)

    # Order: more specific first.
    if "yesterday" in lc or "昨天" in query or "昨日" in query:
        end = today_start
        start = today_start - timedelta(days=1)
        return TimeWindow(start=start, end=end, label="yesterday")

    if "today" in lc or "今天" in query or "今日" in query:
        return TimeWindow(start=today_start, end=now + timedelta(seconds=1), label="today")

    if "last week" in lc or "上周" in query or "上星期" in query:
        # Last 7 days ending now (sliding window — the "calendar week"
        # interpretation is too locale-sensitive to do without config).
        return TimeWindow(start=now - timedelta(days=7), end=now, label="last_week")

    if "this week" in lc or "本周" in query or "这周" in query:
        return TimeWindow(start=now - timedelta(days=7), end=now, label="this_week")

    if "last month" in lc or "上个月" in query or "上月" in query:
        return TimeWindow(start=now - timedelta(days=30), end=now, label="last_month")

    if "上次" in query or "前几天" in query or "刚才" in query or "刚刚" in query:
        # Loose "recent" window: last 24h covers most recent-reference usages.
        return TimeWindow(start=now - timedelta(days=1), end=now, label="recent")

    # ISO date — accept a single yyyy-mm-dd as a 24h window.
    m = _ISO_DATE_RE.search(query)
    if m is not None:
        try:
            day = datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=UTC)
        except ValueError:
            return None
        return TimeWindow(start=day, end=day + timedelta(days=1), label=f"day:{m[0]}")

    return None


# ---------------------------------------------------------------------------
# Entity hint extraction
# ---------------------------------------------------------------------------

# Match Latin words (≥2 chars) and Chinese sequences (≥2 Han chars).
# We deliberately drop length-1 fragments because they create too many
# false positives such as "a", "I", or single Han chars. For Han runs
# we additionally split into bigrams + trigrams so longer phrases like
# multi-word CJK queries yield searchable n-grams
# instead of one giant unsplittable string that matches no atom.
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_HAN_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")


def _han_ngrams(run: str, *, n_min: int = 2, n_max: int = 4) -> list[str]:
    """Yield n-grams of a Han run for FTS-friendly search.

    Generates from longest to shortest (n_max → n_min) so that longer,
    more precise n-grams get lower token_idx values in _word_tokens and
    therefore rank higher in _per_token_atom_search. Shorter n-grams
    (bigrams) are appended last as a broader fallback.

    Example: ``那个项目最近`` → ``[那个项目最, 个项目最近, 那个项目, 个项目最, ..., 那个, 个项, ...]``.
    Caller is responsible for de-duping (we do at the parse-query level).
    """
    out: list[str] = []
    for n in range(n_max, n_min - 1, -1):
        if len(run) < n:
            continue
        for i in range(len(run) - n + 1):
            out.append(run[i : i + n])
    return out


def _word_tokens(query: str) -> tuple[str, ...]:
    """Return word-ish tokens for FTS / hint matching, lowercased.

    Han runs explode into bigrams + trigrams so substring matches work
    against entity names embedded in longer queries. ASCII words are
    returned as-is (lowercased). De-dup preserves first-seen order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in _LATIN_WORD.finditer(query):
        t = m.group(0).lower()
        if t not in seen:
            seen.add(t)
            out.append(t)
    for m in _HAN_RUN.finditer(query):
        run = m.group(0)
        # Always include the full run so phrase-level matches still rank
        # high; then add n-grams for substring-level reach.
        if run not in seen:
            seen.add(run)
            out.append(run)
        for ngram in _han_ngrams(run):
            if ngram not in seen:
                seen.add(ngram)
                out.append(ngram)
    return tuple(out)


def _entity_hints(query: str) -> tuple[str, ...]:
    """Extract candidate entity-name fragments from ``query``.

    Returns a tuple of normalized strings (lowercased Latin, raw Han
    runs). The router feeds these one at a time into the alias table;
    a hit means we've found an entity to anchor recall on.

    NB: only emits the *whole* token forms (no n-grams) so we don't
    spam the alias lookup with low-information bigrams. False positives
    are still OK because ``find_entity_by_alias`` short-circuits on
    no match.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in _LATIN_WORD.finditer(query):
        norm = normalize_alias(m.group(0))
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    for m in _HAN_RUN.finditer(query):
        norm = normalize_alias(m.group(0))
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return tuple(out)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_query(query: str, *, now: datetime | None = None) -> ParsedQuery:
    """Parse a free-form recall query into a :class:`ParsedQuery`.

    Args:
        query: raw user query.
        now: pin time for tests / determinism. Defaults to ``datetime.now(UTC)``.

    The output is always populated (no exceptions on malformed input);
    the router treats absent fields as "no hint".
    """
    text = (query or "").strip()
    if not text:
        return ParsedQuery(text="")
    cur = now or datetime.now(UTC)
    return ParsedQuery(
        text=text,
        entity_hints=_entity_hints(text),
        time_window=_parse_time_window(text, now=cur),
        has_coreference=_has_coreference(text),
        raw_tokens=_word_tokens(text),
    )


__all__ = ["ParsedQuery", "TimeWindow", "parse_query"]
