"""Role assignment on ``octop user`` must fail fast instead of creating a broken user."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support.offline_ops import create_user_offline, set_user_role_offline
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.user_roles import UserRoleRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError


def _open(home: Path) -> UserRepo:
    return UserRepo(SqlitePool(home / "octop.db"))


def test_create_unknown_role_fails_before_writing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    with pytest.raises(OctopError) as excinfo:
        create_user_offline(username="guest", password="TestPass12", role="member", home=home)
    assert excinfo.value.code is ErrorCode.USER_ROLE_NOT_FOUND
    assert "member" in excinfo.value.message
    # The valid role ids are part of the message so the user can fix the command.
    assert "user" in excinfo.value.message
    db = SqlitePool(home / "octop.db")
    assert UserRepo(db).get_by_username("guest") is None
    db.close()


def test_create_applies_custom_role_template(tmp_path: Path) -> None:
    home = tmp_path / "home"
    create_user_offline(username="seed", password="TestPass12", role="user", home=home)
    db = SqlitePool(home / "octop.db")
    role = UserRoleRepo(db).create(
        user_role_name="分析师",
        permissions=["browser"],
        policies=[],
    )
    db.close()

    created = create_user_offline(
        username="analyst",
        password="TestPass12",
        role=role.user_role_id,
        home=home,
    )
    assert created["role"] == role.user_role_id

    db = SqlitePool(home / "octop.db")
    row = UserRepo(db).get_by_username("analyst")
    assert row is not None
    assert row.role_name == "分析师"
    assert row.permissions == ["browser"]
    db.close()


def test_set_role_unknown_role_keeps_current_assignment(tmp_path: Path) -> None:
    home = tmp_path / "home"
    create_user_offline(username="alice", password="TestPass12", role="user", home=home)
    with pytest.raises(OctopError) as excinfo:
        set_user_role_offline("alice", "member", home=home)
    assert excinfo.value.code is ErrorCode.USER_ROLE_NOT_FOUND

    db = SqlitePool(home / "octop.db")
    row = UserRepo(db).get_by_username("alice")
    assert row is not None
    assert row.role == "user"
    assert row.role_name == "用户"
    db.close()


def test_set_role_applies_template_permissions(tmp_path: Path) -> None:
    home = tmp_path / "home"
    create_user_offline(username="alice", password="TestPass12", role="user", home=home)
    db = SqlitePool(home / "octop.db")
    role = UserRoleRepo(db).create(
        user_role_name="分析师",
        permissions=["browser", "skills"],
        policies=[],
    )
    db.close()

    set_user_role_offline("alice", role.user_role_id, home=home)

    db = SqlitePool(home / "octop.db")
    row = UserRepo(db).get_by_username("alice")
    assert row is not None
    assert row.role == role.user_role_id
    assert row.role_name == "分析师"
    assert set(row.permissions) == {"browser", "skills"}
    db.close()


def test_cli_create_reports_unknown_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "octop"))
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(
        cli,
        ["user", "create", "guest", "--password", "TestPass12", "--role", "member"],
    )
    assert result.exit_code == 1
    assert "member" in result.output
    assert "does not exist" in result.output
