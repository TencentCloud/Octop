"""Preserve existing knowledge creation grants without reviving revoked grants."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.user_roles import seeded_user_role_assignment
from octop.infra.users.invites import _role_defaults_for_invite

_FLAG = "granted_knowledge_base_create_permission"


@pytest.mark.parametrize("table", ["users", "user_role"])
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '["knowledge_bases", "channels"]',
            ["knowledge_bases", "channels", "knowledge_bases:create"],
        ),
        ('["channels"]', ["channels"]),
        ("[]", []),
        (
            '["knowledge_bases", "knowledge_bases:create"]',
            ["knowledge_bases", "knowledge_bases:create"],
        ),
        ('{"knowledge_bases": true}', {"knowledge_bases": True}),
    ],
)
def test_upgrade_preserves_existing_creation_access(
    tmp_path: Path, table: str, raw: str, expected: object
) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    with db.transaction() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_FLAG,))
        if table == "users":
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at, permissions) "
                "VALUES ('reader', 'x', 'user', 0, ?)",
                (raw,),
            )
            where = "username = 'reader'"
        else:
            conn.execute(
                "INSERT INTO user_role(user_role_id, user_role_name, permissions, policies, "
                "created_at, updated_at) VALUES ('reader', 'Reader', ?, '[]', 0, 0)",
                (raw,),
            )
            where = "user_role_id = 'reader'"
    run_migrations(db)
    with db.connect() as conn:
        stored = conn.execute(f"SELECT permissions FROM {table} WHERE {where}").fetchone()[0]
    assert json.loads(stored) == expected
    db.close()


def test_explicit_revocation_survives_server_restart(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    with db.transaction() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_FLAG,))
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at, permissions) "
            "VALUES ('reader', 'x', 'user', 0, '[\"knowledge_bases\"]')"
        )
        conn.execute(
            "UPDATE user_role SET permissions = '[\"knowledge_bases\"]' WHERE user_role_id = 'user'"
        )
    run_migrations(db)
    with db.connect() as conn:
        assert (
            conn.execute("SELECT value FROM settings WHERE key = ?", (_FLAG,)).fetchone()[0] == "1"
        )
    with db.transaction() as conn:
        conn.execute(
            "UPDATE users SET permissions = '[\"knowledge_bases\"]' WHERE username = 'reader'"
        )
        conn.execute(
            "UPDATE user_role SET permissions = '[\"knowledge_bases\"]' WHERE user_role_id = 'user'"
        )
    run_migrations(db)
    with db.connect() as conn:
        assert json.loads(
            conn.execute("SELECT permissions FROM users WHERE username = 'reader'").fetchone()[0]
        ) == ["knowledge_bases"]
        assert json.loads(
            conn.execute(
                "SELECT permissions FROM user_role WHERE user_role_id = 'user'"
            ).fetchone()[0]
        ) == ["knowledge_bases"]
    db.close()


def test_upgraded_role_is_used_by_invites_and_sso_defaults(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    with db.transaction() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_FLAG,))
        conn.execute(
            "UPDATE user_role SET permissions = '[\"knowledge_bases\"]' WHERE user_role_id = 'user'"
        )
    run_migrations(db)
    assignment = seeded_user_role_assignment(db)
    assert assignment is not None
    assert assignment[2] == ["knowledge_bases", "knowledge_bases:create"]
    invite = SimpleNamespace(role="user", role_name=None)
    assert _role_defaults_for_invite(db, invite)[1] == ["knowledge_bases", "knowledge_bases:create"]
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT permissions FROM user_role WHERE user_role_id = 'admin'"
            ).fetchone()[0]
            == "[]"
        )
    db.close()
