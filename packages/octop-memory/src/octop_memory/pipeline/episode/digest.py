"""Daily / weekly / monthly digest generator over Episodes.

Aggregation strategy:

- ``daily`` (the primary mode): gather all Episodes within one calendar
  day (UTC) and ask the LLM to write a markdown diary entry. This is
  the natural unit for emotional memory — "今天怎么样".
- ``weekly`` / ``monthly`` (optional roll-ups): instead of re-reading
  raw episodes, these aggregate the **already-generated day-level
  digests** within the period to produce a higher-level retrospective.
  If no daily digests exist for the period yet, weekly/monthly fall
  back to reading episodes directly so they still produce something.

Output is persisted as a :class:`DigestRecord` AND optionally exported
as a markdown file the user can read/edit.

The digest uses the **heavy** LLM tier because the input can be sizable
and the output is consumer-facing markdown. If no LLM is configured, we
fall back to a deterministic plain-text roll-up so the feature still
produces SOMETHING — better than silently doing nothing.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from octop_memory.ports.llm import LLMClient
from octop_memory.ports.llm._protocol import LLMClientError
from octop_memory.types import DigestPeriod, DigestRecord, Episode

if TYPE_CHECKING:
    from octop_memory.core import Memory

logger = logging.getLogger("octop_memory.pipeline.episode.digest")

DECEMBER = 12
"""Month number for December; used in year-boundary arithmetic."""

DIGEST_PROMPT_VERSION = "digest/v2"


@dataclass
class DigestResult:
    """Outcome of generating one digest."""

    digest: DigestRecord
    episode_count: int
    file_path: Path | None = None
    used_llm: bool = False


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------


def day_key(when: datetime) -> str:
    """Return the ISO date key (e.g. ``"2026-06-26"``) for ``when``."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UTC).strftime("%Y-%m-%d")


def day_bounds(when: datetime) -> tuple[datetime, datetime]:
    """Return ``[00:00 UTC, next-day 00:00 UTC)`` covering ``when``."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    when_utc = when.astimezone(UTC)
    start = datetime(when_utc.year, when_utc.month, when_utc.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def iso_week_key(when: datetime) -> str:
    """Return the ISO week key (e.g. ``"2026-W26"``) for ``when``."""
    iso_year, iso_week, _ = when.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def iso_week_bounds(when: datetime) -> tuple[datetime, datetime]:
    """Return ``[Monday 00:00, NextMonday 00:00)`` (UTC) covering ``when``.

    ``isocalendar`` weekday: Monday=1 .. Sunday=7. We snap to Monday
    midnight UTC so digest periods are stable across DST shifts.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    monday_date = when.date() - timedelta(days=when.isoweekday() - 1)
    start = datetime.combine(monday_date, datetime.min.time(), tzinfo=UTC)
    return start, start + timedelta(days=7)


