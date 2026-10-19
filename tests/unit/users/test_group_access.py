"""User-group visibility: no grants keep today's audience, grants narrow it."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.groups import (
    RESOURCE_MODEL,
    RESOURCE_SKILL_PACKAGE,
    GroupAccess,
    model_ref_allowed,
)


@pytest.fixture
def repos(tmp_path: Path) -> RepoBundle:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return RepoBundle.from_pool(pool)


def _user(repos: RepoBundle, username: str, role: str = "user") -> int:
    return repos.user_repo.create(username=username, role=role)


def test_schema_version_includes_user_groups(repos: RepoBundle) -> None:
    with repos.db.connect() as conn:
        version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert version == 22
    assert {"user_group", "user_group_member", "resource_group_grant"}.issubset(names)


def test_no_grants_allow_everyone(repos: RepoBundle) -> None:
    user_id = _user(repos, "ada")
    access = GroupAccess(repos)
    assert access.allows(
        user_id=user_id,
        is_admin=False,
        resource_type=RESOURCE_SKILL_PACKAGE,
        resource_key="pkg",
        is_owner=False,
    )
    assert access.visibility(RESOURCE_SKILL_PACKAGE, "pkg", shared=None) == {
        "visibility": "all",
        "group_ids": [],
    }


def test_grants_narrow_and_owner_admin_bypass(repos: RepoBundle) -> None:
    member = _user(repos, "member")
    outsider = _user(repos, "outsider")
    admin = _user(repos, "root", role="admin")
    group = repos.user_group_repo.create(name="design", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)
    access = GroupAccess(repos)
    access.set_visibility(RESOURCE_MODEL, "openai/gpt", "groups", [group.user_group_id])

    assert access.allows(
        user_id=member,
        is_admin=False,
        resource_type=RESOURCE_MODEL,
        resource_key="openai/gpt",
        is_owner=False,
    )
    assert not access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_MODEL,
        resource_key="openai/gpt",
        is_owner=False,
    )
    assert access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_MODEL,
        resource_key="openai/gpt",
        is_owner=True,
    )
    assert access.allows(
        user_id=outsider,
        is_admin=True,
        resource_type=RESOURCE_MODEL,
        resource_key="openai/gpt",
        is_owner=False,
    )
    assert (
        model_ref_allowed(repos, user_id=outsider, is_admin=False, model_ref="openai/gpt") is False
    )
    assert model_ref_allowed(repos, user_id=admin, is_admin=True, model_ref="openai/gpt") is True
    assert model_ref_allowed(repos, user_id=outsider, is_admin=False, model_ref="auto") is True

    visible = access.visibility(RESOURCE_MODEL, "openai/gpt", shared=None)
    assert visible["visibility"] == "groups"
    assert visible["group_ids"] == [group.user_group_id]

    access.set_visibility(RESOURCE_MODEL, "openai/gpt", "all", [])
    assert access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_MODEL,
        resource_key="openai/gpt",
        is_owner=False,
    )


def test_groups_visibility_requires_a_real_group(repos: RepoBundle) -> None:
    access = GroupAccess(repos)
    with pytest.raises(OctopError) as empty:
        access.set_visibility(RESOURCE_SKILL_PACKAGE, "pkg", "groups", [])
    assert empty.value.code == ErrorCode.FORBIDDEN
    with pytest.raises(OctopError) as missing:
        access.set_visibility(RESOURCE_SKILL_PACKAGE, "pkg", "groups", ["missing"])
    assert missing.value.code == ErrorCode.NOT_FOUND


def test_private_shared_flag_reports_owner(repos: RepoBundle) -> None:
    access = GroupAccess(repos)
    assert access.visibility(RESOURCE_SKILL_PACKAGE, "pkg", shared=False) == {
        "visibility": "owner",
        "group_ids": [],
    }
