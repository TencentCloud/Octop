"""Unit tests for invite code helpers and repo redeem."""

from __future__ import annotations

from pathlib import Path

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
    assert invite_path(code) == f"/?invite={code}"


def test_invite_repo_redeem_once(db: SqlitePool) -> None:
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
    )
    assert invite.status() == "pending"

    uid, used = invites.redeem_creating_user(
        code="AbCdEfGhIjK",
        username="newbie",
        password_hash=hash_password("NewbiePass12"),
        display_name="N",
        locale="zh",
    )
    assert uid > 0
    assert used.status() == "used"
    assert users.get_by_username("newbie") is not None

    with pytest.raises(ValueError, match="used"):
        invites.redeem_creating_user(
            code="AbCdEfGhIjK",
            username="other",
            password_hash=hash_password("OtherPass12"),
            display_name=None,
            locale="en",
        )


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
    revoked = invites.revoke(invite.id)
    assert revoked is not None
    assert revoked.status() == "revoked"
