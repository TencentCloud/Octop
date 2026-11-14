"""The v1 trajectory store applies persistence bounds without mutating caller events."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.history.trajectory.settings import PAYLOAD_MAX_CHARS, SUMMARY_MAX_CHARS
from octop.infra.history.trajectory.store import TrajectoryStore
from octop.infra.history.trajectory.types import TrajectoryEvent

_OVERSIZED_SUMMARY = SUMMARY_MAX_CHARS + 20
_OVERSIZED_CONTENT = PAYLOAD_MAX_CHARS + 50


@pytest.fixture
def store(tmp_path: Path):
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
    yield TrajectoryStore(TrajectoryEventRepo(db))
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


def test_append_applies_the_persist_caps(store: TrajectoryStore) -> None:
    assert store.append(_oversized_event("big")) is True

    stored = store.get("big")
    assert stored is not None
    assert len(stored.summary) <= SUMMARY_MAX_CHARS
    assert len(str(stored.payload["content"])) <= PAYLOAD_MAX_CHARS


def test_append_leaves_the_caller_event_intact(store: TrajectoryStore) -> None:
    event = _oversized_event("big")

    store.append(event)

    assert len(event.summary) == _OVERSIZED_SUMMARY
    assert len(event.payload["content"]) == _OVERSIZED_CONTENT
