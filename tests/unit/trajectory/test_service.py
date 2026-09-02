"""TrajectoryService — observe never raises; list / metrics / export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def test_observe_aggregates_tokens_into_one_assistant(tmp_path: Path) -> None:
    service, bus = _service(tmp_path)
    queue = bus.subscribe("T1")

    for piece in ("Hel", "lo ", "world"):
        service.observe_chunk(
            "A1",
            "T1",
            {"type": "token", "node": "agent", "content": piece, "request_seq": 3},
        )

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "assistant"
    assert ev.summary == "Hello world"
    assert ev.payload["content"] == "Hello world"
    assert ev.request_seq == 3

    published = [queue.get_nowait() for _ in range(queue.qsize())]
    assert len(published) >= 1
    assert published[0]["event_id"] == ev.event_id
    assert all(item["event_id"] == ev.event_id for item in published)


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
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "tool"
    assert ev.payload["call_id"] == "call_1"
    assert ev.payload["name"] == "read_file"
    assert ev.payload["args"] == '{"path":"a.py"}'
    assert ev.payload["result"] == "ok"


def test_observe_does_not_store_state_snapshot(tmp_path: Path) -> None:
    service, _bus = _service(tmp_path)
    service.observe_chunk("A1", "T1", {"type": "user", "content": "hi"})
    service.observe_chunk("A1", "T1", {"type": "state_snapshot", "data": {"messages": []}})
    service.observe_chunk("A1", "T1", {"type": "reasoning", "content": "think"})

    events = service.list_events("T1", before_seq=None, limit=10, kinds=None)
    assert len(events) == 1
    assert events[0].kind == "user"
