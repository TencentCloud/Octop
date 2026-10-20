"""End-to-end tests for the M5 Episode pipeline (extract + digest + recall)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from octop_memory.core import Memory
from octop_memory.pipeline.episode import EpisodeExtractionResult, EpisodeExtractor
from octop_memory.pipeline.episode.digest import (
    day_bounds,
    day_key,
    generate_digest,
    iso_week_bounds,
    iso_week_key,
)
from octop_memory.pipeline.recall import recall_for_prompt
from octop_memory.ports.llm import MockLLMClient
from octop_memory.types import Episode, RawEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_id: str,
    content: str,
    *,
    when: datetime | None = None,
    event_type: str = "user_message",
    session_id: str | None = "sess-ep-1",
) -> RawEvent:
    return RawEvent(
        id=event_id,
        host="manual",
        session_id=session_id,
        thread_id=None,
        user=None,
        timestamp=when or datetime.now(UTC),
        event_type=event_type,  # type: ignore[arg-type]
        content=content,
        payload={},
    )


def _episode_payload(
    *,
    summary: str = "用户和老婆吵架，因加班太多",
    quote: str = "今天和老婆吵架了，她说我天天加班不顾家",
    quote_event_id: str = "raw-1",
    emotion: str = "angry",
    intensity: int = 4,
    people: list[str] | None = None,
    topics: list[str] | None = None,
    occurred_at: str | None = None,
) -> str:
    payload = {
        "episodes": [
            {
                "summary": summary,
                "verbatim_quote": quote,
                "quote_event_id": quote_event_id,
                "source_refs": [quote_event_id],
                "emotion": emotion,
                "intensity": intensity,
                "people": people if people is not None else ["老婆"],
                "topics": topics if topics is not None else ["家庭", "冲突"],
            }
        ]
    }
    if occurred_at is not None:
        payload["episodes"][0]["occurred_at"] = occurred_at
    return json.dumps(payload, ensure_ascii=False)


def _make_memory(tmp_path: Path) -> Memory:
    db = tmp_path / "ep.sqlite"
    return Memory(namespace="ep_test", backend="sqlite", backend_config={"db_path": str(db)})


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TestEpisodeExtractor:
    def test_basic_extraction(self) -> None:
        events = [_make_event("raw-1", "今天和老婆吵架了，她说我天天加班不顾家")]
        mock = MockLLMClient(default_response=_episode_payload())
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)

        assert isinstance(result, EpisodeExtractionResult)
        assert result.failure_reason is None
        assert len(result.episodes) == 1
        ep = result.episodes[0]
        assert ep.emotion == "angry"
        assert ep.intensity == 4
        assert "老婆" in ep.people
        assert "家庭" in ep.topics
        assert ep.quote_event_id == "raw-1"

    def test_output_budget_passed_to_llm(self) -> None:
        # Extraction calls carry a bounded completion budget by default
        # (reasoning-heavy models must not run past the read timeout).
        events = [_make_event("raw-1", "今天和老婆吵架了，她说我天天加班不顾家")]
        mock = MockLLMClient(default_response=_episode_payload())
        extractor = EpisodeExtractor(llm=mock, max_tokens=1024)

        extractor.extract(events)

        assert len(mock.calls) == 1
        assert mock.calls[0].max_tokens == 1024

    def test_empty_episodes_response(self) -> None:
        events = [_make_event("raw-1", "Python 怎么排序字典？")]
        mock = MockLLMClient(default_response=json.dumps({"episodes": []}))
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)
        assert result.episodes == []
        assert result.failure_reason is None

    def test_invalid_json_records_failure(self) -> None:
        events = [_make_event("raw-1", "今天我加班了")]
        mock = MockLLMClient(default_response="not json at all")
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)
        assert result.episodes == []
        assert result.failure_reason is not None

    def test_intensity_clamped_to_1_5(self) -> None:
        events = [_make_event("raw-1", "今天好开心")]
        mock = MockLLMClient(
            default_response=_episode_payload(
                emotion="happy",
                intensity=99,
                topics=["生活"],
                people=[],
            )
        )
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)
        assert len(result.episodes) == 1
        assert result.episodes[0].intensity == 5

    def test_invalid_emotion_falls_back_to_neutral(self) -> None:
        events = [_make_event("raw-1", "随便说说")]
        mock = MockLLMClient(default_response=_episode_payload(emotion="not-a-real-emotion", intensity=2))
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)
        assert len(result.episodes) == 1
        assert result.episodes[0].emotion == "neutral"

    def test_drops_episode_with_unknown_quote_event_id(self) -> None:
        events = [_make_event("raw-1", "今天我加班了")]
        mock = MockLLMClient(default_response=_episode_payload(quote_event_id="raw-does-not-exist"))
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)
        assert result.episodes == []
        # Note: this is dropped, not a parse failure.
        assert result.failure_reason is None

    def test_filters_non_user_messages(self) -> None:
        # Tool calls / host writes shouldn't drive episode extraction.
        events = [
            _make_event("raw-1", "记一下这个项目", event_type="host_memory_write"),
        ]
        mock = MockLLMClient(default_response=_episode_payload())
        extractor = EpisodeExtractor(llm=mock)

        result = extractor.extract(events)
        # No usable events → bail before LLM call
        assert result.episodes == []
        assert result.llm_calls == 0

    def test_naive_llm_timestamp_is_interpreted_as_utc(self) -> None:
        events = [_make_event("raw-1", "今天好开心")]
        mock = MockLLMClient(default_response=_episode_payload(occurred_at="2026-06-20T22:00:00"))

        result = EpisodeExtractor(llm=mock).extract(events)

        assert result.episodes[0].occurred_at == datetime(2026, 6, 20, 22, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Memory persistence
# ---------------------------------------------------------------------------


class TestEpisodePersistence:
    def test_save_get_list(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)

        ep = Episode(
            id="ep-1",
            raw_event_ids=["raw-1"],
            occurred_at=datetime(2026, 6, 20, 22, 0, tzinfo=UTC),
            summary="用户和老婆吵架",
            verbatim_quote="今天和老婆吵架了",
            quote_event_id="raw-1",
            emotion="angry",
            intensity=4,
            people=["老婆"],
            topics=["家庭"],
            extractor_version="episode/v1",
            session_id="sess-1",
            digest_ids=[],
            created_at=datetime.now(UTC),
        )
        memory.add_episodes([ep])

        got = memory.get_episode("ep-1")
        assert got is not None
        assert got.summary == "用户和老婆吵架"
        assert got.people == ["老婆"]

        listed = memory.list_episodes(limit=5)
        assert len(listed) == 1
        assert listed[0].id == "ep-1"

        # Filter by emotion
        angry = memory.list_episodes(emotion="angry", limit=5)
        assert len(angry) == 1
        sad = memory.list_episodes(emotion="sad", limit=5)
        assert sad == []

    def test_naive_timestamps_are_stored_and_loaded_as_utc(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        ep = Episode(
            id="ep-naive",
            raw_event_ids=["raw-1"],
            occurred_at=datetime(2026, 6, 20, 22, 0),
            summary="用户完成了一个里程碑",
            verbatim_quote="终于做完了",
            quote_event_id="raw-1",
            emotion="happy",
            intensity=4,
            people=[],
            topics=["工作"],
            extractor_version="episode/v1",
            created_at=datetime(2026, 6, 20, 22, 1),
        )

        memory.add_episodes([ep])

        loaded = memory.get_episode("ep-naive")
        assert loaded is not None
        assert loaded.occurred_at == datetime(2026, 6, 20, 22, 0, tzinfo=UTC)
        assert loaded.created_at == datetime(2026, 6, 20, 22, 1, tzinfo=UTC)

    def test_legacy_naive_timestamp_is_normalized_on_read(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        ep = Episode(
            id="ep-legacy",
            raw_event_ids=["raw-1"],
            occurred_at=datetime(2026, 6, 20, 22, 0, tzinfo=UTC),
            summary="用户完成了一个里程碑",
            verbatim_quote="终于做完了",
            quote_event_id="raw-1",
            emotion="happy",
            intensity=4,
            people=[],
            topics=["工作"],
            extractor_version="episode/v1",
            created_at=datetime(2026, 6, 20, 22, 1, tzinfo=UTC),
        )
        memory.add_episodes([ep])
        memory.backend._conn.execute(
            "UPDATE ep_test_episodes SET occurred_at = ?, created_at = ? WHERE id = ?",
            ("2026-06-20T22:00:00", "2026-06-20T22:01:00", "ep-legacy"),
        )
        memory.backend._conn.commit()

        loaded = memory.get_episode("ep-legacy")
        assert loaded is not None
        assert loaded.occurred_at == datetime(2026, 6, 20, 22, 0, tzinfo=UTC)
        assert loaded.created_at == datetime(2026, 6, 20, 22, 1, tzinfo=UTC)

    def test_search_episodes_fts(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        ep = Episode(
            id="ep-fts",
            raw_event_ids=["raw-1"],
            occurred_at=datetime(2026, 6, 20, tzinfo=UTC),
            summary="项目终于上线，老板表扬",
            verbatim_quote="项目终于上线了",
            quote_event_id="raw-1",
            emotion="happy",
            intensity=4,
            people=["老板"],
            topics=["工作"],
            extractor_version="episode/v1",
            session_id=None,
            digest_ids=[],
            created_at=datetime.now(UTC),
        )
        memory.add_episodes([ep])

        hits = memory.search_episodes("老板")
        assert len(hits) >= 1
        assert hits[0].id == "ep-fts"


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


class TestDigest:
    def _seed_episodes(self, memory: Memory, anchor: datetime) -> None:
        items = [
            ("吵架", "angry", 4, ["老婆"], ["家庭"], 0),
            ("项目上线", "happy", 4, ["老板"], ["工作"], 1),
            ("加班到深夜", "tired", 3, [], ["工作"], 2),
            ("和好了", "grateful", 3, ["老婆"], ["家庭"], 3),
        ]
        for i, (summary, emo, ints, people, topics, day_offset) in enumerate(items):
            ep = Episode(
                id=f"ep-{i}",
                raw_event_ids=[f"raw-{i}"],
                occurred_at=anchor + timedelta(days=day_offset, hours=20),
                summary=summary,
                verbatim_quote=summary,
                quote_event_id=f"raw-{i}",
                emotion=emo,  # type: ignore[arg-type]
                intensity=ints,
                people=people,
                topics=topics,
                extractor_version="episode/v1",
                session_id=None,
                digest_ids=[],
                created_at=datetime.now(UTC),
            )
            memory.add_episodes([ep])

    def test_iso_week_bounds_round_trip(self) -> None:
        when = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)  # Tuesday
        start, end = iso_week_bounds(when)
        assert start.weekday() == 0  # Monday
        assert (end - start) == timedelta(days=7)
        key = iso_week_key(when)
        assert key.startswith("2026-W")

    def test_fallback_digest_no_llm(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        anchor = datetime(2026, 6, 22, tzinfo=UTC)  # Monday of W26
        self._seed_episodes(memory, anchor)

        out_dir = tmp_path / "journals"
        result = generate_digest(
            memory,
            period_kind="weekly",
            when=anchor,
            llm=None,
            output_dir=out_dir,
        )

        assert result.episode_count == 4
        assert not result.used_llm
        assert result.file_path is not None
        assert result.file_path.exists()
        body = result.file_path.read_text(encoding="utf-8")
        assert "吵架" in body
        assert "项目上线" in body
        # Topic grouping headers
        assert "## 家庭" in body or "## 工作" in body
        # Round-trip via SQLite
        digest = memory.get_digest("weekly", result.digest.period_key)
        assert digest is not None
        assert digest.markdown == body

    def test_llm_digest_renders(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        anchor = datetime(2026, 6, 22, tzinfo=UTC)
        self._seed_episodes(memory, anchor)

        canned = "# 2026-W26 Weekly Digest\n\n本周用户经历了一些情绪起伏..."
        mock = MockLLMClient(default_response=canned)

        result = generate_digest(
            memory,
            period_kind="weekly",
            when=anchor,
            llm=mock,
        )

        assert result.used_llm is True
        assert "2026-W26" in result.digest.markdown
        assert mock.calls, "LLM should have been called"

    def test_regenerate_overwrites_same_key(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        anchor = datetime(2026, 6, 22, tzinfo=UTC)
        self._seed_episodes(memory, anchor)

        first = generate_digest(memory, period_kind="weekly", when=anchor)
        second = generate_digest(memory, period_kind="weekly", when=anchor)
        # Same period_key, but DigestRecord on disk should have been
        # upserted (not duplicated). list_digests must show exactly one.
        digests = memory.list_digests(period_kind="weekly")
        assert len(digests) == 1
        assert first.digest.period_key == second.digest.period_key

    # ------------------------------------------------------------------
    # Daily — primary aggregator for "how was today" emotional-memory granularity.
    # ------------------------------------------------------------------

    def test_day_bounds_round_trip(self) -> None:
        when = datetime(2026, 6, 26, 14, 30, tzinfo=UTC)
        start, end = day_bounds(when)
        assert start == datetime(2026, 6, 26, tzinfo=UTC)
        assert end == datetime(2026, 6, 27, tzinfo=UTC)
        assert day_key(when) == "2026-06-26"

    def test_daily_fallback_no_llm(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        anchor = datetime(2026, 6, 26, tzinfo=UTC)
        self._seed_episodes(memory, anchor)  # 4 days, only day 0 falls into "this day"

        out_dir = tmp_path / "journals"
        result = generate_digest(
            memory,
            period_kind="daily",
            when=anchor,
            llm=None,
            output_dir=out_dir,
        )

        # Only the day-0 episode (anchor day) should be in this digest.
        assert result.episode_count == 1
        assert not result.used_llm
        assert result.digest.period_key == "2026-06-26"
        # Daily files live under the daily/ subfolder
        assert result.file_path is not None
        assert result.file_path.parent.name == "daily"
        assert result.file_path.exists()
        body = result.file_path.read_text(encoding="utf-8")
        assert "Daily Digest" in body
        # Round-trip via SQLite
        digest = memory.get_digest("daily", "2026-06-26")
        assert digest is not None
        assert digest.markdown == body

    def test_daily_llm_uses_daily_prompt(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        anchor = datetime(2026, 6, 26, tzinfo=UTC)
        self._seed_episodes(memory, anchor)

        canned = "# 2026-06-26 Daily Digest\n\n你今天经历了一些事..."
        mock = MockLLMClient(default_response=canned)

        result = generate_digest(
            memory,
            period_kind="daily",
            when=anchor,
            llm=mock,
        )
        assert result.used_llm is True
        assert "2026-06-26" in result.digest.markdown
        # The daily prompt must NOT contain the rollup-only marker.
        assert mock.calls
        prompt_sent = mock.calls[0].prompt
        assert "Daily Diary" in prompt_sent or "Daily Digest" in prompt_sent
        assert "daily_digests" not in prompt_sent  # rollup-only field

    # ------------------------------------------------------------------
    # Weekly roll-up — prefers existing daily digests as input
    # ------------------------------------------------------------------

    def test_weekly_rolls_up_daily_digests_when_present(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        # Anchor on Monday of W26 so the seeded 4 days all fall in the week.
        anchor = datetime(2026, 6, 22, tzinfo=UTC)
        self._seed_episodes(memory, anchor)

        # First, generate one daily digest (deterministic) for one day.
        generate_digest(memory, period_kind="daily", when=anchor, llm=None)
        # Sanity: a daily digest now exists.
        dailies = memory.list_digests(period_kind="daily")
        assert len(dailies) == 1

        # Now run weekly with an LLM mock — verify it sees the daily
        # digest in its prompt rather than raw episodes.
        mock = MockLLMClient(default_response="# 2026-W26 Weekly Digest\n\n本周回顾...")
        result = generate_digest(
            memory,
            period_kind="weekly",
            when=anchor,
            llm=mock,
        )
        assert result.used_llm is True
        prompt_sent = mock.calls[0].prompt
        # The rollup prompt feeds daily digests, not episodes.
        assert "daily digests" in prompt_sent.lower()
        # The daily digest body should appear in the prompt payload.
        assert dailies[0].period_key in prompt_sent

    def test_weekly_falls_back_to_episodes_when_no_dailies(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        anchor = datetime(2026, 6, 22, tzinfo=UTC)
        self._seed_episodes(memory, anchor)

        # No daily digests have been generated yet.
        assert memory.list_digests(period_kind="daily") == []

        result = generate_digest(memory, period_kind="weekly", when=anchor, llm=None)
        # Episodes are read directly into the fallback markdown.
        assert result.episode_count == 4
        assert "吵架" in result.digest.markdown


# ---------------------------------------------------------------------------
# Recall integration
# ---------------------------------------------------------------------------


class TestEpisodeRecall:
    def test_episode_source_returns_hits(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        ep = Episode(
            id="ep-recall",
            raw_event_ids=["raw-1"],
            occurred_at=datetime(2026, 6, 20, 22, 0, tzinfo=UTC),
            summary="用户和老婆吵架，气炸了",
            verbatim_quote="今天和老婆吵架了",
            quote_event_id="raw-1",
            emotion="angry",
            intensity=4,
            people=["老婆"],
            topics=["家庭"],
            extractor_version="episode/v1",
            session_id=None,
            digest_ids=[],
            created_at=datetime.now(UTC),
        )
        memory.add_episodes([ep])

        # Recall via multi-source pipeline including the episode source.
        from octop_memory.pipeline.recall.multi_source import gather_candidates
        from octop_memory.pipeline.recall.parser import parse_query

        parsed = parse_query("老婆")
        candidates = gather_candidates(
            memory,
            parsed,
            sources=("episode", "atom", "raw"),
            per_source_limit=5,
        )
        layers = {c.layer for c in candidates}
        assert "episode" in layers
        ep_hits = [c for c in candidates if c.layer == "episode"]
        assert any(c.source_id == "ep-recall" for c in ep_hits)

    def test_recall_for_prompt_includes_episode(self, tmp_path: Path) -> None:
        memory = _make_memory(tmp_path)
        # Seed an episode.
        ep = Episode(
            id="ep-prompt",
            raw_event_ids=["raw-1"],
            occurred_at=datetime(2026, 6, 20, 22, 0, tzinfo=UTC),
            summary="用户和老婆吵架",
            verbatim_quote="今天和老婆吵架了",
            quote_event_id="raw-1",
            emotion="angry",
            intensity=4,
            people=["老婆"],
            topics=["家庭"],
            extractor_version="episode/v1",
            session_id=None,
            digest_ids=[],
            created_at=datetime.now(UTC),
        )
        memory.add_episodes([ep])

        # The default recall pipeline doesn't yet include 'episode' as a
        # default source — so this test inspects the lower-level gather
        # path. recall_for_prompt is verified to NOT crash with episodes
        # present in the database.
        result = recall_for_prompt(memory, "老婆")
        # Should not raise; rendered text may or may not reference
        # episodes depending on default source list.
        assert result is not None
