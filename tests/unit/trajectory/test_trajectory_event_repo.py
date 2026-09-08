"""TrajectoryEventRepo — append, cursor page, duplicate event_id."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.trajectory.types import TrajectoryEvent


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
    _seed_threads(db, "T1", "T2")
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


def test_thread_delete_cascades_trajectory_events(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    with db.connect() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(trajectory_events)").fetchall()
    assert any(str(row["table"]) == "threads" for row in fks)

    user_id = UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="A1", user_id=user_id, name="Agent")
    ThreadRepo(db).insert(
        thread_id="T1",
        agent_id="A1",
        user_id=user_id,
        channel_type="dashboard",
        session_key="sk",
        last_active=0,
    )
    repo = TrajectoryEventRepo(db)
    assert repo.append(_event(event_id="e1", seq=1, summary="hi")) is True

    ThreadRepo(db).delete("T1")
    assert repo.list_before("T1", before_seq=None, limit=10, kinds=None) == []


def test_list_from_seq_and_prune_older_than_user_turns(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for seq, kind in (
        (1, "system"),
        (2, "user"),
        (3, "assistant"),
        (4, "user"),
        (5, "assistant"),
        (6, "user"),
    ):
        assert repo.append(_event(event_id=f"e{seq}", seq=seq, kind=kind)) is True

    from_seq = repo.list_from_seq("T1", from_seq=4, limit=10)
    assert [event.seq for event in from_seq] == [4, 5, 6]

    deleted = repo.prune_older_than_user_turns("T1", 2)
    assert deleted > 0
    remaining = repo.list_before("T1", before_seq=None, limit=20, kinds=None)
    assert [event.seq for event in remaining] == [4, 5, 6]
