"""TrajectoryStore — thin repo wrapper; duplicate event_id is a no-op."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.trajectory.store import TrajectoryStore
from octop.infra.trajectory.types import TrajectoryEvent


def _event(
    *,
    event_id: str,
    seq: int,
    kind: str = "user",
    thread_id: str = "T1",
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=event_id,
        thread_id=thread_id,
        agent_id="A1",
        seq=seq,
        ts=float(seq),
        kind=kind,  # type: ignore[arg-type]
        turn_id=None,
        request_seq=None,
        is_error=False,
        summary=summary,
        payload=payload or {},
    )


def _store(tmp_path: Path) -> TrajectoryStore:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return TrajectoryStore(TrajectoryEventRepo(db))


def test_append_is_idempotent_on_duplicate_event_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    event = _event(event_id="e1", seq=1, summary="hi")

    assert store.append(event) is True
    assert store.append(event) is False

    page = store.list_before("T1", before_seq=None, limit=10, kinds=None)
    assert [item.event_id for item in page] == ["e1"]
    assert store.get("e1") == event