def month_key(when: datetime) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def month_bounds(when: datetime) -> tuple[datetime, datetime]:
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    start = datetime(when.year, when.month, 1, tzinfo=UTC)
    if when.month == DECEMBER:
        end = datetime(when.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(when.year, when.month + 1, 1, tzinfo=UTC)
    return start, end


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


_EMOTION_EMOJI = {
    "neutral": "·",
    "happy": "😄",
    "sad": "😢",
    "angry": "😠",
    "anxious": "😰",
    "excited": "🤩",
    "frustrated": "😤",
    "grateful": "🙏",
    "tired": "😴",
    "reflective": "🤔",
}


def _fallback_markdown(
    *,
    period_kind: DigestPeriod,
    period_key: str,
    episodes: list[Episode],
    sub_digests: list[DigestRecord] | None = None,
) -> str:
    """Deterministic markdown when no LLM is available.

    For ``daily``: groups episodes by their first topic (or "其他");
    within each group they're listed chronologically with the verbatim
    quote and emotion emoji.

    For ``weekly`` / ``monthly``: when ``sub_digests`` is supplied, the
    fallback simply concatenates the daily digests' markdown bodies
    under per-day headings; otherwise it falls back to the same per-
    topic grouping from episodes.
    """
    title_kind = period_kind.title()

    # Roll-up over already-generated daily digests
    if sub_digests:
        lines: list[str] = [
            f"# {period_key} {title_kind} Digest",
            "",
            f"_Roll-up of {len(sub_digests)} daily digest(s) — generated by deterministic fallback (no LLM)._",
            "",
        ]
        for d in sorted(sub_digests, key=lambda x: x.period_start):
            lines.append(f"## {d.period_key}")
            lines.append("")
            lines.append(d.markdown.strip())
            lines.append("")
        return "\n".join(lines)

    if not episodes:
        return f"# {period_key} {title_kind} Digest\n\n_No episodes captured this period._\n"

    # Daily-style by-topic grouping (also reused by weekly/monthly fallback
    # when no sub-digests exist yet).
    by_topic: dict[str, list[Episode]] = {}
    for ep in episodes:
        topic = ep.topics[0] if ep.topics else "其他"
        by_topic.setdefault(topic, []).append(ep)

    lines = [
        f"# {period_key} {title_kind} Digest",
        "",
        f"_{len(episodes)} episode(s) — generated by deterministic fallback (no LLM)._",
        "",
    ]

    for topic in sorted(by_topic.keys()):
        eps = by_topic[topic]
        lines.append(f"## {topic}")
        lines.append("")
        for ep in eps:
            emoji = _EMOTION_EMOJI.get(ep.emotion, "·")
            day = ep.occurred_at.astimezone(UTC).strftime("%m-%d %H:%M")
            people = f" · 👥 {', '.join(ep.people)}" if ep.people else ""
            lines.append(f"- **{day}** {emoji} {ep.summary}{people}")
            lines.append(f"  - > {ep.verbatim_quote}")
        lines.append("")

    # Emotion timeline
    timeline = " → ".join(
        f"{ep.occurred_at.astimezone(UTC).strftime('%m-%d')}{_EMOTION_EMOJI.get(ep.emotion, '·')}" for ep in episodes
    )
    lines.append("## 情绪轨迹")
    lines.append("")
    lines.append(timeline)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM-backed markdown
# ---------------------------------------------------------------------------


_DAILY_PROMPT = """\
You are a Personal Diary writer. Read this user's diary entries
(Episodes) for ONE DAY and write a concise, human-readable markdown
diary entry.

Output style:
- Tone: warm, observational, second-person ("你今天..." / "今天你..."),
  match the language of the source entries.
- Structure (in this order):
  1. ``# {period_key} Daily Digest`` (h1 title — period_key is the date).
  2. A 1-2 line opening summary ("今天一共 N 条记录，整体心情偏...").
  3. ``## 主题`` sections grouped by topic (家庭/工作/健康/朋友/项目/...)
     — within each, list entries in chronological order with HH:MM,
     summary, and a quote indented underneath.
  4. ``## 情绪轨迹`` (only if 2+ entries) showing the time-of-day
     emotion arc as a single line of "HH:MM<emoji>" arrows.
  5. ``## 值得一提`` (optional) — 1-2 bullet points the user might
     want to revisit.
- Use these emojis for emotion: neutral=·, happy=😄, sad=😢, angry=😠,
  anxious=😰, excited=🤩, frustrated=😤, grateful=🙏, tired=😴,
  reflective=🤔.
- Do NOT invent facts. Stick to what the entries actually say. You may
  group / re-summarize but every claim must be backed by an entry.
- Output markdown only. No JSON, no commentary, no fences.

INPUT (episodes for {period_key}):
{episodes_json}

OUTPUT MARKDOWN:
"""


_ROLLUP_PROMPT = """\
You are a Personal Diary Roll-up writer. The user already has
day-level diary entries; your job is to read them and produce a
higher-level {period_kind_title} retrospective in markdown.

Output style:
- Tone: warm, reflective, third-person ("用户这周/本月..." or
  "你这周..."), match the language of the source entries.
- Structure (in this order):
  1. ``# {period_key} {period_kind_title} Digest`` (h1 title).
  2. A 2-3 line opening that captures the period's overall arc
     ("本周整体心情起伏较大，前半段...，后半段...").
  3. ``## 主线故事`` — 2-4 bullet points pulling out the recurring
     threads or major events that span multiple days.
  4. ``## 情绪轨迹`` — one line of "MM-DD<emoji>" arrows summarizing
     the dominant emotion of each day.
  5. ``## 值得一提`` (optional) — 1-3 bullet points the user might
     want to revisit (recurring conflicts, unresolved feelings,
     wins worth celebrating).
- Use these emojis for emotion: neutral=·, happy=😄, sad=😢, angry=😠,
  anxious=😰, excited=🤩, frustrated=😤, grateful=🙏, tired=😴,
  reflective=🤔.
- Do NOT invent facts beyond what the daily digests state. You may
  abstract / synthesize, but every claim must trace back to an entry.
- Output markdown only. No JSON, no commentary, no fences.

INPUT (daily digests for {period_key}):
{daily_digests_json}

OUTPUT MARKDOWN:
"""


def _episodes_for_prompt(episodes: list[Episode]) -> str:
    return json.dumps(
        [
            {
                "occurred_at": ep.occurred_at.astimezone(UTC).isoformat(),
                "summary": ep.summary,
                "quote": ep.verbatim_quote,
                "emotion": ep.emotion,
                "intensity": ep.intensity,
                "people": ep.people,
                "topics": ep.topics,
            }
            for ep in episodes
        ],
        ensure_ascii=False,
        indent=2,
    )


def _daily_digests_for_prompt(sub_digests: list[DigestRecord]) -> str:
    return json.dumps(
        [
            {
                "date": d.period_key,
                "markdown": d.markdown,
            }
            for d in sorted(sub_digests, key=lambda x: x.period_start)
        ],
        ensure_ascii=False,
        indent=2,
    )


def _llm_markdown(
    *,
    llm: LLMClient,
    period_kind: DigestPeriod,
    period_key: str,
    episodes: list[Episode],
    sub_digests: list[DigestRecord] | None = None,
) -> str | None:
    """Call the heavy LLM; return None on failure (caller falls back).

    For ``daily`` we feed raw episodes. For ``weekly`` / ``monthly`` we
    prefer feeding the already-generated daily digests (more compact,
    higher-quality input) — but if none exist yet, we fall back to
    feeding episodes through the daily template.
    """
    if period_kind != "daily" and sub_digests:
        prompt = _ROLLUP_PROMPT.format(
            period_kind_title=period_kind.title(),
            period_key=period_key,
            daily_digests_json=_daily_digests_for_prompt(sub_digests),
        )
    else:
        prompt = _DAILY_PROMPT.format(
            period_key=period_key,
            episodes_json=_episodes_for_prompt(episodes),
        )
    try:
        out = llm.call_llm(prompt, tier="heavy", temperature=0.3)
    except LLMClientError as e:
        logger.warning("digest LLM call failed: %s", e)
        return None
    text = out.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        text = text[first_nl + 1 :] if first_nl != -1 else text
        text = text.removesuffix("```")
        text = text.strip()
    if not text:
        return None
    return text


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def generate_digest(
    memory: Memory,
    *,
    period_kind: DigestPeriod,
    when: datetime | None = None,
    period_key: str | None = None,
    llm: LLMClient | None = None,
    output_dir: Path | None = None,
) -> DigestResult:
    """Generate (or regenerate) one digest.

    ``when`` resolves the period containing that timestamp. Alternatively
    pass ``period_key`` to address a specific period directly. If both
    are missing, defaults to "current day / week / month" using ``now``.

    For ``daily`` we read episodes in [day_start, day_end). For
    ``weekly`` / ``monthly`` we prefer to roll up the *daily digests*
    that already exist within the period (compact, structured input);
    if no daily digests exist yet, we fall back to reading episodes
    directly so the feature still produces something useful.

    ``output_dir`` (when provided) writes the markdown to
    ``<output_dir>/<period_kind>/<period_key>.md`` for daily, and
    ``<output_dir>/<period_key>.md`` for weekly/monthly. Idempotent:
    running again overwrites.
    """
    cur = when or datetime.now(UTC)

    # Resolve period bounds + key
    if period_kind == "daily":
        if period_key:
            anchor = datetime.strptime(period_key, "%Y-%m-%d").replace(tzinfo=UTC)
            start, end = day_bounds(anchor)
        else:
            start, end = day_bounds(cur)
            period_key = day_key(cur)
    elif period_kind == "weekly":
        if period_key:
            year_str, week_str = period_key.split("-W")
            anchor = datetime.fromisocalendar(int(year_str), int(week_str), 1).replace(tzinfo=UTC)
            start, end = iso_week_bounds(anchor)
        else:
            start, end = iso_week_bounds(cur)
            period_key = iso_week_key(cur)
    elif period_kind == "monthly":
        if period_key:
            year_str, month_str = period_key.split("-")
            anchor = datetime(int(year_str), int(month_str), 1, tzinfo=UTC)
            start, end = month_bounds(anchor)
        else:
            start, end = month_bounds(cur)
            period_key = month_key(cur)
    else:  # pragma: no cover — Literal guards this
        raise ValueError(f"unknown period_kind {period_kind!r}")

    episodes = memory.list_episodes_in_range(start=start, end=end, limit=2000)

    # For roll-up periods (weekly / monthly), prefer to summarize the
    # already-generated daily digests rather than re-chewing all episodes.
    sub_digests: list[DigestRecord] = []
    if period_kind in ("weekly", "monthly"):
        all_daily = memory.list_digests(period_kind="daily", limit=400)
        sub_digests = [d for d in all_daily if start <= d.period_start < end]

    # Render markdown
    markdown: str | None = None
    used_llm = False
    has_input = bool(episodes) or bool(sub_digests)
    if llm is not None and has_input:
        markdown = _llm_markdown(
            llm=llm,
            period_kind=period_kind,
            period_key=period_key,
            episodes=episodes,
            sub_digests=sub_digests if period_kind != "daily" else None,
        )
        if markdown is not None:
            used_llm = True
    if markdown is None:
        markdown = _fallback_markdown(
            period_kind=period_kind,
            period_key=period_key,
            episodes=episodes,
            sub_digests=sub_digests if period_kind != "daily" else None,
        )

    now = datetime.now(UTC)
    digest = DigestRecord(
        id=str(uuid.uuid4()),
        period_kind=period_kind,
        period_key=period_key,
        period_start=start,
        period_end=end,
        markdown=markdown,
        episode_ids=[ep.id for ep in episodes],
        llm_version=DIGEST_PROMPT_VERSION,
        created_at=now,
        updated_at=now,
    )
    memory.upsert_digest(digest)

    file_path: Path | None = None
    if output_dir is not None:
        output_dir = output_dir.expanduser()
        # Daily files go under journals/daily/, weekly/monthly stay
        # at the top-level so directory listings stay scannable.
        target_dir = output_dir / period_kind if period_kind == "daily" else output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{period_key}.md"
        file_path.write_text(markdown, encoding="utf-8")
        logger.info(
            "memory.trigger digest ns=%s kind=%s key=%s eps=%d sub=%d file=%s",
            getattr(memory, "namespace", "?"),
            period_kind,
            period_key,
            len(episodes),
            len(sub_digests),
            file_path,
        )

    return DigestResult(
        digest=digest,
        episode_count=len(episodes),
        file_path=file_path,
        used_llm=used_llm,
    )


__all__ = [
    "DIGEST_PROMPT_VERSION",
    "DigestResult",
    "day_bounds",
    "day_key",
    "generate_digest",
    "iso_week_bounds",
    "iso_week_key",
    "month_bounds",
    "month_key",
]
