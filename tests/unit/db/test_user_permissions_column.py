"""Tests for users.permissions column wiring."""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo, UserRow


def test_user_row_carries_permissions(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    repo = UserRepo(db)
    uid = repo.create(
        username="alice",
        password_hash="x",
        role="user",
        permissions=["browser", "users"],
    )
    row = repo.get(uid)
    assert row is not None
    assert row.permissions == ["browser", "users"]


def test_set_permissions_roundtrip(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    repo = UserRepo(db)
    uid = repo.create(username="bob", password_hash="x", role="user")
    repo.set_permissions(uid, ["providers"])
    got = repo.get(uid)
    assert got is not None
    assert got.permissions == ["providers"]


def test_from_row_accepts_missing_column_default() -> None:
    class _R(dict):
        def keys(self):  # noqa: ANN201
            return super().keys()

    raw = _R(
        id=1,
        username="u",
        password_hash="x",
        role="user",
        display_name=None,
        disabled=0,
        created_at=0,
        locale="zh",
        email=None,
        sso_provider_id=None,
        sso_subject=None,
        preferences_json="{}",
        login_failed_count=0,
        login_locked_until=0,
    )
    row = UserRow.from_row(raw)
    assert row.permissions == []
