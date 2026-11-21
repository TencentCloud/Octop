"""Role templates do not rewrite existing users."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.user_roles import BUILTIN_USER_ROLE_IDS, UserRoleRepo, parse_policies
from octop.infra.db.repos.users import UserRepo
from octop.infra.users.permissions import BASELINE_PERMISSIONS


def test_seeded_roles_leave_existing_users_unchanged(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    users = UserRepo(db)
    uid = users.create(
        username="alice",
        password_hash="x",
        role="user",
        permissions=["browser"],
    )
    row = users.get(uid)
    assert row is not None
    assert row.role_name is None
    assert row.permissions == ["browser"]

    roles = UserRoleRepo(db)
    admin = roles.get("admin")
    user = roles.get("user")
    assert admin is not None and admin.user_role_name == "管理员"
    assert admin.policies == []
    assert user is not None
    assert set(user.permissions) == set(BASELINE_PERMISSIONS)
    assert user.policies == []
    assert frozenset({"admin", "user"}) == BUILTIN_USER_ROLE_IDS

    # Built-in templates can be deleted at the repo layer, but migrate re-seeds them.
    assert roles.delete("user") is True
    roles.delete("admin")
    run_migrations(db)
    assert roles.get("admin") is not None
    assert roles.get("user") is not None
    again = users.get(uid)
    assert again is not None
    assert again.role_name is None
    assert again.permissions == ["browser"]
    assert again.role == "user"


def test_policies_array_omits_disabled_names() -> None:
    raw = json.dumps([{"name": "token_quota", "value": "10"}, {"name": "max_agents", "value": ""}])
    assert parse_policies(raw) == [("token_quota", "10")]


def test_role_repo_roundtrip(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    roles = UserRoleRepo(db)
    created = roles.create(
        user_role_name="分析师",
        description="分析角色",
        permissions=["browser"],
        policies=[("token_quota", "10")],
    )
    assert created.user_role_id
    assert created.user_role_id not in {"admin", "user"}
    loaded = roles.get_by_name("分析师")
    assert loaded is not None
    assert loaded.description == "分析角色"
    assert loaded.policies == [("token_quota", "10")]
    assert loaded.policy_value("max_agents") is None
    assert loaded.policy_value("workspace_root_dir") is None


def test_cli_and_seed_follow_preset_user_role(tmp_path: Path) -> None:
    from octop.cli.support.offline_ops import create_user_offline
    from octop.infra.db.repos.user_roles import seeded_user_role_assignment
    from octop.infra.users.permissions import BASELINE_PERMISSIONS

    home = tmp_path / "home"
    created = create_user_offline(
        username="cliuser",
        password="TestPass12",
        role="user",
        home=home,
    )
    assert created["role"] == "user"
    db = SqlitePool(home / "octop.db")
    row = UserRepo(db).get_by_username("cliuser")
    assert row is not None
    assert row.role == "user"
    assert row.role_name == "用户"
    assert set(row.permissions) == set(BASELINE_PERMISSIONS)

    assignment = seeded_user_role_assignment(db)
    assert assignment is not None
    assert assignment[0] == "user"
    db.close()
