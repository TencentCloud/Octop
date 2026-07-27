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
    repo.set_password_hash(uid, "h2")
    assert repo.get(uid).password_hash == "h2"


def test_delete(repo: UserRepo):
    uid = repo.create(username="a", password_hash="h", role="user")
    repo.delete(uid)
    assert repo.get(uid) is None


def test_count(repo: UserRepo):
    assert repo.count() == 0
    repo.create(username="a", password_hash="h", role="user")
    assert repo.count() == 1
