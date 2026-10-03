"""``octop user role`` must apply the role template, not only relabel ``users.role``.

Every other transport that assigns a template copies it onto the user
(``PATCH /api/users/{id}`` through ``_resolve_role_template``, SSO and
``octop user create`` through ``seeded_user_role_assignment``, invite redeem through
``_role_defaults_for_invite``). The offline CLI path skipped that step, so switching a
user's role left the previous module permissions, the previous ``role_name`` label and
the previous resource limits in place.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support.offline_ops import create_user_offline, set_user_role_offline
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.user_policies import UserPolicyRepo
from octop.infra.db.repos.user_roles import UserRoleRepo
from octop.infra.db.repos.users import UserRepo, UserRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.permissions import BASELINE_PERMISSIONS
from octop.infra.users.resource_policy import POLICY_TOKEN_QUOTA


def _pool(home: Path) -> SqlitePool:
    return SqlitePool(home / "octop.db")


def _seed_user(home: Path, username: str) -> int:
    created = create_user_offline(
        username=username,
        password="TestPass12",
        role="user",
        home=home,
    )
    return int(created["id"])


def _loaded_user(home: Path, username: str) -> tuple[UserRow, dict[str, str]]:
    """Return ``(users row, enabled policy values)`` for ``username``."""
    db = _pool(home)
    try:
        row = UserRepo(db).get_by_username(username)
        assert row is not None
        policies = UserPolicyRepo(db).enabled_values(int(row.id))
    finally:
        db.close()
    return row, policies


def _create_role(
    home: Path,
    *,
    name: str,
    permissions: list[str],
    policies: list[tuple[str, str]],
) -> str:
    db = _pool(home)
    try:
        row = UserRoleRepo(db).create(
            user_role_name=name,
            permissions=permissions,
            policies=policies,
        )
    finally:
        db.close()
    return row.user_role_id


def _stage_template_snapshot(
    home: Path,
    uid: int,
    *,
    role_id: str,
    role_name: str,
    permissions: list[str],
    policies: dict[str, str],
) -> None:
    """Write what an API role assignment would already have stored on the user."""
    db = _pool(home)
    try:
        users = UserRepo(db)
        users.set_role(uid, role_id)
        users.set_role_name(uid, role_name)
        users.set_permissions(uid, permissions)
        UserPolicyRepo(db).merge(uid, policies)
    finally:
        db.close()


def test_applying_a_template_copies_permissions_label_and_limits(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_user(home, "alice")
    analyst = _create_role(
        home,
        name="分析师",
        permissions=["browser"],
        policies=[(POLICY_TOKEN_QUOTA, "10")],
    )

    set_user_role_offline("alice", analyst, home=home)

    row, policies = _loaded_user(home, "alice")
    assert row.role == analyst
    assert row.permissions == ["browser"]
    assert row.role_name == "分析师"
    assert policies == {POLICY_TOKEN_QUOTA: "10"}


def test_switching_templates_revokes_the_previous_module_permissions(tmp_path: Path) -> None:
    home = tmp_path / "home"
    uid = _seed_user(home, "bob")
    auditor = _create_role(
        home,
        name="审计",
        permissions=["users", "admin_console"],
        policies=[(POLICY_TOKEN_QUOTA, "10")],
    )
    limited = _create_role(home, name="受限", permissions=["browser"], policies=[])
    _stage_template_snapshot(
        home,
        uid,
        role_id=auditor,
        role_name="审计",
        permissions=["users", "admin_console"],
        policies={POLICY_TOKEN_QUOTA: "10"},
    )

    set_user_role_offline("bob", limited, home=home)

    row, policies = _loaded_user(home, "bob")
    assert row.role == limited
    assert row.permissions == ["browser"]
    assert "users" not in row.permissions
    assert row.role_name == "受限"
    # The written invariant: "limits from a previous role cannot linger after a switch".
    assert policies == {}


def test_applying_the_admin_template_clears_modules_and_limits(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_user(home, "carol")
    row, _ = _loaded_user(home, "carol")
    assert set(row.permissions) == set(BASELINE_PERMISSIONS)

    set_user_role_offline("carol", "admin", home=home)

    row, policies = _loaded_user(home, "carol")
    assert row.role == "admin"
    assert row.role_name == "管理员"
    # An administrator bypasses the catalog, and the form stores that as an empty list.
    assert row.permissions == []
    assert policies == {}


def test_unknown_template_is_rejected_without_touching_the_user(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_user(home, "dave")

    with pytest.raises(OctopError) as excinfo:
        set_user_role_offline("dave", "no-such-role", home=home)

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert excinfo.value.status == 404
    row, _ = _loaded_user(home, "dave")
    assert row.role == "user"
    assert set(row.permissions) == set(BASELINE_PERMISSIONS)


def test_cli_role_command_fails_on_unknown_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    _seed_user(home, "erin")
    monkeypatch.setenv("OCTOP_HOME", str(home))

    result = CliRunner().invoke(cli, ["user", "role", "erin", "no-such-role"])

    assert result.exit_code != 0
    assert "ok" not in result.output
