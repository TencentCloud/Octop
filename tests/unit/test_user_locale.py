"""tests/unit/test_user_locale.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.locale import normalize_locale, resolve_locale


@pytest.fixture
def db(tmp_path: Path) -> DBPool:
    pool = DBPool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_users_table_has_locale_default_zh(db: DBPool):
    uid = UserRepo(db).create(username="u", password_hash="h", role="user")
    row = UserRepo(db).get(uid)
    assert row is not None
    assert row.locale == "zh"


def test_user_repo_create_accepts_explicit_locale(db: DBPool):
    uid = UserRepo(db).create(username="en-user", password_hash="h", role="admin", locale="en")
    row = UserRepo(db).get(uid)
    assert row is not None
    assert row.locale == "en"


def test_legacy_users_table_gets_locale_column(tmp_path: Path):
    pool = DBPool(tmp_path / "legacy.db")
    with pool.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE users (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              username      TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              role          TEXT NOT NULL,
              display_name  TEXT,
              disabled      INTEGER NOT NULL DEFAULT 0,
              created_at    INTEGER NOT NULL
            );
            CREATE TABLE _schema_version (version INTEGER NOT NULL);
            INSERT INTO _schema_version(version) VALUES (8);
            INSERT INTO users(username, password_hash, role, created_at)
            VALUES ('legacy', 'h', 'admin', 0);
            """
        )

    run_migrations(pool)
    row = UserRepo(pool).get_by_username("legacy")

    assert row is not None
    assert row.locale == "zh"


def test_set_locale_persists(db: DBPool):
    repo = UserRepo(db)
    uid = repo.create(username="u", password_hash="h", role="user")
    repo.set_locale(uid, "en")
    row = repo.get(uid)
    assert row is not None
    assert row.locale == "en"


def test_resolve_locale_prefers_user_setting():
    assert resolve_locale(user_locale="en", channel_type="feishu") == "en"
    assert resolve_locale(user_locale="zh", channel_type="telegram") == "zh"


def test_normalize_locale_bcp47():
    assert normalize_locale("zh-CN") == "zh"
    assert normalize_locale("en-US") == "en"
