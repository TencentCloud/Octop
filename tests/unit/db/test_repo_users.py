"""tests/unit/test_repo_users.py"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo, UserRow


@pytest.fixture
def repo(tmp_path: Path) -> UserRepo:
    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    return UserRepo(db)


def test_last_login_backfill_from_audit_does_not_clobber(repo: UserRepo):
    uid = repo.create(username="alice", password_hash="h", role="user")
    created = repo.get(uid)
    assert created is not None
    assert created.last_login_at is None
    with repo._db.transaction() as conn:
        conn.execute(
            "INSERT INTO audit_log(ts, actor, action, target, payload) VALUES (?, ?, ?, ?, ?)",
            (1_700_000_000, "alice", "auth.login", None, None),
        )
    run_migrations(repo._db)
    filled = repo.get(uid)
    assert filled is not None
    assert filled.last_login_at == 1_700_000_000
    repo.touch_last_login(uid, now=1_800_000_000)
    run_migrations(repo._db)
    kept = repo.get(uid)
    assert kept is not None
    assert kept.last_login_at == 1_800_000_000


def test_create_and_get(repo: UserRepo):
    uid = repo.create(username="alice", password_hash="h", role="admin", display_name="Alice")
    row = repo.get(uid)
    assert isinstance(row, UserRow)
    assert row.username == "alice"
    assert row.role == "admin"
    assert row.disabled == 0
    assert row.created_at <= int(time.time())


def test_get_by_username(repo: UserRepo):
    repo.create(username="bob", password_hash="h", role="user")
    assert repo.get_by_username("bob").username == "bob"
    assert repo.get_by_username("nobody") is None


def test_unique_username(repo: UserRepo):
    repo.create(username="a", password_hash="h", role="user")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(username="a", password_hash="h2", role="user")


def test_list_filters_disabled(repo: UserRepo):
    a = repo.create(username="a", password_hash="h", role="user")
    repo.create(username="b", password_hash="h", role="user")
    repo.set_disabled(a, True)
    rows = repo.list(include_disabled=False)
    assert [r.username for r in rows] == ["b"]
    assert len(repo.list(include_disabled=True)) == 2


def test_set_role(repo: UserRepo):
    uid = repo.create(username="a", password_hash="h", role="user")
    repo.set_role(uid, "admin")
    assert repo.get(uid).role == "admin"


def test_set_password_hash(repo: UserRepo):
    uid = repo.create(username="a", password_hash="h1", role="user")
    assert repo.get(uid).password_version == 0
    repo.set_password_hash(uid, "h2")
    row = repo.get(uid)
    assert row is not None
    assert row.password_hash == "h2"
    assert row.password_version == 1


def test_delete(repo: UserRepo):
    uid = repo.create(username="a", password_hash="h", role="user")
    repo.delete(uid)
    assert repo.get(uid) is None


def test_count(repo: UserRepo):
    assert repo.count() == 0
    repo.create(username="a", password_hash="h", role="user")
    assert repo.count() == 1
