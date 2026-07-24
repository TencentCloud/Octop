"""tests/unit/test_repo_agents.py"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo, AgentRow
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def user_id(db: SqlitePool) -> int:
    return UserRepo(db).create(username="alice", password_hash="h", role="admin")


@pytest.fixture
def repo(db: SqlitePool) -> AgentRepo:
    return AgentRepo(db)


def test_create_and_get(repo: AgentRepo, user_id: int):
    aid = new_ulid()
    repo.create(agent_id=aid, user_id=user_id, name="bot")
    row = repo.get(aid)
    assert isinstance(row, AgentRow)
    assert row.agent_id == aid
    assert isinstance(row.id, int)
    assert row.user_id == user_id
    assert row.name == "bot"
    assert row.enabled == 1


def test_unique_name_per_user(repo: AgentRepo, user_id: int):
    # Partial unique index: per-user names must differ; system agents (user_id NULL) are exempt.
    repo.create(agent_id=new_ulid(), user_id=user_id, name="bot-a")
    repo.create(agent_id=new_ulid(), user_id=user_id, name="bot-b")
    rows = repo.list_by_user(user_id)
    assert len(rows) == 2


def test_duplicate_name_same_user_raises(repo: AgentRepo, user_id: int):
    repo.create(agent_id=new_ulid(), user_id=user_id, name="bot")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(agent_id=new_ulid(), user_id=user_id, name="bot")


def test_system_agents_allow_duplicate_names(repo: AgentRepo):
    repo.create(agent_id=new_ulid(), user_id=None, name="system")
    repo.create(agent_id=new_ulid(), user_id=None, name="system")
    rows = repo.list_all()
    assert sum(1 for r in rows if r.name == "system" and r.user_id is None) == 2


def test_list_by_user(repo: AgentRepo, user_id: int, db: SqlitePool):
    other_uid = UserRepo(db).create(username="bob", password_hash="h", role="user")
    repo.create(agent_id=new_ulid(), user_id=user_id, name="a1")
    repo.create(agent_id=new_ulid(), user_id=user_id, name="a2")
    repo.create(agent_id=new_ulid(), user_id=other_uid, name="b1")
    rows = repo.list_by_user(user_id)
    assert len(rows) == 2
    assert all(r.user_id == user_id for r in rows)


def test_set_state(repo: AgentRepo, user_id: int):
    aid = new_ulid()
    repo.create(agent_id=aid, user_id=user_id, name="bot")
    repo.set_state(aid, "running")
    row = repo.get(aid)
    assert row.last_state == "running"
    assert row.last_error is None
    repo.set_state(aid, "error", error="oops")
    row = repo.get(aid)
    assert row.last_state == "error"
    assert row.last_error == "oops"


def test_update_config(repo: AgentRepo, user_id: int):
    aid = new_ulid()
    repo.create(agent_id=aid, user_id=user_id, name="bot")
    repo.update_config(aid, description="my agent", default_model="gpt-4")
    row = repo.get(aid)
    assert row.description == "my agent"
    assert row.default_model == "gpt-4"
    assert row.name == "bot"  # unchanged


def test_update_config_can_clear_default_model(repo: AgentRepo, user_id: int):
    aid = new_ulid()
    repo.create(agent_id=aid, user_id=user_id, name="bot", default_model="gpt-4")
    repo.update_config(aid, default_model=None)
    row = repo.get(aid)
    assert row.default_model is None


def test_cascade_delete_on_user(repo: AgentRepo, user_id: int, db: SqlitePool):
    aid = new_ulid()
    repo.create(agent_id=aid, user_id=user_id, name="bot")
    assert repo.get(aid) is not None
    with db.transaction() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    assert repo.get(aid) is None
