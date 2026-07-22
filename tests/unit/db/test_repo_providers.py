"""tests/unit/test_repo_providers.py"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.providers import ProviderRepo, ProviderRow
from octop.infra.db.repos.users import UserRepo


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def user_id(db: SqlitePool) -> int:
    return UserRepo(db).create(username="alice", password_hash="h", role="admin")


@pytest.fixture
def repo(db: SqlitePool) -> ProviderRepo:
    return ProviderRepo(db)


def test_create_and_get(repo: ProviderRepo):
    pid = repo.create(name="openai", kind="openai")
    row = repo.get(pid)
    assert isinstance(row, ProviderRow)
    assert row.name == "openai"
    assert row.kind == "openai"


def test_unique_name(repo: ProviderRepo):
    repo.create(name="openai", kind="openai")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(name="openai", kind="openai")


def test_list_all(repo: ProviderRepo):
    repo.create(name="openai", kind="openai")
    repo.create(name="anthropic", kind="anthropic")
    names = {r.name for r in repo.list_all()}
    assert "openai" in names
    assert "anthropic" in names


def test_get_by_name(repo: ProviderRepo):
    repo.create(name="openai", kind="openai")
    assert repo.get_by_name("openai").name == "openai"
    assert repo.get_by_name("missing") is None


def test_update(repo: ProviderRepo):
    pid = repo.create(name="openai", kind="openai")
    repo.update(pid, note="updated")
    row = repo.get(pid)
    assert row.note == "updated"
    assert row.kind == "openai"  # unchanged


def test_delete(repo: ProviderRepo):
    pid = repo.create(name="openai", kind="openai")
    repo.delete(pid)
    assert repo.get(pid) is None


# ---------------------------------------------------------------------------
# find_referencing_agent_ids
# ---------------------------------------------------------------------------


def test_find_referencing_agent_ids_returns_agents_that_use_provider(db: SqlitePool, user_id: int):
    from octop.infra.db.repos.agents import AgentRepo

    repo = ProviderRepo(db)
    agent_repo = AgentRepo(db)

    agent_repo.create(
        agent_id="a1",
        user_id=user_id,
        name="bot",
        persona_mbti=None,
        config_json='{"providers": ["openai"]}',
    )
    agent_repo.create(
        agent_id="a2",
        user_id=user_id,
        name="other",
        persona_mbti=None,
        config_json='{"providers": ["anthropic"]}',
    )

    refs = repo.find_referencing_agent_ids(agent_repo, "openai")
    assert refs == ["a1"]


def test_find_referencing_agent_ids_returns_empty_when_no_references(db: SqlitePool, user_id: int):
    from octop.infra.db.repos.agents import AgentRepo

    repo = ProviderRepo(db)
    agent_repo = AgentRepo(db)

    agent_repo.create(
        agent_id="a1",
        user_id=user_id,
        name="bot",
        persona_mbti=None,
        config_json='{"providers": ["anthropic"]}',
    )

    refs = repo.find_referencing_agent_ids(agent_repo, "openai")
    assert refs == []


def test_find_referencing_agent_ids_handles_multiple_providers_per_agent(
    db: SqlitePool, user_id: int
):
    from octop.infra.db.repos.agents import AgentRepo

    repo = ProviderRepo(db)
    agent_repo = AgentRepo(db)

    agent_repo.create(
        agent_id="a1",
        user_id=user_id,
        name="bot",
        persona_mbti=None,
        config_json='{"providers": ["openai", "anthropic"]}',
    )

    assert repo.find_referencing_agent_ids(agent_repo, "openai") == ["a1"]
    assert repo.find_referencing_agent_ids(agent_repo, "anthropic") == ["a1"]
    assert repo.find_referencing_agent_ids(agent_repo, "bedrock") == []


def test_find_referencing_agent_ids_handles_null_config_json(db: SqlitePool, user_id: int):
    from octop.infra.db.repos.agents import AgentRepo

    repo = ProviderRepo(db)
    agent_repo = AgentRepo(db)

    agent_repo.create(
        agent_id="a1",
        user_id=user_id,
        name="bot",
        persona_mbti=None,
        config_json=None,
    )

    # Must not raise, must return empty
    assert repo.find_referencing_agent_ids(agent_repo, "openai") == []
