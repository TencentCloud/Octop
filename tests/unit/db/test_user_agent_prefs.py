"""tests/unit/db/test_user_agent_prefs.py — schema v21 per-user agent prefs."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.user_agent_prefs import UserAgentPrefRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "prefs.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def repo(db: SqlitePool) -> UserAgentPrefRepo:
    return UserAgentPrefRepo(db)


@pytest.fixture
def user_id(db: SqlitePool) -> int:
    return UserRepo(db).create(username="alice", password_hash="h", role="user")


def test_get_prefs_empty(repo: UserAgentPrefRepo, user_id: int):
    assert repo.get_prefs(user_id) == {}


def test_set_pin_upserts_and_keeps_sort_order(repo: UserAgentPrefRepo, user_id: int):
    aid = new_ulid()
    repo.reorder(user_id, [aid, new_ulid()])
    repo.set_pin(user_id, aid, True)
    prefs = repo.get_prefs(user_id)
    assert prefs[aid].pinned is True
    assert prefs[aid].sort_order == 0  # reorder survived the pin upsert

    repo.set_pin(user_id, aid, False)
    assert repo.get_prefs(user_id)[aid].pinned is False


def test_reorder_writes_index_sequence(repo: UserAgentPrefRepo, user_id: int):
    a, b, c = new_ulid(), new_ulid(), new_ulid()
    repo.reorder(user_id, [c, a, b])
    prefs = repo.get_prefs(user_id)
    assert prefs[a].sort_order == 1
    assert prefs[b].sort_order == 2
    assert prefs[c].sort_order == 0
    # reorder never flips pinning on
    assert all(not p.pinned for p in prefs.values())


def test_reorder_collapses_duplicates_and_skips_empty(repo: UserAgentPrefRepo, user_id: int):
    a, b = new_ulid(), new_ulid()
    repo.reorder(user_id, [a, "", b, a])
    prefs = repo.get_prefs(user_id)
    assert {k: v.sort_order for k, v in prefs.items()} == {a: 0, b: 1}

    repo.reorder(user_id, [])
    assert repo.get_prefs(user_id).keys() == {a, b}  # empty write is a no-op


def test_reorder_last_write_wins(repo: UserAgentPrefRepo, user_id: int):
    a, b = new_ulid(), new_ulid()
    repo.reorder(user_id, [a, b])
    repo.reorder(user_id, [b, a])
    prefs = repo.get_prefs(user_id)
    assert prefs[b].sort_order == 0
    assert prefs[a].sort_order == 1


def test_prefs_are_isolated_per_user(repo: UserAgentPrefRepo, db: SqlitePool, user_id: int):
    other = UserRepo(db).create(username="bob", password_hash="h", role="user")
    a, b = new_ulid(), new_ulid()
    repo.reorder(user_id, [b, a])
    repo.set_pin(user_id, a, True)

    # bob's view is untouched by alice's arrangement
    assert repo.get_prefs(other) == {}
    # alice's rows unchanged by bob's emptiness
    prefs = repo.get_prefs(user_id)
    assert prefs[b].sort_order == 0
    assert prefs[a].pinned is True


def test_list_by_user_prefs_ordering(db: SqlitePool, repo: UserAgentPrefRepo, user_id: int):
    agents = AgentRepo(db)
    ids = [new_ulid() for _ in range(4)]  # creation order: 0,1,2,3
    for i, aid in enumerate(ids):
        agents.create(agent_id=aid, user_id=user_id, name=f"bot-{i}")

    # default (no prefs): creation order — unchanged behavior
    plain = [r.agent_id for r in agents.list_by_user(user_id)]
    assert plain == ids

    # pin the last-created agent + manually order the middle two
    repo.set_pin(user_id, ids[3], True)
    repo.reorder(user_id, [ids[1], ids[0]])

    ordered = [r.agent_id for r in agents.list_by_user(user_id, prefs_user_id=user_id)]
    # ids[3] pinned first; manually ordered ids[1], ids[0] next;
    # ids[2] (never ordered) falls back to creation order, last
    assert ordered == [ids[3], ids[1], ids[0], ids[2]]

    # explicit None keeps legacy order even when prefs exist
    legacy = [r.agent_id for r in agents.list_by_user(user_id, prefs_user_id=None)]
    assert legacy == ids


def test_list_shared_uses_viewer_prefs_not_owner(
    db: SqlitePool, repo: UserAgentPrefRepo, user_id: int
):
    """Shared rows must sort by the VIEWER's prefs — owner prefs never leak."""
    agents = AgentRepo(db)
    viewer = UserRepo(db).create(username="viewer", password_hash="h", role="user")
    s1, s2 = new_ulid(), new_ulid()
    agents.create(agent_id=s1, user_id=user_id, name="shared-1")
    agents.create(agent_id=s2, user_id=user_id, name="shared-2")
    agents.set_shared(s1, True)
    agents.set_shared(s2, True)

    # owner pins s2, but viewer has no prefs → viewer still sees creation order
    repo.set_pin(user_id, s2, True)
    viewer_view = [
        r.agent_id for r in agents.list_shared(exclude_user_id=viewer, prefs_user_id=viewer)
    ]
    assert viewer_view == [s1, s2]

    # viewer pins s1 → only the viewer's list flips
    repo.set_pin(viewer, s1, True)
    viewer_view = [
        r.agent_id for r in agents.list_shared(exclude_user_id=viewer, prefs_user_id=viewer)
    ]
    assert viewer_view == [s1, s2]

    # owner's own list still reflects the owner's pin of s2
    owner_view = [r.agent_id for r in agents.list_by_user(user_id, prefs_user_id=user_id)]
    assert owner_view == [s2, s1]


def test_list_all_ignores_prefs_by_default(db: SqlitePool, repo: UserAgentPrefRepo, user_id: int):
    agents = AgentRepo(db)
    a, b = new_ulid(), new_ulid()
    agents.create(agent_id=a, user_id=user_id, name="a")
    agents.create(agent_id=b, user_id=user_id, name="b")
    repo.set_pin(user_id, b, True)
    repo.reorder(user_id, [b, a])
    # admin global view: plain creation order regardless of personal prefs
    assert [r.agent_id for r in agents.list_all()] == [a, b]
