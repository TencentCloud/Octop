# tests/unit/db/test_agent_is_shared.py
from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.users import UserRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_is_shared_default_zero_and_list_shared(db):
    run_migrations(db)  # or use fixture that already migrated
    UserRepo(db).create(username="u1", password_hash="h", role="user")
    UserRepo(db).create(username="u2", password_hash="h", role="user")
    repo = AgentRepo(db)
    repo.create(agent_id="a1", user_id=1, name="mine")
    repo.create(agent_id="a2", user_id=2, name="theirs")
    repo.set_shared("a2", True)
    rows = repo.list_shared(exclude_user_id=1)
    assert [r.agent_id for r in rows] == ["a2"]
    assert rows[0].is_shared == 1
