"""AUTO failover candidates stay inside the turn user's model grants."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.providers.store import AutoRouteCandidate
from octop.infra.agents.providers.turn_access import (
    filter_auto_route_candidates,
    turn_model_access,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle
from octop.infra.users.groups import RESOURCE_MODEL, GroupAccess


@pytest.fixture
def repos(tmp_path: Path) -> RepoBundle:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return RepoBundle.from_pool(pool)


def test_unbound_turn_keeps_every_candidate(repos: RepoBundle) -> None:
    candidates = [AutoRouteCandidate("openai/gpt", 1000), AutoRouteCandidate("Magpie/a", 1000)]
    assert filter_auto_route_candidates(candidates, repos=repos) == candidates


def test_turn_user_cannot_fail_over_to_a_hidden_model(repos: RepoBundle) -> None:
    user_id = repos.user_repo.create(username="member", role="user")
    outsider = repos.user_repo.create(username="outsider", role="user")
    group = repos.user_group_repo.create(name="design", description=None)
    repos.user_group_member_repo.add(group.user_group_id, user_id)
    GroupAccess(repos).set_visibility(
        RESOURCE_MODEL,
        "openai/private",
        "groups",
        [group.user_group_id],
    )
    candidates = [
        AutoRouteCandidate("Magpie/public", 8000),
        AutoRouteCandidate("openai/private", 8000),
    ]
    with turn_model_access(outsider, is_admin=False):
        allowed = filter_auto_route_candidates(candidates, repos=repos)
    assert [item.ref for item in allowed] == ["Magpie/public"]

    with turn_model_access(user_id, is_admin=False):
        allowed = filter_auto_route_candidates(candidates, repos=repos)
    assert [item.ref for item in allowed] == ["Magpie/public", "openai/private"]
