"""Unit tests for invite code helpers and repo redeem."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.invites import InviteRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.users.invites import (
    DEFAULT_EXPIRES_DAYS,
    generate_invite_code,
    invite_path,
)
from octop.infra.users.password import hash_password


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_generate_invite_code_shape() -> None:
    code = generate_invite_code()
    assert len(code) == 11
    assert code.isalnum()
    assert invite_path(code) == f"/invite?code={code}"


def test_invite_repo_redeem_multiple(db: SqlitePool) -> None:
    users = UserRepo(db)
    invites = InviteRepo(db)
    admin_id = users.create(
        username="admin",
        password_hash=hash_password("AdminPass12"),
        role="admin",
    )
    invite = invites.create(
        code="AbCdEfGhIjK",
        created_by=admin_id,
        expires_at=now_ts() + DEFAULT_EXPIRES_DAYS * 86400,
        note="n1",
        max_uses=2,
    )
    assert invite.status() == "active"

    uid, used = invites.redeem_creating_user(
        code="AbCdEfGhIjK",
        username="newbie",
        password_hash=hash_password("NewbiePass12"),
        display_name="N",
        locale="zh",
    )
    assert uid > 0
    assert used.status() == "active"
    assert users.get_by_username("newbie") is not None

    second_id, full = invites.redeem_creating_user(
        code="AbCdEfGhIjK",
        username="other",
        password_hash=hash_password("OtherPass12"),
        display_name=None,
        locale="en",
    )
    assert second_id != uid
    assert full.status() == "disabled"
    assert full.use_count == 2
    rows, total = invites.list_users(invite.id, limit=1, offset=1)
    assert total == 2
    assert len(rows) == 1
    users.delete(uid)
    assert invites.list_users(invite.id, limit=20, offset=0)[1] == 1
    remaining = invites.get(invite.id)
    assert remaining is not None and remaining.use_count == 2 and not remaining.enabled
    with pytest.raises(ValueError, match="exhausted"):
        invites.set_enabled(invite.id, True)


def test_invite_repo_revoke(db: SqlitePool) -> None:
    users = UserRepo(db)
    invites = InviteRepo(db)
    admin_id = users.create(
        username="admin2",
        password_hash=hash_password("AdminPass12"),
        role="admin",
    )
    invite = invites.create(
        code="ZzYyXxWwVvU",
        created_by=admin_id,
        expires_at=now_ts() + 86400,
    )
    revoked = invites.set_enabled(invite.id, False)
    assert revoked is not None
    assert revoked.status() == "disabled"
    with pytest.raises(ValueError, match="disabled"):
        invites.redeem_creating_user(
            code=invite.code,
            username="blocked",
            password_hash="hash",
            display_name=None,
            locale="en",
        )
    enabled = invites.set_enabled(invite.id, True)
    assert enabled is not None and enabled.status() == "active"


def test_expired_invite_cannot_be_redeemed(db: SqlitePool) -> None:
    users = UserRepo(db)
    admin_id = users.create(username="admin", password_hash="hash", role="admin")
    invites = InviteRepo(db)
    invite = invites.create(code="expired", created_by=admin_id, expires_at=now_ts())
    assert invite.status() == "expired"
    with pytest.raises(ValueError, match="expired"):
        invites.redeem_creating_user(
            code=invite.code,
            username="blocked",
            password_hash="hash",
            display_name=None,
            locale="en",
        )


def test_legacy_invites_migrate_without_reopening(db: SqlitePool) -> None:
    users = UserRepo(db)
    admin_id = users.create(username="admin", password_hash="hash", role="admin")
    invited_id = users.create(username="invited", password_hash="hash", role="user")
    with db.connect() as conn:
        conn.execute("DROP TABLE user_invite_redemptions")
        conn.execute("ALTER TABLE user_invites DROP COLUMN enabled")
        conn.execute("ALTER TABLE user_invites DROP COLUMN max_uses")
        conn.execute("ALTER TABLE user_invites DROP COLUMN use_count")
        conn.execute(
            "INSERT INTO user_invites(code, created_by, created_at, expires_at, used_at, used_by_user_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("old-used", admin_id, 1, now_ts() + 1000, 2, invited_id),
        )
        conn.execute(
            "INSERT INTO user_invites(code, created_by, created_at, expires_at, revoked_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("old-revoked", admin_id, 1, now_ts() + 1000, 2),
        )
        conn.execute(
            "INSERT INTO user_invites(code, created_by, created_at, expires_at, used_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("old-user-deleted", admin_id, 1, now_ts() + 1000, 2),
        )
        conn.execute(
            "INSERT INTO user_invites(code, created_by, created_at, expires_at) VALUES (?, ?, ?, ?)",
            ("old-unused", admin_id, 1, now_ts() + 1000),
        )
        conn.execute("UPDATE _schema_version SET version = 25")
    run_migrations(db)
    repo = InviteRepo(db)
    used = repo.get_by_code("old-used")
    revoked = repo.get_by_code("old-revoked")
    deleted = repo.get_by_code("old-user-deleted")
    unused = repo.get_by_code("old-unused")
    assert used is not None and used.status() == "disabled" and used.use_count == 1
    assert revoked is not None and revoked.status() == "disabled"
    assert deleted is not None and deleted.status() == "disabled" and deleted.use_count == 1
    assert unused is not None and unused.status() == "active" and unused.max_uses == 1
    assert repo.list_users(used.id, limit=20, offset=0)[0][0]["id"] == invited_id
    with pytest.raises(ValueError, match="exhausted"):
        repo.set_enabled(used.id, True)
    run_migrations(db)
    assert not repo.get(used.id).enabled


def test_concurrent_redemptions_from_separate_connections(db: SqlitePool) -> None:
    admin_id = UserRepo(db).create(username="admin", password_hash="hash", role="admin")
    invite = InviteRepo(db).create(
        code="concurrent", created_by=admin_id, expires_at=now_ts() + 1000, max_uses=1
    )
    second_db = SqlitePool(db.path)
    barrier = Barrier(2)

    def register(pool: SqlitePool, username: str) -> int | None:
        barrier.wait(timeout=5)
        try:
            return InviteRepo(pool).redeem_creating_user(
                code=invite.code,
                username=username,
                password_hash="hash",
                display_name=None,
                locale="en",
            )[0]
        except ValueError as exc:
            assert str(exc) == "disabled"
            return None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(register, db, "first")
            second = executor.submit(register, second_db, "second")
            outcomes = [first.result(timeout=10), second.result(timeout=10)]
        assert outcomes.count(None) == 1
        full = InviteRepo(db).get(invite.id)
        assert full is not None and full.use_count == 1 and not full.enabled
        assert InviteRepo(db).list_users(invite.id, limit=20, offset=0)[1] == 1
    finally:
        second_db.close()
