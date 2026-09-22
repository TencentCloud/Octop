"""tests/unit/test_db_sql_helpers.py"""

from __future__ import annotations

from datetime import UTC, datetime

from octop.infra.db.repos._base import insert_returning_id, sql_in_placeholders, sql_unix_day_bucket


def test_sql_in_placeholders():
    assert sql_in_placeholders(3) == "?, ?, ?"
    assert sql_in_placeholders(1) == "?"


def test_sql_unix_day_bucket_sqlite():
    assert sql_unix_day_bucket("ts") == "date(ts, 'unixepoch')"


def test_sql_unix_day_bucket_postgresql():
    assert "to_timestamp(ts)" in sql_unix_day_bucket("ts", dialect="postgresql")


def test_sql_unix_day_bucket_sqlite_uses_zone_offset_at_window_start():
    at = int(datetime(2026, 9, 22, 0, 0, tzinfo=UTC).timestamp())
    assert (
        sql_unix_day_bucket("ts", timezone="Asia/Shanghai", at=at)
        == "date(ts, 'unixepoch', '+08:00')"
    )
    assert (
        sql_unix_day_bucket("ts", timezone="Asia/Kolkata", at=at)
        == "date(ts, 'unixepoch', '+05:30')"
    )


def test_sql_unix_day_bucket_sqlite_follows_dst():
    winter = int(datetime(2026, 1, 15, 12, 0, tzinfo=UTC).timestamp())
    summer = int(datetime(2026, 7, 15, 12, 0, tzinfo=UTC).timestamp())
    assert (
        sql_unix_day_bucket("ts", timezone="America/New_York", at=winter)
        == "date(ts, 'unixepoch', '-05:00')"
    )
    assert (
        sql_unix_day_bucket("ts", timezone="America/New_York", at=summer)
        == "date(ts, 'unixepoch', '-04:00')"
    )


def test_sql_unix_day_bucket_postgresql_converts_per_row():
    expr = sql_unix_day_bucket("ts", dialect="postgresql", timezone="Asia/Shanghai")
    assert "AT TIME ZONE 'Asia/Shanghai'" in expr


def test_sql_unix_day_bucket_unknown_zone_falls_back_to_utc():
    at = int(datetime(2026, 9, 22, 0, 0, tzinfo=UTC).timestamp())
    assert (
        sql_unix_day_bucket("ts", timezone="Mars/Olympus", at=at)
        == "date(ts, 'unixepoch', '+00:00')"
    )


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
