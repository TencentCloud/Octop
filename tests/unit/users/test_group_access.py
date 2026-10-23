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
    assert version == 25
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


def test_user_group_id_is_short_and_accepts_custom(repos: RepoBundle) -> None:
    auto = repos.user_group_repo.create(name="auto", description=None)
    assert 3 <= len(auto.user_group_id) <= 8
    assert auto.user_group_id.isalnum()

    custom = repos.user_group_repo.create(
        name="custom",
        description=None,
        user_group_id="design-team",
    )
    assert custom.user_group_id == "design-team"
    assert repos.user_group_repo.get("design-team") is not None


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


def test_connector_visibility_is_per_instance(repos: RepoBundle) -> None:
    from octop.infra.users.groups import RESOURCE_CONNECTOR

    owner = _user(repos, "owner")
    member = _user(repos, "member")
    outsider = _user(repos, "outsider")
    access = GroupAccess(repos)
    # Legacy feature-wide helper is a no-op; visibility is per instance_id.
    assert repos.connector_repo.connector_feature_allows(owner)
    assert repos.connector_repo.connector_feature_allows(outsider)
    group = repos.user_group_repo.create(name="ops", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)
    instance_id = "conn-shared"
    repos.connector_repo.create(
        instance_id=instance_id,
        user_id=owner,
        kind="tencent-docs",
        display_name="Docs",
        mcp_server_name=f"connector_{instance_id}",
        shared=True,
    )
    access.set_visibility(
        RESOURCE_CONNECTOR,
        instance_id,
        "groups",
        [group.user_group_id],
    )
    assert access.allows(
        user_id=member,
        is_admin=False,
        resource_type=RESOURCE_CONNECTOR,
        resource_key=instance_id,
        is_owner=False,
    )
    assert not access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_CONNECTOR,
        resource_key=instance_id,
        is_owner=False,
    )
    assert access.allows(
        user_id=owner,
        is_admin=False,
        resource_type=RESOURCE_CONNECTOR,
        resource_key=instance_id,
        is_owner=True,
    )
    visible_for_member = {row.instance_id for row in repos.connector_repo.list_visible(member)}
    visible_for_outsider = {row.instance_id for row in repos.connector_repo.list_visible(outsider)}
    assert instance_id in visible_for_member
    assert instance_id not in visible_for_outsider


def test_storage_visibility_is_per_backend(repos: RepoBundle) -> None:
    from octop.infra.users.groups import RESOURCE_STORAGE_BACKEND

    outsider = _user(repos, "outsider")
    member = _user(repos, "member")
    admin = _user(repos, "root", role="admin")
    access = GroupAccess(repos)
    backend = "cos-main"
    assert access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=backend,
        is_owner=False,
    )
    group = repos.user_group_repo.create(name="ops", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)
    access.set_visibility(
        RESOURCE_STORAGE_BACKEND,
        backend,
        "groups",
        [group.user_group_id],
    )
    assert not access.allows(
        user_id=outsider,
        is_admin=False,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=backend,
        is_owner=False,
    )
    assert access.allows(
        user_id=member,
        is_admin=False,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=backend,
        is_owner=False,
    )
    assert access.allows(
        user_id=admin,
        is_admin=True,
        resource_type=RESOURCE_STORAGE_BACKEND,
        resource_key=backend,
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
        group_access_by_group,
        model_resource_key,
    )

    owner = _user(repos, "owner")
    group = repos.user_group_repo.create(name="ops", description=None)
    other = repos.user_group_repo.create(name="other", description=None)
    access = GroupAccess(repos)
    # Legacy feature-wide connector grant must not appear in per-instance summaries.
    access.set_visibility(
        RESOURCE_CONNECTOR, CONNECTOR_FEATURE_KEY, "groups", [group.user_group_id]
    )
    shared_id = "conn-shared"
    private_id = "conn-private"
    repos.connector_repo.create(
        instance_id=shared_id,
        user_id=owner,
        kind="tencent-docs",
        display_name="Shared Docs",
        mcp_server_name=f"connector_{shared_id}",
        shared=True,
    )
    repos.connector_repo.create(
        instance_id=private_id,
        user_id=owner,
        kind="qq-mail",
        display_name="Private Mail",
        mcp_server_name=f"connector_{private_id}",
        shared=False,
    )
    access.set_visibility(RESOURCE_CONNECTOR, shared_id, "groups", [group.user_group_id])
    repos.storage_backend_repo.create(
        name="cos-main",
        kind="cos",
        endpoint=None,
        access_key=None,
        secret_key=None,
        bucket=None,
        region=None,
        config_json=None,
        note=None,
    )
    access.set_visibility(RESOURCE_STORAGE_BACKEND, "cos-main", "groups", [group.user_group_id])
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
    assert summary["connectors"] == [
        {
            "key": "old-instance",
            "label": "old-instance",
            "missing": True,
            "audience": "groups",
        },
        {
            "key": shared_id,
            "label": "Shared Docs",
            "missing": False,
            "audience": "groups",
        },
        {
            "key": private_id,
            "label": "Private Mail",
            "missing": False,
            "audience": "owner",
        },
    ]
    assert summary["storage"] == [
        {
            "key": "cos-main",
            "label": "cos-main",
            "missing": False,
            "audience": "groups",
        }
    ]
    assert summary["plugins"] == []
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
    assert summary["bridges"] == []
    assert summary["experts"] == []
    other_summary = summaries[other.user_group_id]
    assert other_summary["connectors"] == [
        {
            "key": private_id,
            "label": "Private Mail",
            "missing": False,
            "audience": "owner",
        },
    ]
    assert other_summary["storage"] == []
    assert other_summary["plugins"] == []
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


