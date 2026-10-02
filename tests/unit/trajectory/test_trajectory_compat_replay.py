"""Resume replay has to see the events the v2 archive owns.

``ArchiveTrajectoryStore`` overrides every read method that can be answered by
the v2 archive — ``list_before``, ``get``, ``iter_for_export`` — because a v2
thread's events are written into ``history_v2.sqlite`` and never into
``trajectory_events``. The SSE endpoint resumes a dropped stream through a
different member, ``list_from_seq`` (a browser reconnect carries
``Last-Event-ID``), and that one was left with the inherited repo-only query.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.history.service import HistoryArchive
from octop.infra.history.store import HistoryStore
from octop.infra.history.trajectory.types import TrajectoryEvent
from octop.infra.history.trajectory_compat import ArchiveTrajectoryStore


@pytest.fixture
def archive(tmp_path: Path):
    db = SqlitePool(tmp_path / "legacy.sqlite")
    run_migrations(db)
    user_id = UserRepo(db).create(username="replay-user", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="A1", user_id=user_id, name="Agent")
    threads = ThreadRepo(db)
    for thread_id in ("T1", "T2"):
        threads.insert(
            thread_id=thread_id,
            agent_id="A1",
            user_id=user_id,
            channel_type="dashboard",
            session_key=f"sk-{thread_id}",
            last_active=0,
        )
    store = HistoryStore(tmp_path / "history.sqlite", identity="test")
    yield HistoryArchive(store, ThreadMessageRepo(db), TrajectoryEventRepo(db), enabled=True)
    store.close()
    db.close()


def _event(seq: int, *, thread_id: str) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=f"e{thread_id}{seq}",
        thread_id=thread_id,
        agent_id="A1",
        seq=seq,
        ts=float(seq),
        kind="tool",
        turn_id=None,
        request_seq=None,
        is_error=False,
        summary=f"step {seq}",
        payload={"n": seq},
    )


def test_resume_replays_the_events_a_v2_thread_already_emitted(archive: HistoryArchive) -> None:
    archive.begin("A1", "T1")  # T1 becomes the v2 (archived) thread
    store = ArchiveTrajectoryStore(archive)
    for seq in (1, 2, 3, 4):
        assert store.append(_event(seq, thread_id="T1")) is True

    replayed = store.list_from_seq("T1", from_seq=3, limit=10)

    assert [event.seq for event in replayed] == [3, 4]


def test_resume_still_replays_a_legacy_thread(archive: HistoryArchive) -> None:
    archive.begin("A1", "T1")  # only T1 is v2; T2 stays on the legacy repo path
    store = ArchiveTrajectoryStore(archive)
    for seq in (1, 2, 3):
        assert store.append(_event(seq, thread_id="T2")) is True

    replayed = store.list_from_seq("T2", from_seq=2, limit=10)

    assert [event.seq for event in replayed] == [2, 3]


def test_resume_returns_the_oldest_due_events_up_to_the_limit(
    archive: HistoryArchive,
) -> None:
    archive.begin("A1", "T1")
    store = ArchiveTrajectoryStore(archive)
    for seq in (1, 2, 3, 4):
        assert store.append(_event(seq, thread_id="T1")) is True

    replayed = store.list_from_seq("T1", from_seq=1, limit=2)

    assert [event.seq for event in replayed] == [1, 2]


def test_resume_with_a_non_positive_limit_replays_nothing(archive: HistoryArchive) -> None:
    archive.begin("A1", "T1")
    store = ArchiveTrajectoryStore(archive)
    assert store.append(_event(1, thread_id="T1")) is True

    assert store.list_from_seq("T1", from_seq=1, limit=0) == []
