"""TrajectoryService — observe never raises; list / metrics / export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.trajectory.live import TrajectoryLiveBus
from octop.infra.trajectory.service import TrajectoryService
from octop.infra.trajectory.store import TrajectoryStore


def _seed_threads(db: SqlitePool, *thread_ids: str, agent_id: str = "A1") -> None:
    user_id = UserRepo(db).create(username="traj-user", password_hash="h", role="user")
    AgentRepo(db).create(agent_id=agent_id, user_id=user_id, name="Agent")
    threads = ThreadRepo(db)
    for tid in thread_ids:
        threads.insert(
            thread_id=tid,
            agent_id=agent_id,
            user_id=user_id,
            channel_type="dashboard",
            session_key=f"sk-{tid}",
            last_active=0,
        )


def _service(tmp_path: Path) -> tuple[TrajectoryService, TrajectoryLiveBus]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    _seed_threads(db, "T1")
    bus = TrajectoryLiveBus()
    service = TrajectoryService(TrajectoryStore(TrajectoryEventRepo(db)), bus)
    return service, bus


def test_observe_chunk_swallows_projector_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise RuntimeError("projector down")

    monkeypatch.setattr("octop.infra.trajectory.service.project_harness_chunk", boom)
    service, _bus = _service(tmp_path)

    service.observe_chunk("A1", "T1", {"type": "user", "content": "hi"})


def test_observe_chunk_appends_publishes_and_exports(tmp_path: Path) -> None:
    service, bus = _service(tmp_path)
    queue = bus.subscribe("T1")

    service.observe_chunk("A1", "T1", {"type": "user", "content": "hello"})

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert len(events) == 1
    assert events[0].kind == "user"
    assert "hello" in events[0].summary
    assert service.get_event(events[0].event_id) == events[0]

    published = queue.get_nowait()
    assert published["event_id"] == events[0].event_id
    assert published["kind"] == "user"

    metrics = service.metrics("T1")
    assert metrics.turns == 1
    assert metrics.steps == 1

    lines = list(service.export_jsonl("T1"))
    assert len(lines) == 1
    exported = json.loads(lines[0])
    assert exported["event_id"] == events[0].event_id
    assert exported["kind"] == "user"


def test_observe_aggregates_tokens_without_per_token_db_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("octop.infra.trajectory.service.time.monotonic", lambda: 1.0)
    service, bus = _service(tmp_path)
    queue = bus.subscribe("T1")
    append = MagicMock(side_effect=service._store.append)  # noqa: SLF001
    upsert = MagicMock(side_effect=service._store.upsert)  # noqa: SLF001
    service._store.append = append  # type: ignore[method-assign]  # noqa: SLF001
    service._store.upsert = upsert  # type: ignore[method-assign]  # noqa: SLF001

    for piece in ("Hel", "lo ", "world"):
        service.observe_chunk(
            "A1",
            "T1",
            {"type": "token", "node": "agent", "content": piece, "request_seq": 3},
        )

    assert append.call_count == 1
    assert upsert.call_count == 0
    service.finish_turn("T1")
    assert upsert.call_count == 1

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "assistant"
    assert ev.summary == "Hello world"
    assert ev.payload["content"] == "Hello world"
    assert ev.request_seq == 3

    published = [queue.get_nowait() for _ in range(queue.qsize())]
    assert len(published) == 2
    assert published[0]["event_id"] == ev.event_id
    assert all(item["event_id"] == ev.event_id for item in published)


def test_finish_turn_persists_usage_and_marks_final_live_snapshot(tmp_path: Path) -> None:
    service, bus = _service(tmp_path)
    queue = bus.subscribe("T1")
    service.observe_chunk("A1", "T1", {"type": "token", "content": "done"})

    service.finish_turn(
        "T1",
        {"input_tokens": 12, "output_tokens": 3, "cache_read_tokens": 4},
    )

    event = service.list_events("T1", before_seq=None, limit=1, kinds=None)[0]
    assert event.payload["input_tokens"] == 12
    assert "_final" not in event.payload
    published = [queue.get_nowait() for _ in range(queue.qsize())]
    assert published[-1]["_final"] is True


def test_finish_turn_attaches_usage_when_tools_follow_assistant(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)
    service.observe_chunk("A1", "T1", {"type": "token", "content": "checking"})
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "c1", "name": "read", "args": "{}"},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_result", "id": "c1", "name": "read", "content": "ok"},
    )

    service.finish_turn("T1", {"input_tokens": 7, "output_tokens": 2})

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assistant = next(event for event in events if event.kind == "assistant")
    assert assistant.payload["input_tokens"] == 7
    assert assistant.payload["output_tokens"] == 2


def test_metrics_reuses_short_lived_cache(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)
    service.observe_chunk("A1", "T1", {"type": "user", "content": "hello"})
    iterate = MagicMock(side_effect=service._store.iter_for_export)  # noqa: SLF001
    service._store.iter_for_export = iterate  # type: ignore[method-assign]  # noqa: SLF001

    service.metrics("T1")
    service.metrics("T1")
    assert iterate.call_count == 1

    service.metrics("T1", refresh=True)
    assert iterate.call_count == 2


def test_observe_merges_tool_call_and_result(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)

    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "call_1", "name": "read_", "args": '{"p'},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "call_1", "name": "file", "args": 'ath":"a.py"}'},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_result", "id": "call_1", "name": "read_file", "content": "ok"},
    )

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert [event.kind for event in events] == ["assistant", "tool"]
    parent, ev = events
    assert parent.payload.get("tool_call_only") is True
    assert parent.summary == "(tool call only)"
    assert ev.kind == "tool"
    assert ev.payload["call_id"] == "call_1"
    assert ev.payload["name"] == "read_file"
    assert ev.payload["args"] == '{"path":"a.py"}'
    assert ev.payload["result"] == "ok"


def test_observe_tool_burst_shares_one_tool_call_only_parent(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)

    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "c1", "name": "ls", "args": "{}"},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_result", "id": "c1", "name": "ls", "content": "a"},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "c2", "name": "ls", "args": "{}"},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_result", "id": "c2", "name": "ls", "content": "b"},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "token", "node": "agent", "content": "done", "request_seq": 1},
    )

    events = service.list_events("T1", before_seq=None, limit=20, kinds=None)
    assert [event.kind for event in events] == ["assistant", "tool", "tool", "assistant"]
    assert events[0].payload.get("tool_call_only") is True
    assert events[-1].summary == "done"
    assert events[-1].payload.get("tool_call_only") is not True


def test_observe_does_not_synthesize_parent_when_assistant_text_precedes_tools(
    tmp_path: Path,
) -> None:
    service, _bus = _service(tmp_path)
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "token", "node": "agent", "content": "Looking…", "request_seq": 2},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "c1", "name": "read", "args": "{}"},
    )
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_result", "id": "c1", "name": "read", "content": "x"},
    )

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert [event.kind for event in events] == ["assistant", "tool"]
    assert events[0].summary == "Looking…"
    assert events[0].payload.get("tool_call_only") is not True


def test_observe_does_not_store_state_snapshot(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)
    service.observe_chunk("A1", "T1", {"type": "user", "content": "hi"})
    service.observe_chunk("A1", "T1", {"type": "state_snapshot", "data": {"messages": []}})
    service.observe_chunk("A1", "T1", {"type": "reasoning", "content": "think"})

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert len(events) == 1
    assert events[0].kind == "user"


def test_has_kind_detects_system_events(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)
    assert service.has_kind("T1", "system") is False
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "system", "label": "Initial System Prompt", "content": "You are Octop."},
    )
    assert service.has_kind("T1", "system") is True
    assert service.has_kind("T1", "context") is False


def test_observe_assigns_turn_id_and_wall_clock_ts(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "system", "label": "Initial System Prompt", "content": "sys"},
    )
    service.observe_chunk("A1", "T1", {"type": "user", "content": "hi"})
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "token", "node": "agent", "content": "hello"},
    )
    service.observe_chunk("A1", "T1", {"type": "user", "content": "again"})

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert [event.kind for event in events] == ["system", "user", "assistant", "user"]
    assert events[0].turn_id is None
    assert events[0].ts > 0
    assert events[1].turn_id == "T1:turn:1"
    assert events[2].turn_id == "T1:turn:1"
    assert events[3].turn_id == "T1:turn:2"
    assert events[1].ts > 0


def test_observe_tool_result_records_tool_duration_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _bus = _service(tmp_path)
    clock = {"t": 1000.0}

    def fake_time() -> float:
        return clock["t"]

    monkeypatch.setattr("octop.infra.trajectory.service.time.time", fake_time)
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_call_chunk", "id": "c1", "name": "ls", "args": "{}"},
    )
    clock["t"] = 1000.25
    service.observe_chunk(
        "A1",
        "T1",
        {"type": "tool_result", "id": "c1", "name": "ls", "content": "ok"},
    )

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    tool = next(event for event in events if event.kind == "tool")
    assert tool.payload.get("tool_duration_ms") == pytest.approx(250.0)
