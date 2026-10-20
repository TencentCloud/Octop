"""Tests for M1 L0 raw events: schema, CRUD, FTS, batch insert, GC, CLI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory
from octop_memory.pipeline.lifecycle import run_gc
from octop_memory.types import RawEvent


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})


# ---------------------------------------------------------------------------
# add_raw / get_raw / list_raw
# ---------------------------------------------------------------------------


def test_add_raw_default_fields(memory: Memory) -> None:
    """Default host=manual, timestamp=now(UTC), payload={}."""
    before = datetime.now(UTC)
    event = memory.add_raw("hello", event_type="user_message")
    after = datetime.now(UTC)

    assert event.id  # uuid generated
    assert event.host == "manual"
    assert event.event_type == "user_message"
    assert event.content == "hello"
    assert event.payload == {}
    assert before <= event.timestamp <= after


def test_add_raw_full_fields(memory: Memory) -> None:
    ts = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    event = memory.add_raw(
        "test content",
        event_type="user_message",
        host="openclaw",
        session_id="s1",
        thread_id="t1",
        user="alice",
        timestamp=ts,
        payload={"role": "user"},
    )
    assert event.host == "openclaw"
    assert event.session_id == "s1"
    assert event.thread_id == "t1"
    assert event.user == "alice"
    assert event.timestamp == ts
    assert event.payload == {"role": "user"}


def test_get_raw_round_trip(memory: Memory) -> None:
    event = memory.add_raw("abc", event_type="manual", payload={"k": "v"})
    fetched = memory.get_raw(event.id)
    assert fetched is not None
    assert fetched.id == event.id
    assert fetched.content == "abc"
    assert fetched.payload == {"k": "v"}


def test_get_raw_missing(memory: Memory) -> None:
    assert memory.get_raw("nope") is None


# ---------------------------------------------------------------------------
# Immutability — strict insert; no update API
# ---------------------------------------------------------------------------


def test_raw_event_strict_insert(memory: Memory) -> None:
    """Re-inserting same id must raise (immutable / append-only)."""
    event = RawEvent(
        id="fixed",
        host="test",
        session_id=None,
        thread_id=None,
        user=None,
        timestamp=datetime.now(UTC),
        event_type="manual",
        content="first",
        payload={},
    )
    memory.backend.save_raw(event)
    with pytest.raises(sqlite3.IntegrityError):
        memory.backend.save_raw(event)


# ---------------------------------------------------------------------------
# Payload isolation
# ---------------------------------------------------------------------------


def test_raw_payload_isolated_from_input_dict(memory: Memory) -> None:
    p = {"k": "v"}
    event = memory.add_raw("x", event_type="manual", payload=p)
    p["k"] = "mutated"  # caller mutates after add
    fetched = memory.get_raw(event.id)
    assert fetched is not None
    assert fetched.payload == {"k": "v"}


# ---------------------------------------------------------------------------
# list_raw filtering and ordering
# ---------------------------------------------------------------------------


def test_list_raw_orders_desc_by_timestamp(memory: Memory) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    memory.add_raw("a", event_type="manual", timestamp=base)
    memory.add_raw("b", event_type="manual", timestamp=base + timedelta(hours=1))
    memory.add_raw("c", event_type="manual", timestamp=base + timedelta(hours=2))

    events = memory.list_raw()
    assert [e.content for e in events] == ["c", "b", "a"]


def test_list_raw_filter_by_host(memory: Memory) -> None:
    memory.add_raw("from openclaw", event_type="manual", host="openclaw")
    memory.add_raw("from hermes", event_type="manual", host="hermes")
    memory.add_raw("from manual", event_type="manual", host="manual")

    events = memory.list_raw(host="openclaw")
    assert len(events) == 1
    assert events[0].content == "from openclaw"


def test_list_raw_filter_by_session_and_type(memory: Memory) -> None:
    memory.add_raw("s1 user", event_type="user_message", session_id="s1")
    memory.add_raw("s1 ai", event_type="assistant_message", session_id="s1")
    memory.add_raw("s2 user", event_type="user_message", session_id="s2")

    events = memory.list_raw(session_id="s1", event_type="user_message")
    assert len(events) == 1
    assert events[0].content == "s1 user"


def test_list_raw_time_range(memory: Memory) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    memory.add_raw("old", event_type="manual", timestamp=base)
    memory.add_raw("mid", event_type="manual", timestamp=base + timedelta(days=1))
    memory.add_raw("new", event_type="manual", timestamp=base + timedelta(days=2))

    events = memory.list_raw(
        after=base + timedelta(hours=12),
        before=base + timedelta(days=1, hours=12),
    )
    assert [e.content for e in events] == ["mid"]


def test_list_raw_limit(memory: Memory) -> None:
    for i in range(5):
        memory.add_raw(f"event {i}", event_type="manual")
    events = memory.list_raw(limit=3)
    assert len(events) == 3


# ---------------------------------------------------------------------------
# search_raw — FTS
# ---------------------------------------------------------------------------


def test_search_raw_finds_by_content(memory: Memory) -> None:
    memory.add_raw("Hermes adapter uses enhancement mode", event_type="user_message")
    memory.add_raw("OpenClaw replace mode discussion", event_type="user_message")
    memory.add_raw("Just lunch chat", event_type="user_message")

    hits = memory.search_raw("Hermes")
    assert len(hits) == 1
    assert "Hermes" in hits[0].content


def test_search_raw_fts_clears_after_delete(memory: Memory) -> None:
    """FTS index must be kept in sync with main table (delete trigger)."""
    e1 = memory.add_raw("unique-marker-zzz", event_type="manual")
    assert memory.search_raw("unique-marker-zzz")
    stats = run_gc(memory, orphan_raw_days=0, now=datetime.now(UTC) + timedelta(seconds=1))
    assert stats.orphan_raw_events_deleted >= 1
    assert memory.get_raw(e1.id) is None
    # No ghost in FTS
    assert memory.search_raw("unique-marker-zzz") == []


# ---------------------------------------------------------------------------
# batch insert (single fsync)
# ---------------------------------------------------------------------------


def test_save_raw_batch(memory: Memory) -> None:
    events = [
        RawEvent(
            id=f"id-{i}",
            host="test",
            session_id="s",
            thread_id=None,
            user=None,
            timestamp=datetime(2026, 6, 1, 10, i, tzinfo=UTC),
            event_type="manual",
            content=f"event {i}",
            payload={"i": i},
        )
        for i in range(10)
    ]
    memory.add_raw_batch(events)
    listed = memory.list_raw(limit=20)
    assert len(listed) == 10
    # Round-trip a payload
    fetched = memory.get_raw("id-3")
    assert fetched is not None
    assert fetched.payload == {"i": 3}


def test_save_raw_batch_empty_is_noop(memory: Memory) -> None:
    memory.add_raw_batch([])
    assert memory.list_raw() == []


# ---------------------------------------------------------------------------
# CLI round-trip
# ---------------------------------------------------------------------------


class TestRawCLI:
    def _run(self, runner: CliRunner, db_path: str, *args: str, json_mode: bool = False):
        flags = ["--db", db_path, "--namespace", "test"]
        if json_mode:
            flags.append("--json")
        return runner.invoke(main, [*flags, *args])

    def test_add_show_list_search(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()

        result = self._run(
            runner,
            db_path,
            "raw",
            "add",
            "--content",
            "Hermes adapter discussion",
            "--event-type",
            "user_message",
            "--host",
            "openclaw",
            "--session-id",
            "s1",
            "--payload",
            '{"role":"user"}',
            json_mode=True,
        )
        assert result.exit_code == 0, result.output
        eid = json.loads(result.output)["data"]["id"]

        # show
        result = self._run(runner, db_path, "raw", "show", eid, json_mode=True)
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["host"] == "openclaw"
        assert data["payload"] == {"role": "user"}

        # list
        result = self._run(runner, db_path, "raw", "list", json_mode=True)
        assert result.exit_code == 0
        assert len(json.loads(result.output)["data"]["events"]) == 1

        # search
        result = self._run(runner, db_path, "raw", "search", "Hermes", json_mode=True)
        assert result.exit_code == 0
        assert len(json.loads(result.output)["data"]["events"]) == 1

    def test_add_invalid_payload(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()
        result = self._run(
            runner,
            db_path,
            "raw",
            "add",
            "--content",
            "x",
            "--payload",
            "[1,2,3]",
        )
        assert result.exit_code != 0
        assert "JSON object" in result.output

    def test_show_missing_event(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()
        result = self._run(runner, db_path, "raw", "show", "nope")
        assert result.exit_code != 0

    def test_list_filter_by_event_type(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "cli.db")
        runner = CliRunner()

        for et in ["user_message", "assistant_message", "tool_call"]:
            self._run(runner, db_path, "raw", "add", "--content", et, "--event-type", et)

        result = self._run(
            runner,
            db_path,
            "raw",
            "list",
            "--event-type",
            "user_message",
            json_mode=True,
        )
        assert result.exit_code == 0
        events = json.loads(result.output)["data"]["events"]
        assert len(events) == 1
        assert events[0]["event_type"] == "user_message"
