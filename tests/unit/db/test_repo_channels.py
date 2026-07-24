"""tests/unit/test_repo_channels.py"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.channels import ChannelRepo, ChannelRow
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def agent_id(db: SqlitePool) -> str:
    uid = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    aid = new_ulid()
    AgentRepo(db).create(agent_id=aid, user_id=uid, name="bot")
    return aid


@pytest.fixture
def user_id(db: SqlitePool) -> int:
    return UserRepo(db).get_by_username("alice").id


@pytest.fixture
def repo(db: SqlitePool) -> ChannelRepo:
    return ChannelRepo(db)


def test_create_and_get(repo: ChannelRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        channel_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        kind="slack",
        name="main",
        config_json="{}",
    )
    row = repo.get(cid)
    assert isinstance(row, ChannelRow)
    assert row.channel_id == cid
    assert row.kind == "slack"
    assert row.enabled == 1


def test_get_by_agent_and_name(repo: ChannelRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        channel_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        kind="weixin",
        name="weixin",
        config_json="{}",
    )
    row = repo.get_by_agent_and_name(agent_id, "weixin")
    assert row is not None
    assert row.channel_id == cid
    assert repo.get_by_agent_and_name(agent_id, "missing") is None


def test_unique_agent_name(repo: ChannelRepo, agent_id: str, user_id: int):
    repo.create(
        channel_id=new_ulid(),
        agent_id=agent_id,
        user_id=user_id,
        kind="slack",
        name="main",
        config_json="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(
            channel_id=new_ulid(),
            agent_id=agent_id,
            user_id=user_id,
            kind="discord",
            name="main",
            config_json="{}",
        )


def test_list_by_agent(repo: ChannelRepo, agent_id: str, user_id: int):
    repo.create(
        channel_id=new_ulid(),
        agent_id=agent_id,
        user_id=user_id,
        kind="slack",
        name="ch1",
        config_json="{}",
    )
    repo.create(
        channel_id=new_ulid(),
        agent_id=agent_id,
        user_id=user_id,
        kind="discord",
        name="ch2",
        config_json="{}",
    )
    rows = repo.list_by_agent(agent_id)
    assert len(rows) == 2


def test_update_partial(repo: ChannelRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        channel_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        kind="slack",
        name="main",
        config_json="{}",
    )
    repo.update(cid, config_json='{"token":"x"}', enabled=False)
    row = repo.get(cid)
    assert row.config_json == '{"token":"x"}'
    assert row.enabled == 0
    assert row.kind == "slack"  # unchanged


def test_delete(repo: ChannelRepo, agent_id: str, user_id: int):
    cid = new_ulid()
    repo.create(
        channel_id=cid,
        agent_id=agent_id,
        user_id=user_id,
        kind="slack",
        name="main",
        config_json="{}",
    )
    repo.delete(cid)
    assert repo.get(cid) is None