def test_validate_visibility_rejects_empty_groups(repos: RepoBundle) -> None:
    access = GroupAccess(repos)
    with pytest.raises(OctopError) as exc:
        access.validate_visibility("groups", [])
    assert exc.value.code == ErrorCode.FORBIDDEN

    group = repos.user_group_repo.create(name="ops", description=None)
    assert access.validate_visibility("groups", [group.user_group_id]) == [group.user_group_id]
    assert access.validate_visibility("all", None) == []
    assert access.validate_visibility("owner", None) == []


def test_bridge_list_visible_respects_shared_and_grants(repos: RepoBundle) -> None:
    from octop.infra.users.groups import RESOURCE_BRIDGE

    owner = _user(repos, "bridge-owner")
    member = _user(repos, "bridge-member")
    outsider = _user(repos, "bridge-outsider")
    group = repos.user_group_repo.create(name="bridge-ops", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)

    private = repos.bridge_connection_repo.create(
        connection_id="br-private",
        owner_user_id=owner,
        peer_base_url="https://peer.example",
        peer_username="u1",
        display_name="Private Link",
        shared=False,
    )
    open_link = repos.bridge_connection_repo.create(
        connection_id="br-open",
        owner_user_id=owner,
        peer_base_url="https://peer2.example",
        peer_username="u2",
        display_name="Open Link",
        shared=True,
    )
    group_link = repos.bridge_connection_repo.create(
        connection_id="br-groups",
        owner_user_id=owner,
        peer_base_url="https://peer3.example",
        peer_username="u3",
        display_name="Group Link",
        shared=True,
    )
    GroupAccess(repos).set_visibility(
        RESOURCE_BRIDGE, group_link.connection_id, "groups", [group.user_group_id]
    )

    owner_ids = {row.connection_id for row in repos.bridge_connection_repo.list_visible(owner)}
    member_ids = {row.connection_id for row in repos.bridge_connection_repo.list_visible(member)}
    outsider_ids = {
        row.connection_id for row in repos.bridge_connection_repo.list_visible(outsider)
    }
    assert private.connection_id in owner_ids
    assert open_link.connection_id in owner_ids
    assert group_link.connection_id in owner_ids

    assert private.connection_id not in member_ids
    assert open_link.connection_id in member_ids
    assert group_link.connection_id in member_ids

    assert private.connection_id not in outsider_ids
    assert open_link.connection_id in outsider_ids
    assert group_link.connection_id not in outsider_ids


def test_shared_expert_list_respects_group_grants(repos: RepoBundle) -> None:
    from octop.infra.users.groups import RESOURCE_EXPERT, expert_visible_to

    owner = _user(repos, "expert-owner")
    member = _user(repos, "expert-member")
    outsider = _user(repos, "expert-outsider")
    group = repos.user_group_repo.create(name="expert-ops", description=None)
    repos.user_group_member_repo.add(group.user_group_id, member)

    repos.agent_repo.create(agent_id="ex-private", user_id=owner, name="Private")
    repos.agent_repo.create(agent_id="ex-open", user_id=owner, name="Open")
    repos.agent_repo.create(agent_id="ex-group", user_id=owner, name="Grouped")
    repos.agent_repo.set_shared("ex-open", True)
    repos.agent_repo.set_shared("ex-group", True)
    GroupAccess(repos).set_visibility(RESOURCE_EXPERT, "ex-group", "groups", [group.user_group_id])

    def ids(user_id: int) -> set[str]:
        return {
            row.agent_id
            for row in repos.agent_repo.list_shared(
                exclude_user_id=user_id,
                viewer_user_id=user_id,
            )
        }

    assert ids(member) == {"ex-open", "ex-group"}
    assert ids(outsider) == {"ex-open"}

    grouped = repos.agent_repo.get("ex-group")
    assert grouped is not None
    assert expert_visible_to(repos, grouped, user_id=member, is_admin=False)
    assert not expert_visible_to(repos, grouped, user_id=outsider, is_admin=False)
    assert expert_visible_to(repos, grouped, user_id=owner, is_admin=False)
    private = repos.agent_repo.get("ex-private")
    assert private is not None
    assert not expert_visible_to(repos, private, user_id=member, is_admin=False)
