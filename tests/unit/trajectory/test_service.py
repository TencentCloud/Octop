"""TrajectoryService — observe never raises; list / metrics / export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.trajectory.live import TrajectoryLiveBus
from octop.infra.trajectory.service import TrajectoryService
from octop.infra.trajectory.store import TrajectoryStore


def _service(tmp_path: Path) -> tuple[TrajectoryService, TrajectoryLiveBus]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
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
