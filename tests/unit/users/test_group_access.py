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
    assert version == 24
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


def test_disabled_group_does_not_grant(repos: RepoBundle) -> None:
    member = _user(repos, "member")
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
    repos.user_group_repo.update(group.user_group_id, enabled=False)
    assert not access.allows(
        user_id=member,
        is_admin=False,
        resource_type=RESOURCE_MODEL,
        resource_key="openai/gpt",
        is_owner=False,
    )
    from octop.infra.users.groups import group_visibility_sql

    clause = group_visibility_sql(RESOURCE_MODEL, "'openai/gpt'")
    with repos.db.connect() as conn:
        row = conn.execute(f"SELECT 1 WHERE {clause}", (member,)).fetchone()
    assert row is None


def test_connector_feature_gate_ignores_ownership(repos: RepoBundle) -> None:
    from octop.infra.users.groups import CONNECTOR_FEATURE_KEY, RESOURCE_CONNECTOR

    owner = _user(repos, "owner")
    member = _user(repos, "member")
    admin = _user(repos, "root", role="admin")
    access = GroupAccess(repos)
    assert repos.connector_repo.connector_feature_allows(owner)
    group = repos.user_group_repo.create(name="ops", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)
    access.set_visibility(
        RESOURCE_CONNECTOR,
        CONNECTOR_FEATURE_KEY,
        "groups",
        [group.user_group_id],
    )
    assert not repos.connector_repo.connector_feature_allows(owner)
    assert repos.connector_repo.connector_feature_allows(member)
    assert repos.connector_repo.connector_feature_allows(admin)
    assert access.visibility(RESOURCE_CONNECTOR, CONNECTOR_FEATURE_KEY, shared=None) == {
        "visibility": "groups",
        "group_ids": [group.user_group_id],
    }


def test_storage_feature_gate_is_not_per_backend(repos: RepoBundle) -> None:
    from octop.infra.users.groups import RESOURCE_STORAGE_BACKEND, STORAGE_FEATURE_KEY

    outsider = _user(repos, "outsider")
    member = _user(repos, "member")
    admin = _user(repos, "root", role="admin")
    access = GroupAccess(repos)
    assert access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=STORAGE_FEATURE_KEY,
        is_owner=False,
    )
    group = repos.user_group_repo.create(name="ops", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)
    access.set_visibility(
        RESOURCE_STORAGE_BACKEND,
        STORAGE_FEATURE_KEY,
        "groups",
        [group.user_group_id],
    )
    assert not access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=STORAGE_FEATURE_KEY,
        is_owner=False,
    )
    assert access.allows(
        user_id=member,
        is_admin=False,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=STORAGE_FEATURE_KEY,
        is_owner=False,
    )
    assert access.allows(
        user_id=admin,
        is_admin=True,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=STORAGE_FEATURE_KEY,
        is_owner=False,
    )


def test_group_access_summary_includes_everyone_and_group_grants(repos: RepoBundle) -> None:
    import json

    from octop.infra.users.groups import (
        CONNECTOR_FEATURE_KEY,
        RESOURCE_CONNECTOR,
        RESOURCE_KNOWLEDGE_BASE,
        RESOURCE_MODEL,
        RESOURCE_SKILL_PACKAGE,
        RESOURCE_STORAGE_BACKEND,
        STORAGE_FEATURE_KEY,
        group_access_by_group,
        model_resource_key,
    )

    group = repos.user_group_repo.create(name="ops", description=None)
    other = repos.user_group_repo.create(name="other", description=None)
    access = GroupAccess(repos)
    access.set_visibility(
        RESOURCE_CONNECTOR, CONNECTOR_FEATURE_KEY, "groups", [group.user_group_id]
    )
    access.set_visibility(
        RESOURCE_STORAGE_BACKEND, STORAGE_FEATURE_KEY, "groups", [group.user_group_id]
    )
    repos.provider_repo.create(
        name="openai",
        kind="openai",
        models_json=json.dumps(
            [
                {"id": "gpt", "name": "GPT"},
                {"id": "mini", "name": "Mini"},
            ]
        ),
    )
    access.set_visibility(
        RESOURCE_MODEL,
        model_resource_key("openai", "gpt"),
        "groups",
        [group.user_group_id],
    )
    repos.skill_package_repo.create(id="pkg-private", name="Private kit", created_by="1")
    repos.skill_package_repo.create(id="pkg-open", name="Open kit", created_by="1", shared=True)
    access.set_visibility(RESOURCE_SKILL_PACKAGE, "pkg-private", "groups", [group.user_group_id])
    access.set_visibility(RESOURCE_KNOWLEDGE_BASE, "missing-base", "groups", [group.user_group_id])
    repos.resource_group_grant_repo.replace(
        RESOURCE_CONNECTOR, "old-instance", [group.user_group_id]
    )

    summaries = group_access_by_group(repos)
    summary = summaries[group.user_group_id]
    assert summary["connectors"] == "groups"
    assert summary["storage"] == "groups"
    assert summary["models"] == [
        {"key": "openai/gpt", "label": "GPT · openai", "missing": False, "audience": "groups"},
        {"key": "openai/mini", "label": "Mini · openai", "missing": False, "audience": "all"},
    ]
    assert summary["skill_packages"] == [
        {"key": "pkg-open", "label": "Open kit", "missing": False, "audience": "all"},
        {
            "key": "pkg-private",
            "label": "Private kit",
            "missing": False,
            "audience": "creator",
        },
    ]
    assert summary["knowledge_bases"] == [
        {
            "key": "missing-base",
            "label": "missing-base",
            "missing": True,
            "audience": "groups",
        }
    ]
    other_summary = summaries[other.user_group_id]
    assert other_summary["connectors"] == "none"
    assert other_summary["storage"] == "none"
    assert other_summary["models"] == [
        {"key": "openai/mini", "label": "Mini · openai", "missing": False, "audience": "all"}
    ]
    assert other_summary["skill_packages"] == summary["skill_packages"]


def test_private_shared_flag_reports_owner(repos: RepoBundle) -> None:
    access = GroupAccess(repos)
    assert access.visibility(RESOURCE_SKILL_PACKAGE, "pkg", shared=False) == {
        "visibility": "owner",
        "group_ids": [],
    }
