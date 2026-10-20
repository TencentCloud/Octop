"""Unit tests for the dashboard JSON-RPC surface (M5+ orca dashboard).

Drives :class:`Bridge` directly with hand-built rows to keep tests
deterministic — no LLM, no extractor pipeline. Each test composes a
fresh ``Memory`` with a few candidates / atoms / entities / episodes /
journal entries, then exercises one RPC at a time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octop_memory.adapters.bridge.handlers import (
    ERR_INVALID_PARAMS,
    ERR_PATH_NOT_FOUND,
    Bridge,
)
from octop_memory.core import Memory
from octop_memory.types import (
    AtomCard,
    Candidate,
    Entity,
    Episode,
    JournalEntry,
    RawEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    db_path = tmp_path / "dashboard.sqlite"
    return Memory(
        namespace="test_dash",
        backend="sqlite",
        backend_config={"db_path": str(db_path)},
    )


@pytest.fixture
def bridge(memory: Memory) -> Bridge:
    return Bridge(memory)


def _now(offset_days: float = 0) -> datetime:
    return datetime.now(UTC) - timedelta(days=offset_days)


def _make_candidate(
    *,
    cid: str,
    candidate_type: str = "Preference",
    status: str = "promoted",
    title: str = "test",
    assertion: str = "user prefers test",
    importance: str = "medium",
) -> Candidate:
    return Candidate(
        id=cid,
        raw_event_ids=[],
        candidate_type=candidate_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title=title,
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id="",
        subject_name="user",
        subject_entity_type="User",
        target_entity_id=None,
        confidence="medium",
        importance=importance,  # type: ignore[arg-type]
        recommended_action="promote",
        promotion_reason="test",
        extractor_version="test",
        created_at=_now(),
    )


def _make_entity(eid: str = "ent-user", name: str = "user") -> Entity:
    return Entity(
        id=eid,
        entity_type="User",
        canonical_name=name,
        aliases=[],
        atom_count=0,
        created_at=_now(),
    )


def _make_atom(
    *,
    aid: str,
    candidate_id: str,
    entity_id: str = "ent-user",
    importance: str = "medium",
    assertion: str = "fact",
    days_ago: float = 0,
    deprecated: bool = False,
) -> AtomCard:
    return AtomCard(
        id=aid,
        entity_id=entity_id,
        candidate_id=candidate_id,
        raw_event_ids=[],
        assertion=assertion,
        verbatim_quote=assertion,
        quote_event_id="",
        search_terms=[],
        occurred_at=_now(days_ago),
        confidence="medium",
        importance=importance,  # type: ignore[arg-type]
        created_at=_now(days_ago),
        deprecated_at=_now(days_ago) if deprecated else None,
    )


def _make_episode(
    *,
    eid: str,
    summary: str,
    days_ago: float = 0,
    emotion: str = "happy",
    intensity: int = 3,
    topics: list[str] | None = None,
    people: list[str] | None = None,
) -> Episode:
    return Episode(
        id=eid,
        raw_event_ids=[],
        occurred_at=_now(days_ago),
        summary=summary,
        verbatim_quote=summary,
        quote_event_id="",
        emotion=emotion,  # type: ignore[arg-type]
        intensity=intensity,
        people=people or [],
        topics=topics or [],
        extractor_version="test",
        created_at=_now(days_ago),
    )


def _seed(memory: Memory) -> None:
    """Seed a small but topologically-complete memory for the tests.

    Three atoms (Preference / Task / Fact) hanging off two entities,
    one rejected candidate (so promote/reject paths have something to
    target), one episode, one journal entry.
    """
    e_user = _make_entity("ent-user", "user")
    e_proj = _make_entity("ent-proj", "Bo5heng")
    memory.add_entity(e_user)
    memory.add_entity(e_proj)

    c_pref = _make_candidate(cid="c-pref", candidate_type="Preference", assertion="喜欢喝美式咖啡", importance="high")
    c_task = _make_candidate(
        cid="c-task", candidate_type="Task", assertion="本周写完 memory 设计文档", importance="medium"
    )
    c_fact = _make_candidate(cid="c-fact", candidate_type="Fact", assertion="在 Bo5heng 工作", importance="medium")
    c_pending = _make_candidate(
        cid="c-pending", candidate_type="Decision", assertion="也许要换团队", importance="low", status="pending"
    )
    memory.add_candidate(c_pref)
    memory.add_candidate(c_task)
    memory.add_candidate(c_fact)
    memory.add_candidate(c_pending)

    a_pref = _make_atom(
        aid="a-pref",
        candidate_id="c-pref",
        entity_id="ent-user",
        importance="high",
        assertion="喜欢喝美式咖啡",
        days_ago=1,
    )
    a_task = _make_atom(
        aid="a-task",
        candidate_id="c-task",
        entity_id="ent-user",
        importance="medium",
        assertion="本周写完 memory 设计文档",
        days_ago=2,
    )
    a_fact = _make_atom(
        aid="a-fact",
        candidate_id="c-fact",
        entity_id="ent-proj",
        importance="medium",
        assertion="在 Bo5heng 工作",
        days_ago=10,
    )
    memory.add_atom(a_pref)
    memory.add_atom(a_task)
    memory.add_atom(a_fact)

    ep = _make_episode(
        eid="ep-1",
        summary="and the user laughed",
        days_ago=1,
        emotion="happy",
        intensity=4,
        topics=["family"],
        people=["wife"],
    )
    memory.add_episodes([ep])

    memory.append_journal(
        JournalEntry(
            id="j-1",
            timestamp=_now(0.5),
            action="promote",
            actor="auto",
            target_atom_id="a-pref",
            target_candidate_id="c-pref",
            target_entity_id="ent-user",
            note="seed",
        )
    )

    memory.add_raw_batch(
        [
            RawEvent(
                id="seed-turn-1",
                host="test",
                session_id="s1",
                thread_id="t1",
                user="u",
                timestamp=_now(1),
                event_type="user_message",
                content="今天喝了美式",
            ),
            RawEvent(
                id="seed-turn-2",
                host="test",
                session_id="s1",
                thread_id="t1",
                user="u",
                timestamp=_now(2),
                event_type="user_message",
                content="本周要写完文档",
            ),
            RawEvent(
                id="seed-turn-old",
                host="test",
                session_id="s1",
                thread_id="t1",
                user="u",
                timestamp=_now(10),
                event_type="user_message",
                content="旧消息不应计入近 7 天",
            ),
        ]
    )


def _ok(resp: dict) -> dict:
    """Strip envelope, fail loudly on error."""
    assert "error" not in resp, resp
    return resp["result"]


# ---------------------------------------------------------------------------
# list_atoms
# ---------------------------------------------------------------------------


class TestListAtoms:
    def test_basic_listing(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "list_atoms", "params": {}})
        result = _ok(resp)
        assert result["total"] == 3
        assert len(result["items"]) == 3
        # Each item carries a kind via Candidate join.
        kinds = {item["kind"] for item in result["items"]}
        assert kinds == {"Preference", "Task", "Fact"}

    def test_filter_by_candidate_type(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "list_atoms", "params": {"candidate_type": "Preference"}}
        )
        result = _ok(resp)
        assert result["total"] == 1
        assert result["items"][0]["id"] == "a-pref"
        assert result["items"][0]["kind"] == "Preference"

    def test_filter_by_importance_min(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 3, "method": "list_atoms", "params": {"importance_min": "high"}})
        result = _ok(resp)
        assert result["total"] == 1
        assert result["items"][0]["importance"] == "high"

    def test_filter_by_query(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 4, "method": "list_atoms", "params": {"query": "美式"}})
        result = _ok(resp)
        assert result["total"] == 1
        assert "美式" in result["items"][0]["assertion"]

    def test_pagination(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 5, "method": "list_atoms", "params": {"limit": 2, "offset": 0}})
        result = _ok(resp)
        assert len(result["items"]) == 2
        assert result["has_more"] is True

        resp2 = bridge.handle({"jsonrpc": "2.0", "id": 6, "method": "list_atoms", "params": {"limit": 2, "offset": 2}})
        result2 = _ok(resp2)
        assert len(result2["items"]) == 1
        assert result2["has_more"] is False

    def test_invalid_order(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 7, "method": "list_atoms", "params": {"order": "bogus"}})
        assert resp["error"]["code"] == ERR_INVALID_PARAMS


# ---------------------------------------------------------------------------
# list_entities / list_episodes / list_journal
# ---------------------------------------------------------------------------


class TestListEntities:
    def test_basic(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "list_entities", "params": {}})
        result = _ok(resp)
        assert result["total"] == 2
        names = {item["canonical_name"] for item in result["items"]}
        assert names == {"user", "Bo5heng"}

    def test_query_filter(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "list_entities", "params": {"query": "bo5"}})
        result = _ok(resp)
        assert result["total"] == 1
        assert result["items"][0]["canonical_name"] == "Bo5heng"


class TestListEpisodes:
    def test_basic(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "list_episodes", "params": {}})
        result = _ok(resp)
        assert result["total"] == 1
        assert result["items"][0]["emotion"] == "happy"

    def test_intensity_min(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        # intensity 4 >= 4 → kept
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "list_episodes", "params": {"intensity_min": 4}})
        assert _ok(resp)["total"] == 1
        # intensity 4 < 5 → empty
        resp = bridge.handle({"jsonrpc": "2.0", "id": 3, "method": "list_episodes", "params": {"intensity_min": 5}})
        assert _ok(resp)["total"] == 0

    def test_topic_filter(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 4, "method": "list_episodes", "params": {"topic": "family"}})
        assert _ok(resp)["total"] == 1

    def test_mixed_legacy_timezone_rows_sort_without_error(self, memory: Memory, bridge: Bridge) -> None:
        memory.add_episodes(
            [
                _make_episode(eid="ep-aware", summary="aware", days_ago=1),
                _make_episode(eid="ep-naive", summary="naive", days_ago=2),
            ]
        )
        memory.backend._conn.execute(
            "UPDATE test_dash_episodes SET occurred_at = ? WHERE id = ?",
            ("2026-06-20T22:00:00", "ep-naive"),
        )
        memory.backend._conn.commit()

        result = _ok(bridge.handle({"jsonrpc": "2.0", "id": 5, "method": "list_episodes", "params": {}}))

        assert result["total"] == 2
        assert all(item["occurred_at"].endswith("+00:00") for item in result["items"])


class TestListJournal:
    def test_basic_newest_first(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        # Add a second, older entry to verify ordering.
        memory.append_journal(
            JournalEntry(
                id="j-0",
                timestamp=_now(5),
                action="reject",
                actor="user",
                target_candidate_id="c-pending",
                note="older",
            )
        )
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "list_journal", "params": {}})
        result = _ok(resp)
        assert result["total"] == 2
        assert result["items"][0]["id"] == "j-1"  # newest first
        # enriched with the acted-on memory's text (atom a-pref's assertion),
        # so the dashboard can show *which* memory, not just a generic memory row.
        assert result["items"][0]["target_summary"] == "喜欢喝美式咖啡"

    def test_action_filter(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "list_journal", "params": {"action": "promote"}})
        assert _ok(resp)["total"] == 1


# ---------------------------------------------------------------------------
# get_raw_event / get_candidate
# ---------------------------------------------------------------------------


class TestSingleFetch:
    def test_get_candidate_ok(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "get_candidate", "params": {"candidate_id": "c-pref"}}
        )
        result = _ok(resp)
        assert result["candidate_type"] == "Preference"

    def test_get_candidate_missing(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "get_candidate", "params": {"candidate_id": "nope"}})
        assert resp["error"]["code"] == ERR_PATH_NOT_FOUND

    def test_get_raw_event_missing(self, memory: Memory, bridge: Bridge) -> None:
        resp = bridge.handle({"jsonrpc": "2.0", "id": 3, "method": "get_raw_event", "params": {"event_id": "nope"}})
        assert resp["error"]["code"] == ERR_PATH_NOT_FOUND

    def test_get_raw_event_ok(self, memory: Memory, bridge: Bridge) -> None:
        memory.add_raw_batch(
            [
                RawEvent(
                    id="evt-1",
                    host="test",
                    session_id="s1",
                    thread_id="t1",
                    user="u",
                    timestamp=_now(),
                    event_type="user_message",
                    content="hello",
                )
            ]
        )
        resp = bridge.handle({"jsonrpc": "2.0", "id": 4, "method": "get_raw_event", "params": {"event_id": "evt-1"}})
        result = _ok(resp)
        assert result["content"] == "hello"


class TestListRawEvents:
    def _seed_raw(self, memory: Memory) -> None:
        memory.add_raw_batch(
            [
                RawEvent(
                    id="r1",
                    host="test",
                    session_id="s1",
                    thread_id="t1",
                    user="u",
                    timestamp=_now(2),
                    event_type="user_message",
                    content="项目截止日期是周五",
                ),
                RawEvent(
                    id="r2",
                    host="test",
                    session_id="s1",
                    thread_id="t1",
                    user="u",
                    timestamp=_now(1),
                    event_type="assistant_message",
                    content="好的，我记下了",
                ),
                RawEvent(
                    id="r3",
                    host="test",
                    session_id="s2",
                    thread_id="t2",
                    user="u",
                    timestamp=_now(0),
                    event_type="user_message",
                    content="帮我查一下天气",
                ),
            ]
        )

    def test_basic_newest_first(self, memory: Memory, bridge: Bridge) -> None:
        self._seed_raw(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "list_raw_events", "params": {}})
        result = _ok(resp)
        assert result["total"] == 3
        # list_raw orders by timestamp DESC → r3 (newest) first.
        assert result["items"][0]["id"] == "r3"
        assert result["items"][0]["content"] == "帮我查一下天气"

    def test_filter_by_session(self, memory: Memory, bridge: Bridge) -> None:
        self._seed_raw(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "list_raw_events", "params": {"session_id": "s1"}})
        result = _ok(resp)
        assert result["total"] == 2
        assert {i["id"] for i in result["items"]} == {"r1", "r2"}

    def test_filter_by_event_type(self, memory: Memory, bridge: Bridge) -> None:
        self._seed_raw(memory)
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "list_raw_events", "params": {"event_type": "assistant_message"}}
        )
        result = _ok(resp)
        assert result["total"] == 1
        assert result["items"][0]["id"] == "r2"

    def test_query_filter(self, memory: Memory, bridge: Bridge) -> None:
        self._seed_raw(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 4, "method": "list_raw_events", "params": {"query": "天气"}})
        result = _ok(resp)
        assert result["total"] == 1
        assert result["items"][0]["id"] == "r3"

    def test_pagination(self, memory: Memory, bridge: Bridge) -> None:
        self._seed_raw(memory)
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 5, "method": "list_raw_events", "params": {"limit": 2, "offset": 0}}
        )
        result = _ok(resp)
        assert len(result["items"]) == 2
        assert result["has_more"] is True

    def test_invalid_event_type(self, memory: Memory, bridge: Bridge) -> None:
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 6, "method": "list_raw_events", "params": {"event_type": "bogus"}}
        )
        assert resp["error"]["code"] == ERR_INVALID_PARAMS


# ---------------------------------------------------------------------------
# stats_*
# ---------------------------------------------------------------------------


class TestStats:
    def test_counts(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "stats_counts", "params": {}})
        result = _ok(resp)
        assert result["atoms"] == 3
        assert result["entities"] == 2
        assert result["episodes"] == 1
        assert result["candidates_pending"] == 1
        # All atoms / entity / episode created within the last 7 days.
        assert result["atoms_delta_7d"] >= 2  # a-pref and a-task within 7d (a-fact is 10d ago)
        assert result["entities_delta_7d"] == 2
        assert result["episodes_delta_7d"] == 1
        assert result["last_extract_run"] is None

    def test_growth_shape(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "stats_growth", "params": {"days": 7}})
        result = _ok(resp)
        assert len(result["series"]) == 7
        assert {"date", "atoms", "episodes", "entities", "turns"} <= set(result["series"][0].keys())
        # Sum of atoms across the 7-day window includes the two recent atoms.
        total_atoms = sum(d["atoms"] for d in result["series"])
        assert total_atoms == 2
        # Two recent user_message turns; the 10-day-old one is outside the window.
        total_turns = sum(d["turns"] for d in result["series"])
        assert total_turns == 2

    def test_atom_kinds(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 3, "method": "stats_atom_kinds", "params": {}})
        result = _ok(resp)
        kinds = {row["kind"]: row["count"] for row in result["series"]}
        assert kinds == {"Preference": 1, "Task": 1, "Fact": 1}

    def test_recent_journal(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 4, "method": "recent_journal", "params": {"limit": 5}})
        result = _ok(resp)
        assert len(result["items"]) == 1
        assert result["items"][0]["action"] == "promote"


# ---------------------------------------------------------------------------
# Write actions
# ---------------------------------------------------------------------------


class TestWriteActions:
    def test_deprecate_atom(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "deprecate_atom",
                "params": {"atom_id": "a-fact", "reason": "outdated"},
            }
        )
        result = _ok(resp)
        assert result["status"] == "deprecated"
        # Re-deprecating fails cleanly.
        resp2 = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "deprecate_atom", "params": {"atom_id": "a-fact"}})
        assert resp2["error"]["code"] == ERR_PATH_NOT_FOUND

    def test_create_atom_new_entity(self, memory: Memory, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "create_atom",
                "params": {
                    "assertion": "喜欢早起跑步",
                    "entity_name": "作息",
                    "entity_type": "Fact",
                    "kind": "Preference",
                },
            }
        )
        result = _ok(resp)
        assert result["status"] == "created"
        assert result["created_entity"] is True
        assert result["atom"]["assertion"] == "喜欢早起跑步"
        assert result["atom"]["kind"] == "Preference"
        assert result["entity"]["canonical_name"] == "作息"

    def test_replace_atom(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "replace_atom",
                "params": {"atom_id": "a-fact", "assertion": "用户其实更喜欢茶"},
            }
        )
        result = _ok(resp)
        assert result["status"] == "replaced"
        assert result["old_atom_id"] == "a-fact"
        assert result["atom"]["assertion"] == "用户其实更喜欢茶"
        assert result["atom"]["id"] != "a-fact"
        loaded = memory.get_atom("a-fact")
        assert loaded is not None
        assert loaded.superseded_by == result["atom"]["id"]

    def test_replace_missing_atom(self, memory: Memory, bridge: Bridge) -> None:
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "replace_atom",
                "params": {"atom_id": "nope", "assertion": "x"},
            }
        )
        assert resp["error"]["code"] == ERR_PATH_NOT_FOUND

    def test_reject_candidate(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "reject_candidate",
                "params": {"candidate_id": "c-pending", "reason": "not relevant"},
            }
        )
        result = _ok(resp)
        assert result["status"] == "rejected"
        # Journal entry written.
        latest = memory.list_journal(limit=10)
        assert any(e.action == "reject" for e in latest)

    def test_reject_already_promoted(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "reject_candidate", "params": {"candidate_id": "c-pref"}}
        )
        # c-pref status is "promoted" → not rejectable.
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_promote_conflict_supersedes_old_atom(self, memory: Memory, bridge: Bridge) -> None:
        memory.add_entity(_make_entity("ent-user", "user"))
        raw = memory.add_raw(content="喜欢喝美式咖啡", event_type="user_message", host="t")
        pending = _make_candidate(
            cid="c-old",
            candidate_type="Preference",
            assertion="喜欢喝美式咖啡",
            status="pending",
        )
        pending.raw_event_ids = [raw.id]
        pending.quote_event_id = raw.id
        conflict = _make_candidate(
            cid="c-conflict",
            candidate_type="Preference",
            assertion="不喜欢喝美式咖啡",
            status="pending",
        )
        conflict.raw_event_ids = [raw.id]
        conflict.quote_event_id = raw.id
        memory.add_candidate(pending)
        memory.add_candidate(conflict)
        first = memory.promote_candidates([pending])
        assert first.promoted == 1
        old_atoms = memory.list_atoms(include_deprecated=False)
        assert len(old_atoms) == 1
        memory.update_candidate_status("c-conflict", status="conflict")

        resp = bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "promote_candidate",
                "params": {"candidate_id": "c-conflict"},
            }
        )
        result = _ok(resp)
        assert result["promoted"] == 1
        live = memory.list_atoms(include_deprecated=False)
        assert len(live) == 1
        assert live[0].assertion == "不喜欢喝美式咖啡"
        old = memory.get_atom(old_atoms[0].id)
        assert old is not None and old.deprecated_at is not None
        assert old.superseded_by == live[0].id

    def test_promote_already_promoted_rejected(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "promote_candidate", "params": {"candidate_id": "c-pref"}}
        )
        assert resp["error"]["code"] == ERR_INVALID_PARAMS


# ---------------------------------------------------------------------------
# terminal_*
# ---------------------------------------------------------------------------


class TestTerminalAggregators:
    def test_about_me(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": "terminal_about_me", "params": {"limit": 5}})
        result = _ok(resp)
        assert len(result["items"]) == 1
        assert result["items"][0]["kind"] == "Preference"

    def test_current_focus_within_7d(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 2, "method": "terminal_current_focus", "params": {}})
        result = _ok(resp)
        assert len(result["items"]) == 1
        assert result["items"][0]["kind"] == "Task"

    def test_things_you_told_me(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 3, "method": "terminal_things_you_told_me", "params": {}})
        result = _ok(resp)
        kinds = {item["kind"] for item in result["items"]}
        assert kinds == {"Fact"}  # No Decisions promoted in seed.

    def test_recent_stories(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 4, "method": "terminal_recent_stories", "params": {}})
        result = _ok(resp)
        assert len(result["items"]) == 1

    def test_entities(self, memory: Memory, bridge: Bridge) -> None:
        _seed(memory)
        resp = bridge.handle({"jsonrpc": "2.0", "id": 5, "method": "terminal_entities", "params": {}})
        result = _ok(resp)
        assert len(result["items"]) == 2
