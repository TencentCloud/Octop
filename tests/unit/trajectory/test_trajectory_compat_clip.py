"""ArchiveTrajectoryStore must bound oversized events on every backend it writes.

The persist caps in ``trajectory.settings`` exist to bound SQLite row size. The
v2 archive keeps trajectory events in ``documents`` rows of ``history_v2.sqlite``
and writes them through ``HistoryStore.put_document`` directly, so the caps have
to be applied before routing, not inside the legacy repo.
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
from octop.infra.history.trajectory.settings import PAYLOAD_MAX_CHARS, SUMMARY_MAX_CHARS
from octop.infra.history.trajectory.types import TrajectoryEvent
from octop.infra.history.trajectory_compat import ArchiveTrajectoryStore

_OVERSIZED_SUMMARY = SUMMARY_MAX_CHARS + 20
_OVERSIZED_CONTENT = PAYLOAD_MAX_CHARS + 50


@pytest.fixture
def archive(tmp_path: Path):
    db = SqlitePool(tmp_path / "legacy.sqlite")
    run_migrations(db)
    user_id = UserRepo(db).create(username="clip-user", password_hash="h", role="user")
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


def _oversized_event(event_id: str, *, thread_id: str = "T1") -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id=event_id,
        thread_id=thread_id,
        agent_id="A1",
        seq=1,
        ts=1.0,
        kind="tool",
        turn_id=None,
        request_seq=None,
        is_error=False,
        summary="s" * _OVERSIZED_SUMMARY,
        payload={"name": "big", "content": "x" * _OVERSIZED_CONTENT},
    )


def test_v2_archive_append_applies_the_persist_caps(archive: HistoryArchive) -> None:
    archive.begin("A1", "T1")  # opens the v2 segment every new turn routes into
    store = ArchiveTrajectoryStore(archive)

    assert store.append(_oversized_event("big")) is True

    stored = store.get("big")
    assert stored is not None
    assert len(stored.summary) <= SUMMARY_MAX_CHARS
    assert len(str(stored.payload["content"])) <= PAYLOAD_MAX_CHARS


def test_v2_archive_and_legacy_repo_agree_on_the_caps(archive: HistoryArchive) -> None:
    archive.begin("A1", "T1")  # T1 = v2 archived; T2 keeps the legacy repo path
    store = ArchiveTrajectoryStore(archive)

    assert store.append(_oversized_event("v2-event", thread_id="T1")) is True
    assert store.append(_oversized_event("legacy-event", thread_id="T2")) is True

    v2_event = store.get("v2-event")
    legacy_event = store.get("legacy-event")
    assert v2_event is not None and legacy_event is not None
    assert len(v2_event.summary) == len(legacy_event.summary) <= SUMMARY_MAX_CHARS
    assert (
        len(str(v2_event.payload["content"]))
        == len(str(legacy_event.payload["content"]))
        <= PAYLOAD_MAX_CHARS
    )


def test_v2_archive_append_leaves_the_caller_event_intact(archive: HistoryArchive) -> None:
    archive.begin("A1", "T1")
    store = ArchiveTrajectoryStore(archive)
    event = _oversized_event("big")

    store.append(event)

    assert len(event.summary) == _OVERSIZED_SUMMARY
    assert len(event.payload["content"]) == _OVERSIZED_CONTENT
