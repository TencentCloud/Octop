"""Episode picker — selects the most care-worthy events from the user's episode memory.

Scoring logic:
  score = intensity * emotion_weight * recency_weight

- emotion_weight: negative emotions (sad/angry/anxious/frustrated) = 1.5,
                  tired/reflective = 1.2,
                  others (happy/excited/grateful/neutral) = 1.0
- recency_weight: 0-1 day = 1.0, 1-3 days = 0.8, 3-7 days = 0.6
- person dedup: keep only the highest-scoring episode per person
- time-window fallback: if all within 7 days are pushed, expand to 30 days and re-pick
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octop_memory.types import Episode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emotion weight mapping
# ---------------------------------------------------------------------------

_EMOTION_WEIGHT: dict[str, float] = {
    # High weight: negative emotions that need more care
    "sad": 1.5,
    "angry": 1.5,
    "anxious": 1.5,
    "frustrated": 1.5,
    # Medium weight: tired/reflective
    "tired": 1.2,
    "reflective": 1.2,
    # Low weight: positive/neutral emotions
    "happy": 1.0,
    "excited": 1.0,
    "grateful": 1.0,
    "neutral": 1.0,
}


def _emotion_weight(emotion: str) -> float:
    return _EMOTION_WEIGHT.get(emotion, 1.0)


def _recency_weight(occurred_at: datetime, now: datetime) -> float:
    """Return a time-decay weight based on how many days ago the episode occurred."""
    # Ensure both datetimes are aware or both are naive
    if occurred_at.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    elif occurred_at.tzinfo is None and now.tzinfo is not None:
        occurred_at = occurred_at.replace(tzinfo=UTC)

    delta_days = (now - occurred_at).total_seconds() / 86400
    if delta_days < 1:
        return 1.0
    elif delta_days < 3:
        return 0.8
    else:
        return 0.6


def _score(episode: Episode, now: datetime) -> float:
    """Compute the pick score for an episode."""
    return float(
        episode.intensity
        * _emotion_weight(episode.emotion)
        * _recency_weight(episode.occurred_at, now)
    )


@dataclass
class PickResult:
    """Pick result."""

    episodes: list[Episode]
    """The picked episodes (sorted, highest score first)."""

    window_days: int
    """The actual time window used (days)."""


class EpisodePicker:
    """Pick the most care-worthy events from a list of episodes.

    Args:
        top_k: Maximum number of episodes to pick (default 3).
        window_days: Initial time window (days, default 7).
        fallback_days: Fallback time window (days, default 30).
    """

    def __init__(
        self,
        *,
        top_k: int = 3,
        window_days: int = 7,
        fallback_days: int = 30,
    ) -> None:
        self._top_k = top_k
        self._window_days = window_days
        self._fallback_days = fallback_days

    def pick(
        self,
        episodes: list[Episode],
        *,
        pushed_ids: set[str],
        now: datetime | None = None,
    ) -> PickResult:
        """Pick the Top-K most care-worthy episodes from candidates.

        Args:
            episodes: Candidate episode list (typically all from the last N days).
            pushed_ids: Set of already-pushed episode_ids (used for dedup).
            now: Current time, defaults to UTC now.

        Returns:
            A PickResult containing the picked episodes and the actual time window used.
        """
        if now is None:
            now = datetime.now(UTC)

        # First try the window_days window
        result = self._pick_in_window(
            episodes,
            pushed_ids=pushed_ids,
            now=now,
            window_days=self._window_days,
        )
        if result:
            return PickResult(episodes=result, window_days=self._window_days)

        # All within 7 days already pushed; expand to fallback_days
        logger.info(
            "EpisodePicker: all episodes within %d days already pushed, expanding to %d days",
            self._window_days,
            self._fallback_days,
        )
        result = self._pick_in_window(
            episodes,
            pushed_ids=pushed_ids,
            now=now,
            window_days=self._fallback_days,
        )
        return PickResult(episodes=result, window_days=self._fallback_days)

    def _pick_in_window(
        self,
        episodes: list[Episode],
        *,
        pushed_ids: set[str],
        now: datetime,
        window_days: int,
    ) -> list[Episode]:
        """Pick the Top-K unpushed episodes within the given time window."""
        cutoff = now - timedelta(days=window_days)

        # Filter: within the time window + not yet pushed
        candidates = [
            ep
            for ep in episodes
            if ep.id not in pushed_ids and self._in_window(ep.occurred_at, cutoff, now)
        ]

        if not candidates:
            return []

        # Sort by score descending
        scored = sorted(candidates, key=lambda ep: _score(ep, now), reverse=True)

        # Person dedup: keep only the highest-scoring episode per person
        result = self._dedup_by_people(scored, now)

        return result[: self._top_k]

    @staticmethod
    def _in_window(occurred_at: datetime, cutoff: datetime, now: datetime) -> bool:
        """Check whether the episode falls within the time window."""
        # Normalize timezone handling
        if occurred_at.tzinfo is not None and cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
            now = now.replace(tzinfo=UTC)
        elif occurred_at.tzinfo is None and cutoff.tzinfo is not None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        return cutoff <= occurred_at <= now

    @staticmethod
    def _dedup_by_people(
        scored_episodes: list[Episode],
        now: datetime,
    ) -> list[Episode]:
        """Keep only the highest-scoring episode per person (already sorted by score descending, so take first occurrence).

        Note: one episode may involve multiple people (e.g. ["wife", "boss"]);
        here we dedup per person, keeping the first occurrence for each person (i.e. the highest score).
        """
        seen_people: set[str] = set()
        result: list[Episode] = []

        for ep in scored_episodes:
            # Episodes without a people field are not deduped; keep them directly
            if not ep.people:
                result.append(ep)
                continue

            # Check whether all people of this episode have already appeared
            new_people = [p for p in ep.people if p not in seen_people]
            if new_people:
                result.append(ep)
                seen_people.update(ep.people)

        return result
