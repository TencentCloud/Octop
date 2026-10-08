"""Unit tests for SQLite snapshot helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop.infra.backup.snapshot import (
    capture_jwt_secret_from_pool,
    capture_users_from_pool,
    restore_jwt_secret_into_pool,
    snapshot_sqlite_file,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DatabasePool, SqlitePool


@pytest.mark.skipif(os.name == "nt", reason="Windows disallows '?' in path names")
def test_snapshot_sqlite_file_with_special_chars_in_path(tmp_path: Path) -> None:
    """Paths containing URI metacharacters must not alter connect options."""
    tricky_dir = tmp_path / "dir?mode=memory"
    tricky_dir.mkdir()
    source = tricky_dir / "data.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('ok')")

    dest = tmp_path / "backup.db"
    snapshot_sqlite_file(source, dest)

    with sqlite3.connect(dest) as conn:
        row = conn.execute("SELECT v FROM t").fetchone()
    assert row is not None
    assert row[0] == "ok"


def test_capture_users_reads_mapping_values_and_serializes_jsonb_permissions() -> None:
    """PostgreSQL rows iterate over column names and decode JSONB as lists."""
    row = {
        "id": 1,
        "username": "alice",
        "password_hash": "hash",
        "role": "user",
        "display_name": None,
        "disabled": 0,
        "created_at": 1,
        "locale": "zh",
        "preferences_json": "{}",
        "login_failed_count": 0,
        "login_locked_until": 0,
        "email": "alice@example.com",
        "permissions": ["channels", "knowledge_bases"],
        "role_name": "User",
        "avatar_icon": None,
    }
    pool = MagicMock(spec=DatabasePool)
    pool.connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [
        row
    ]

    captured = capture_users_from_pool(pool)

    assert captured == [
        (
            1,
            "alice",
            "hash",
            "user",
            None,
            0,
            1,
            "zh",
            "{}",
            0,
            0,
            "alice@example.com",
            '["channels", "knowledge_bases"]',
            "User",
            None,
        )
    ]


def test_jwt_secret_capture_and_restore(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    secret = b"session-jwt-secret-value-32bytes!!"

    assert capture_jwt_secret_from_pool(pool) is None

    with pool.connect() as conn:
        conn.execute(
            "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
            ("jwt", secret, 1),
        )
    assert capture_jwt_secret_from_pool(pool) == secret

    # Overwrite with a foreign secret, then restore the captured one.
    with pool.connect() as conn:
        conn.execute("UPDATE secrets SET v = ? WHERE k = ?", (b"foreign", "jwt"))
    restore_jwt_secret_into_pool(pool, secret)
    assert capture_jwt_secret_from_pool(pool) == secret

    # Insert path when the row is missing after a restore wipe.
    with pool.connect() as conn:
        conn.execute("DELETE FROM secrets WHERE k = ?", ("jwt",))
    restore_jwt_secret_into_pool(pool, secret)
    assert capture_jwt_secret_from_pool(pool) == secret
    pool.close()
