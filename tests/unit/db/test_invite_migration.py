"""Invite migration coverage for restored databases with missing tables."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from tests.support.postgresql import requires_postgresql

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DatabasePool, PostgresPool, SqlitePool
from octop.infra.db.repos.invites import InviteRepo
from octop.infra.db.repos.users import UserRepo


def _assert_missing_invite_table_is_repaired(db: DatabasePool) -> None:
    run_migrations(db)
    user_id = UserRepo(db).create(
        username="invite-migration-admin", password_hash="hash", role="admin"
    )
    with db.transaction() as conn:
        conn.execute("DROP TABLE user_invite_redemptions")
        conn.execute("DROP TABLE user_invites")
        conn.execute("UPDATE _schema_version SET version = 25")

    run_migrations(db)
    invite = InviteRepo(db).create(code="repaired", created_by=user_id, expires_at=4_102_444_800)
    assert invite.enabled
    InviteRepo(db).redeem_creating_user(
        code=invite.code,
        username="invite-migration-user",
        password_hash="hash",
        display_name=None,
        locale="en",
    )
    assert InviteRepo(db).get(invite.id).use_count == 1
    with db.transaction() as conn:
        conn.execute("DROP TABLE user_invite_redemptions")
    run_migrations(db)
    assert InviteRepo(db).get(invite.id).use_count == 1
    assert InviteRepo(db).list_users(invite.id, limit=20, offset=0) == ([], 0)


def test_sqlite_repairs_missing_invite_table(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "invites.db")
    try:
        _assert_missing_invite_table_is_repaired(db)
    finally:
        db.close()


def _assert_v26_repairs_new_v25_columns(db: DatabasePool, *, capped: bool) -> None:
    run_migrations(db)
    user_id = UserRepo(db).create(username="legacy-admin", password_hash="hash", role="admin")
    repo = InviteRepo(db)
    limit = 3 if capped else None
    invite = repo.create(
        code="legacy-invite", created_by=user_id, expires_at=4_102_444_800, max_uses=limit
    )
    repo.redeem_creating_user(
        code=invite.code,
        username="legacy-invite-user",
        password_hash="hash",
        display_name=None,
        locale="en",
    )
    if capped:
        deleted_id, _ = repo.redeem_creating_user(
            code=invite.code,
            username="deleted-legacy-invite-user",
            password_hash="hash",
            display_name=None,
            locale="en",
        )
        UserRepo(db).delete(deleted_id)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO audit_log (ts, actor, action) VALUES (1234, 'legacy-admin', 'auth.login')"
        )
        conn.execute("ALTER TABLE users DROP COLUMN last_login_at")
        conn.execute("ALTER TABLE threads DROP COLUMN contributed")
        conn.execute("ALTER TABLE user_invites ADD COLUMN used_at BIGINT")
        conn.execute(
            "ALTER TABLE user_invites ADD COLUMN used_by_user_id BIGINT "
            "REFERENCES users(id) ON DELETE SET NULL"
        )
        conn.execute("ALTER TABLE user_invites ADD COLUMN revoked_at BIGINT")
        # Earlier v26 builds could re-enable a legacy revoked invite.
        conn.execute("UPDATE user_invites SET revoked_at = 1234 WHERE id = ?", (invite.id,))
        if not capped:
            conn.execute("ALTER TABLE user_invites DROP COLUMN max_uses")
            conn.execute("ALTER TABLE user_invites DROP COLUMN use_count")
        conn.execute("UPDATE _schema_version SET version = 26")

    run_migrations(db)
    with db.connect() as conn:
        assert (
            conn.execute("SELECT last_login_at FROM users WHERE id = ?", (user_id,)).fetchone()[0]
            == 1234
        )
        conn.execute("SELECT contributed FROM threads LIMIT 1")
        assert conn.execute("SELECT version FROM _schema_version").fetchone()[0] == 26
        columns = {
            column[0] for column in conn.execute("SELECT * FROM user_invites LIMIT 0").description
        }
        assert {"used_at", "used_by_user_id", "revoked_at"}.isdisjoint(columns)
    previous_count = 2 if capped else 1
    row = repo.get(invite.id)
    assert (
        row is not None
        and row.max_uses == limit
        and row.use_count == previous_count
        and row.enabled
    )
    participants, count = repo.list_users(invite.id, limit=20, offset=0)
    assert count == 1 and participants[0]["username"] == "legacy-invite-user"
    repo.redeem_creating_user(
        code=invite.code,
        username="second-legacy-invite-user",
        password_hash="hash",
        display_name=None,
        locale="en",
    )
    run_migrations(db)
    row = repo.get(invite.id)
    assert row is not None and row.use_count == previous_count + 1 and row.enabled == (not capped)


@pytest.mark.parametrize("capped", [False, True])
def test_sqlite_repairs_new_upstream_columns_at_v26(tmp_path: Path, capped: bool) -> None:
    db = SqlitePool(tmp_path / "legacy-v26.db")
    try:
        _assert_v26_repairs_new_v25_columns(db, capped=capped)
    finally:
        db.close()


@requires_postgresql
@pytest.mark.postgresql
def test_postgresql_repairs_missing_invite_table() -> None:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    url = os.environ["OCTOP_TEST_DATABASE_URL"]
    schema = "invite_migration_" + uuid.uuid4().hex[:12]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    info = conninfo_to_dict(url)
    info["options"] = f"-c search_path={schema}"
    db = PostgresPool(make_conninfo(**info))
    try:
        _assert_missing_invite_table_is_repaired(db)
    finally:
        db.close()
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@requires_postgresql
@pytest.mark.postgresql
@pytest.mark.parametrize("capped", [False, True])
def test_postgresql_repairs_new_upstream_columns_at_v26(capped: bool) -> None:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    url = os.environ["OCTOP_TEST_DATABASE_URL"]
    schema = "invite_migration_" + uuid.uuid4().hex[:12]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    info = conninfo_to_dict(url)
    info["options"] = f"-c search_path={schema}"
    db = PostgresPool(make_conninfo(**info))
    try:
        _assert_v26_repairs_new_v25_columns(db, capped=capped)
    finally:
        db.close()
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
