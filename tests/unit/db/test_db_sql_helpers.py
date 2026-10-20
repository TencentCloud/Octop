"""tests/unit/test_db_sql_helpers.py"""

from __future__ import annotations

import sqlite3

from octop.infra.db.repos._base import (
    insert_returning_id,
    is_unique_violation,
    sql_in_placeholders,
    sql_unix_day_bucket,
)


def test_is_unique_violation_recognizes_sqlite_unique_errors():
    assert is_unique_violation(sqlite3.IntegrityError("UNIQUE constraint failed: providers.name"))
    assert not is_unique_violation(
        sqlite3.IntegrityError("NOT NULL constraint failed: providers.name")
    )
    assert not is_unique_violation(ValueError("UNIQUE constraint failed: providers.name"))


def test_sql_in_placeholders():
    assert sql_in_placeholders(3) == "?, ?, ?"
    assert sql_in_placeholders(1) == "?"


def test_sql_unix_day_bucket_sqlite():
    assert sql_unix_day_bucket("ts") == "date(ts, 'unixepoch')"


def test_sql_unix_day_bucket_postgresql():
    assert "to_timestamp(ts)" in sql_unix_day_bucket("ts", dialect="postgresql")


def test_insert_returning_id(tmp_path):
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import SqlitePool

    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    with db.transaction() as conn:
        uid = insert_returning_id(
            conn,
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("u", "h", "user"),
        )
    assert isinstance(uid, int)
    assert uid >= 1
