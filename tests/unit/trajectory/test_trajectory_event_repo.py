"""TrajectoryEventRepo — append, cursor page, duplicate event_id."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.trajectory.types import TrajectoryEvent


def _event(
    *,
    event_id: str,
    seq: int,
    kind: str = "user",
    thread_id: str = "T1",
    summary: str = "",
    payload: dict[str, Any] | None = None,
    is_error: bool = False,
    turn_id: str | None = None,
    request_seq: int | None = None,
) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=event_id,
        thread_id=thread_id,
        agent_id="A1",
        seq=seq,
        ts=float(seq),
        kind=kind,  # type: ignore[arg-type]
        turn_id=turn_id,
        request_seq=request_seq,
        is_error=is_error,
        summary=summary,
        payload=payload or {},
    )


def _repo(tmp_path: Path) -> TrajectoryEventRepo:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return TrajectoryEventRepo(db)


def test_append_pages_before_seq_and_rejects_duplicate_event_id(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = _event(event_id="e1", seq=1, kind="user", summary="hi")
    second = _event(event_id="e2", seq=2, kind="assistant", summary="hello")

    assert repo.append(first) is True
    assert repo.append(second) is True

    page = repo.list_before("T1", before_seq=None, limit=10, kinds=None)
    assert [event.event_id for event in page] == ["e1", "e2"]
    assert page[0] == first
    assert page[1] == second

    older = repo.list_before("T1", before_seq=2, limit=10, kinds=None)
    assert [event.event_id for event in older] == ["e1"]

    assert repo.append(first) is False
    assert repo.get("e1") == first


def test_list_before_filters_kinds_and_limit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for seq, kind in ((1, "user"), (2, "assistant"), (3, "tool"), (4, "assistant")):
        assert repo.append(_event(event_id=f"e{seq}", seq=seq, kind=kind)) is True

    latest = repo.list_before("T1", before_seq=None, limit=2, kinds=None)
    assert [event.seq for event in latest] == [3, 4]

    assistants = repo.list_before("T1", before_seq=None, limit=10, kinds=["assistant"])
    assert [event.seq for event in assistants] == [2, 4]


def test_get_delete_and_iter_for_export(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = _event(event_id="e1", seq=1, payload={"n": 1})
    second = _event(event_id="e2", seq=2, is_error=True, turn_id="t", request_seq=7)
    assert repo.append(first) is True
    assert repo.append(second) is True
    assert repo.append(_event(event_id="other", seq=1, thread_id="T2")) is True

    assert repo.get("missing") is None
    exported = list(repo.iter_for_export("T1"))
    assert [event.event_id for event in exported] == ["e1", "e2"]
    assert exported[1].is_error is True
    assert exported[1].turn_id == "t"
    assert exported[1].request_seq == 7

    assert repo.delete_for_thread("T1") == 2
    assert repo.list_before("T1", before_seq=None, limit=10, kinds=None) == []
    assert repo.get("other") is not None
