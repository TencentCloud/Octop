"""Episode Extractor — turns raw events into L2.5 user-diary episodes.

Episodes capture **what happened to the user** and **how they felt**, the
exact category that the candidate extractor explicitly filters out as
"transient emotion / casual chat". This module runs in parallel with the
candidate pipeline so the agent can remember day-to-day life events
("I had a fight with my wife last weekend") without polluting the atom
layer that holds stable facts ("my wife's name is XiaoLi").

Pipeline:
1. Render the episode prompt against a batch of raw events.
2. Call ``LLMClient.call_llm(tier="light", response_format="json")``.
3. Parse the JSON into ``Episode`` dataclasses.
4. Return an :class:`EpisodeExtractionResult`.

The extractor is side-effect-free; the caller persists episodes via
``Memory.add_episodes``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from octop_memory.domain.datetime import as_utc
from octop_memory.domain.retention import is_runtime_error
from octop_memory.pipeline.episode.prompts import (
    EPISODE_EXTRACTOR_VERSION,
    render_episode_prompt,
)
from octop_memory.ports.llm import DEFAULT_EXTRACT_MAX_TOKENS, LLMClient
from octop_memory.ports.llm._protocol import LLMClientError
from octop_memory.types import Episode, EpisodeEmotion, RawEvent

logger = logging.getLogger("octop_memory.pipeline.episode")

DEFAULT_MAX_EPISODES = 10

_VALID_EMOTIONS: set[str] = {
    "neutral",
    "happy",
    "sad",
    "angry",
    "anxious",
    "excited",
    "frustrated",
    "grateful",
    "tired",
    "reflective",
}


@dataclass
class EpisodeExtractionResult:
    """Outcome of running the episode extractor on one batch."""

    episodes: list[Episode]
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    llm_calls: int = 0


def _serialize_events_for_prompt(events: list[RawEvent]) -> str:
    """Compact JSON of raw events for the episode prompt.

    Compact JSON of raw events for the prompt; we keep only what the
    LLM needs (event_id / event_type / content / timestamp).

    We deliberately filter to user_message + assistant_message — episodes
    are about user life, tool calls and host writes are noise.
    """
    payload = [
        {
            "event_id": e.id,
            "event_type": e.event_type,
            "content": e.content,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
        if e.event_type in ("user_message", "assistant_message")
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


class EpisodeExtractor:
    """Stateless orchestrator that turns raw events into Episodes."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        max_episodes: int = DEFAULT_MAX_EPISODES,
        extractor_version: str = EPISODE_EXTRACTOR_VERSION,
        temperature: float = 0.0,
        max_tokens: int | None = DEFAULT_EXTRACT_MAX_TOKENS,
    ) -> None:
        self._llm = llm
        self._max_episodes = max_episodes
        self._extractor_version = extractor_version
        self._temperature = temperature
        # ``None`` = unset by the caller — keep the built-in budget.
        self._max_tokens = DEFAULT_EXTRACT_MAX_TOKENS if max_tokens is None else max_tokens

    @property
    def extractor_version(self) -> str:
        return self._extractor_version

    def extract(
        self,
        events: list[RawEvent],
        *,
        session_id: str | None = None,
    ) -> EpisodeExtractionResult:
        """Run extraction on a batch of raw events."""
        events = [
            event
            for event in events
            if not is_runtime_error(event) and not event.payload.get("manual_document_evidence")
        ]
        if not events:
            return EpisodeExtractionResult(episodes=[])

        # Best-effort session tag.
        if session_id is None:
            sids = {e.session_id for e in events if e.session_id}
            if len(sids) == 1:
                session_id = sids.pop()

        events_json = _serialize_events_for_prompt(events)
        # If filtering left no usable events, bail early.
        try:
            parsed_input = json.loads(events_json)
        except json.JSONDecodeError:
            parsed_input = []
        if not parsed_input:
            return EpisodeExtractionResult(episodes=[])

        prompt = render_episode_prompt(events_json, max_episodes=self._max_episodes)
        raw_event_index: dict[str, RawEvent] = {e.id: e for e in events}

        try:
            raw_output = self._llm.call_llm(
                prompt,
                tier="light",
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_format="json",
            )
        except LLMClientError as e:
            return EpisodeExtractionResult(
                episodes=[],
                failure_reason=f"LLM call failed: {e}",
                llm_calls=1,
            )

        try:
            episodes, warnings = _parse_episode_output(
                raw_output,
                raw_event_index=raw_event_index,
                session_id=session_id,
                extractor_version=self._extractor_version,
                max_episodes=self._max_episodes,
            )
        except _EpisodeParseError as e:
            return EpisodeExtractionResult(
                episodes=[],
                failure_reason=f"parse failed: {e}",
                llm_calls=1,
            )

        return EpisodeExtractionResult(
            episodes=episodes,
            warnings=warnings,
            llm_calls=1,
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class _EpisodeParseError(Exception):
    """Internal parse-failure signal."""


def _parse_episode_output(
    raw_output: str,
    *,
    raw_event_index: dict[str, RawEvent],
    session_id: str | None,
    extractor_version: str,
    max_episodes: int,
) -> tuple[list[Episode], list[str]]:
    """Parse LLM JSON into ``Episode`` dataclasses with referential checks."""
    text = raw_output.strip()
    # Strip markdown fences if the model decided to add them despite the prompt.
    if text.startswith("```"):
        first_nl = text.find("\n")
        text = text[first_nl + 1 :] if first_nl != -1 else text
        text = text.removesuffix("```")
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise _EpisodeParseError(f"invalid JSON: {e}") from e

    if not isinstance(data, dict) or "episodes" not in data:
        raise _EpisodeParseError("missing top-level 'episodes' array")

    raw_episodes = data["episodes"]
    if not isinstance(raw_episodes, list):
        raise _EpisodeParseError("'episodes' must be a list")

    warnings: list[str] = []
    episodes: list[Episode] = []
    now = datetime.now(UTC)

    if len(raw_episodes) > max_episodes:
        warnings.append(f"episode list truncated: {len(raw_episodes)} > cap {max_episodes}")
        raw_episodes = raw_episodes[:max_episodes]

    for idx, item in enumerate(raw_episodes):
        if not isinstance(item, dict):
            warnings.append(f"episode[{idx}] is not an object — skipped")
            continue
        try:
            episode = _coerce_episode(
                item,
                raw_event_index=raw_event_index,
                session_id=session_id,
                extractor_version=extractor_version,
                now=now,
            )
        except _EpisodeParseError as e:
            warnings.append(f"episode[{idx}] dropped: {e}")
            continue
        episodes.append(episode)

    return episodes, warnings


def _coerce_episode(
    item: dict[str, Any],
    *,
    raw_event_index: dict[str, RawEvent],
    session_id: str | None,
    extractor_version: str,
    now: datetime,
) -> Episode:
    summary = _require_str(item, "summary", max_len=400)
    verbatim = _require_str(item, "verbatim_quote", max_len=400)

    quote_event_id = item.get("quote_event_id")
    if not isinstance(quote_event_id, str) or quote_event_id not in raw_event_index:
        raise _EpisodeParseError(f"quote_event_id {quote_event_id!r} not in batch")
    quote_event = raw_event_index[quote_event_id]

    source_refs = item.get("source_refs") or [quote_event_id]
    if not isinstance(source_refs, list):
        raise _EpisodeParseError("source_refs must be a list")
    valid_refs: list[str] = []
    for ref in source_refs:
        if isinstance(ref, str) and ref in raw_event_index:
            valid_refs.append(ref)
    if not valid_refs:
        valid_refs = [quote_event_id]

    emotion_raw = item.get("emotion", "neutral")
    emotion: EpisodeEmotion = "neutral"
    if isinstance(emotion_raw, str) and emotion_raw in _VALID_EMOTIONS:
        emotion = emotion_raw  # type: ignore[assignment]

    intensity_raw = item.get("intensity", 1)
    try:
        intensity = int(intensity_raw)
    except (TypeError, ValueError):
        intensity = 1
    intensity = max(1, min(5, intensity))

    people = _coerce_str_list(item.get("people"))
    topics = _coerce_str_list(item.get("topics"))

    occurred_at = as_utc(quote_event.timestamp)
    occurred_raw = item.get("occurred_at")
    if isinstance(occurred_raw, str):
        with contextlib.suppress(ValueError):
            occurred_at = as_utc(datetime.fromisoformat(occurred_raw))

    return Episode(
        id=str(uuid.uuid4()),
        raw_event_ids=valid_refs,
        occurred_at=occurred_at,
        summary=summary,
        verbatim_quote=verbatim,
        quote_event_id=quote_event_id,
        emotion=emotion,
        intensity=intensity,
        people=people,
        topics=topics,
        extractor_version=extractor_version,
        session_id=session_id,
        digest_ids=[],
        created_at=now,
    )


def _require_str(item: dict[str, Any], key: str, *, max_len: int) -> str:
    val = item.get(key)
    if not isinstance(val, str) or not val.strip():
        raise _EpisodeParseError(f"missing or empty {key!r}")
    return val[:max_len]


def _coerce_str_list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    out: list[str] = []
    for x in val:
        if isinstance(x, str) and x.strip():
            out.append(x.strip()[:50])
    return out[:10]


# ---------------------------------------------------------------------------
# Convenience: glue extractor + Memory storage
# ---------------------------------------------------------------------------


def extract_episodes_for_session(
    *,
    memory: object,
    extractor: EpisodeExtractor,
    session_id: str,
    persist: bool = True,
    new_event_ids: set[str] | None = None,
) -> EpisodeExtractionResult:
    """Run the episode extractor against a session's raw events.

    ``new_event_ids`` lets the caller restrict extraction to the events
    captured this turn (incremental mode) — same approach the candidate
    extractor uses via ``Bridge._seen_ids_for``.
    """
    raw_events: list[RawEvent] = memory.list_raw(session_id=session_id, limit=10_000)  # type: ignore[attr-defined]
    if new_event_ids is not None:
        raw_events = [e for e in raw_events if e.id in new_event_ids]
    if not raw_events:
        return EpisodeExtractionResult(episodes=[])

    result = extractor.extract(raw_events, session_id=session_id)

    if persist and result.episodes:
        memory.add_episodes(result.episodes)  # type: ignore[attr-defined]
        logger.info(
            "memory.trigger episodes ns=%s session=%s wrote=%d",
            getattr(memory, "namespace", "?"),
            session_id,
            len(result.episodes),
        )

    return result


__all__ = [
    "DEFAULT_MAX_EPISODES",
    "EpisodeExtractionResult",
    "EpisodeExtractor",
    "extract_episodes_for_session",
]
