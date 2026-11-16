"""Peer threads get ``last_active`` once the seeded question lands."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.agents.teams.team_manager import TeamManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


class _Projection:
    """Minimal thread_messages stand-in: accepts the first append."""

    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.rows: dict[str, list[Any]] = {}
        self.appended: list[tuple[str, list[Any]]] = []

    def projection_status(self, thread_id: str) -> str:
        return self.status.get(thread_id, "pending")

    def mark_projection(self, thread_id: str, status: str) -> None:
        self.status[thread_id] = status

    def page(self, thread_id: str, *, limit: int, offset: int) -> list[Any]:
        return self.rows.get(thread_id, [])[:limit]

    def append_if_ready(self, thread_id: str, messages: list[Any]) -> None:
        self.appended.append((thread_id, messages))
        self.rows.setdefault(thread_id, []).extend(messages)


@pytest.fixture
def registry(tmp_path: Path) -> ThreadRegistry:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="agt_peer", user_id=1, name="Member")
    return ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))


def _manager(registry: ThreadRegistry, projection: _Projection) -> TeamManager:
    return TeamManager(
        agent_manager=MagicMock(),
        thread_registry=registry,
        user_repo=MagicMock(),
        thread_message_repo=projection,
    )


def test_seeded_member_question_bumps_last_active(
    registry: ThreadRegistry,
) -> None:
    projection = _Projection()
    manager = _manager(registry, projection)
    tid = registry.create_thread(
        agent_id="agt_peer",
        user_id=1,
        channel_type="dashboard",
        session_key="agt_peer:dashboard:1:team:thr_room",
    )
    assert registry.get_thread(tid).last_active == 0

    manager._seed_member_user_question(tid, "summarise the room so far")

    assert projection.appended, "seed should reach the history projection"
    assert registry.get_thread(tid).last_active > 0


def test_failed_seed_leaves_last_active_untouched(
    registry: ThreadRegistry,
) -> None:
    projection = _Projection()

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("projection down")

    projection.append_if_ready = boom  # type: ignore[method-assign]
    manager = _manager(registry, projection)
    tid = registry.create_thread(
        agent_id="agt_peer",
        user_id=1,
        channel_type="dashboard",
        session_key="agt_peer:dashboard:1:team:thr_room2",
    )

    manager._seed_member_user_question(tid, "anything")

    assert registry.get_thread(tid).last_active == 0
