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


def test_list_shared_keeps_globally_shared_agents(db):
    """An agent with ``user_id IS NULL`` is shared with everyone.

    ``agents.user_id`` is nullable (``001_initial.sql``) and ``AgentCreateSpec``
    defaults ``user_id`` to ``None``, so the globally-shared shape is the one
    ``agents/manager.py`` documents as *"Shared agents (user_id IS NULL)"*.
    Excluding one user's own agents must therefore keep those rows: SQL
    ``user_id != ?`` evaluates to NULL — not TRUE — for a NULL ``user_id`` and
    drops the row.
    """
    UserRepo(db).create(username="u1", password_hash="h", role="user")
    UserRepo(db).create(username="u2", password_hash="h", role="user")
    repo = AgentRepo(db)
    repo.create(agent_id="global", user_id=None, name="global")
    repo.set_shared("global", True)
    repo.create(agent_id="u2-own", user_id=2, name="theirs")
    repo.set_shared("u2-own", True)

    rows = repo.list_shared(exclude_user_id=1)
    names = {r.agent_id for r in rows}

    assert "global" in names, "globally shared agent disappeared for another user"
    assert "u2-own" in names
    # Still excludes the caller's own shared agent.
    UserRepo(db).create(username="u3", password_hash="h", role="user")
    repo.create(agent_id="u1-own", user_id=1, name="mine")
    repo.set_shared("u1-own", True)
    assert "u1-own" not in {r.agent_id for r in repo.list_shared(exclude_user_id=1)}


def test_list_shared_without_exclude_returns_null_owner_rows(db):
    """The NULL-owner row is also present when no exclusion is requested."""
    UserRepo(db).create(username="u1", password_hash="h", role="user")
    repo = AgentRepo(db)
    repo.create(agent_id="global", user_id=None, name="global")
    repo.set_shared("global", True)

    rows = repo.list_shared()
    assert [r.agent_id for r in rows] == ["global"]
    assert rows[0].user_id is None
