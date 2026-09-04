"""TrajectoryStore — thin repo wrapper; duplicate event_id is a no-op."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.trajectory.store import TrajectoryStore
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
    _seed_threads(db, "T1")
    return TrajectoryStore(TrajectoryEventRepo(db))


def test_append_is_idempotent_on_duplicate_event_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    event = _event(event_id="e1", seq=1, summary="hi")

    assert store.append(event) is True
    assert store.append(event) is False

    page = store.list_before("T1", before_seq=None, limit=10, kinds=None)
    assert [item.event_id for item in page] == ["e1"]
    assert store.get("e1") == event


def test_append_clips_oversized_payload_and_summary(tmp_path: Path) -> None:
    from octop.infra.trajectory.settings import PAYLOAD_MAX_CHARS, SUMMARY_MAX_CHARS

    store = _store(tmp_path)
    huge = "x" * (PAYLOAD_MAX_CHARS + 50)
    event = _event(
        event_id="big",
        seq=1,
        summary="s" * (SUMMARY_MAX_CHARS + 20),
        payload={"content": huge, "args": huge},
    )
    assert store.append(event) is True
    stored = store.get("big")
    assert stored is not None
    assert len(stored.summary) <= SUMMARY_MAX_CHARS
    assert len(str(stored.payload["content"])) <= PAYLOAD_MAX_CHARS
    assert len(str(stored.payload["args"])) <= PAYLOAD_MAX_CHARS
