"""One-time grant of experts / tasks / token usage to existing accounts."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.db.migrate import (
    _NAV_PAGE_PERMISSIONS_FLAG,
    _grant_default_nav_permissions,
    run_migrations,
)
from octop.infra.db.pool import SqlitePool


def _perms(pool: SqlitePool, sql: str, params: tuple[object, ...]) -> list[str]:
    with pool.connect() as conn:
        raw = conn.execute(sql, params).fetchone()[0]
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    return [str(item) for item in parsed]


def test_nav_page_permissions_are_granted_once(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    with pool.transaction() as conn:
        conn.execute(
            "DELETE FROM settings WHERE key = ?",
            (_NAV_PAGE_PERMISSIONS_FLAG,),
        )
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at, permissions) "
            "VALUES (?, ?, 'user', 0, ?)",
            ("ada", "x", json.dumps(["channels"])),
        )
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at, permissions) "
            "VALUES (?, ?, 'admin', 0, ?)",
            ("root", "x", "[]"),
        )
        conn.execute(
            "INSERT INTO user_role("
            "user_role_id, user_role_name, permissions, policies, created_at, updated_at"
            ") VALUES ('c_custom', 'Custom', ?, '[]', 0, 0)",
            (json.dumps(["channels"]),),
        )

    _grant_default_nav_permissions(pool)

    ada = _perms(
        pool,
        "SELECT permissions FROM users WHERE username = ?",
        ("ada",),
    )
    assert ada == ["channels", "experts", "tasks", "token_usage"]
    root = _perms(
        pool,
        "SELECT permissions FROM users WHERE username = ?",
        ("root",),
    )
    assert root == []
    custom = _perms(
        pool,
        "SELECT permissions FROM user_role WHERE user_role_id = ?",
        ("c_custom",),
    )
    assert "experts" in custom and "tasks" in custom and "token_usage" in custom
    admin_role = _perms(
        pool,
        "SELECT permissions FROM user_role WHERE user_role_id = ?",
        ("admin",),
    )
    assert admin_role == []

    with pool.transaction() as conn:
        conn.execute(
            "UPDATE users SET permissions = ? WHERE username = ?",
            (json.dumps(["channels"]), "ada"),
        )
    _grant_default_nav_permissions(pool)
    ada_again = _perms(
        pool,
        "SELECT permissions FROM users WHERE username = ?",
        ("ada",),
    )
    assert ada_again == ["channels"]
