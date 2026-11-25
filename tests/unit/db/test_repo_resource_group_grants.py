"""tests/unit/db/test_repo_resource_group_grants.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.resource_group_grants import ResourceGroupGrantRepo
from octop.infra.db.repos.user_groups import UserGroupRepo

_MODEL = "model"


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "x.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def group_id(db: SqlitePool) -> str:
    return UserGroupRepo(db).create(name="ops", description=None).user_group_id


@pytest.fixture
def grants(db: SqlitePool) -> ResourceGroupGrantRepo:
    return ResourceGroupGrantRepo(db)


def _grant(grants: ResourceGroupGrantRepo, group_id: str, key: str) -> None:
    grants.replace(_MODEL, key, [group_id])


def test_delete_prefix_removes_the_key_and_its_children(
    grants: ResourceGroupGrantRepo, group_id: str
) -> None:
    for key in ("openai", "openai/gpt", "openai/o3", "anthropic/claude"):
        _grant(grants, group_id, key)

    grants.delete_prefix(_MODEL, "openai")

    for key in ("openai", "openai/gpt", "openai/o3"):
        assert grants.group_ids(_MODEL, key) == set()
    assert grants.group_ids(_MODEL, "anthropic/claude") == {group_id}


def test_delete_prefix_does_not_expand_wildcard_characters(
    grants: ResourceGroupGrantRepo, group_id: str
) -> None:
    for key in ("my_pro/gpt", "myXpro/gpt", "my%pro/gpt", "aZZb/x", "a%b/x"):
        _grant(grants, group_id, key)

    grants.delete_prefix(_MODEL, "my_pro")
    grants.delete_prefix(_MODEL, "a%b")

    assert grants.group_ids(_MODEL, "my_pro/gpt") == set()
    assert grants.group_ids(_MODEL, "a%b/x") == set()
    # ``_`` and ``%`` stay literal parts of the provider name
    assert grants.group_ids(_MODEL, "myXpro/gpt") == {group_id}
    assert grants.group_ids(_MODEL, "my%pro/gpt") == {group_id}
    assert grants.group_ids(_MODEL, "aZZb/x") == {group_id}


def test_delete_prefix_is_case_sensitive(grants: ResourceGroupGrantRepo, group_id: str) -> None:
    _grant(grants, group_id, "openai/gpt")
    _grant(grants, group_id, "OpenAI/gpt")

    grants.delete_prefix(_MODEL, "openai")

    assert grants.group_ids(_MODEL, "openai/gpt") == set()
    assert grants.group_ids(_MODEL, "OpenAI/gpt") == {group_id}
