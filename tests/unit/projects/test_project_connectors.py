"""Project connector declarations — resolution rule, S1/S2, S11 (PLAN.md §1).

Real SQLite control plane + the **router handlers invoked directly**, which is the
strongest evidence available before the integration task mounts them: this fork
materializes ``include_router`` only through ``api/app.py``, so a post-build mount
is not routable (recorded in the T-CONN report). The handlers are three-line
wrappers over the service, so calling them exercises the same service call and the
same Pydantic response models the HTTP surface returns.

``GET`` / ``PUT`` both answer with the **bare array** frozen by the Lead's
shape-alignment notice (no ``{kinds: [...]}`` wrapper).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers.project_connectors import (
    ConnectorKindsIn,
    list_project_connectors,
    replace_project_connectors,
)
from octop.infra.connectors.catalog import list_catalog
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_connectors import ProjectConnectorRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.connectors import ProjectConnectorService
from octop.infra.projects.service import ProjectActor, ProjectService
from octop.infra.utils.paths import PathLayout


class Actor:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


def _connector(
    services: SimpleNamespace,
    *,
    user_id: int,
    kind: str,
    name: str,
    status: str = "active",
    shared: bool = False,
) -> str:
    instance_id = f"inst-{user_id}-{kind}-{name}"
    services.connector_repo.create(
        instance_id=instance_id,
        user_id=user_id,
        kind=kind,
        display_name=name,
        mcp_server_name=f"mcp-{instance_id}",
    )
    if shared:
        with services.db.transaction() as conn:
            conn.execute("UPDATE connectors SET shared = 1 WHERE instance_id = ?", (instance_id,))
    if status != "active":
        services.connector_repo.update_status(instance_id, status)
    return instance_id


def _rows(services: SimpleNamespace, project_id: str) -> list[str]:
    with services.db.connect() as conn:
        rows = conn.execute(
            "SELECT kind FROM project_connectors WHERE project_id = ? ORDER BY created_at, id",
            (project_id,),
        ).fetchall()
    return [str(row["kind"]) for row in rows]


def _columns(services: SimpleNamespace, table: str) -> set[str]:
    with services.db.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    services = SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        timeline_repo=TimelineRepo(pool),
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        agent_repo=AgentRepo(pool),
        thread_repo=ThreadRepo(pool),
        connector_repo=ConnectorRepo(pool),
        project_connector_repo=ProjectConnectorRepo(pool),
        paths=PathLayout.from_env(),
    )
    service = ProjectService(services)
    owner = Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))
    member = Actor(services.user_repo.create(username="member", password_hash="h", role="user"))
    project = service.create_project(owner_user=owner, name="Apollo")
    service.add_member(
        project.id,
        user=owner,
        subject_type="user",
        subject_id=str(member.id),
        role="member",
        subject_user_id=member.id,
    )
    services.project_id = project.id
    services.owner = owner
    services.member = member
    services.service = service
    services.connectors = ProjectConnectorService(services, project_service=service)
    return services


async def _list(services: SimpleNamespace, user: Actor) -> list[dict[str, Any]]:
    # The handlers take an OctopServer; wrapping the fake keeps them on the same
    # ``server.services`` path the real app uses.
    server = SimpleNamespace(services=services)
    models = await list_project_connectors(services.project_id, server=server, user=user)
    assert isinstance(models, list), "the response is a bare array, not a wrapper object"
    return [model.model_dump(mode="json") for model in models]


async def _put(services: SimpleNamespace, user: Actor, kinds: list[str]) -> list[dict[str, Any]]:
    server = SimpleNamespace(services=services)
    models = await replace_project_connectors(
        services.project_id, ConnectorKindsIn(kinds=kinds), server=server, user=user
    )
    assert isinstance(models, list), "the response is a bare array, not a wrapper object"
    return [model.model_dump(mode="json") for model in models]


def test_declaration_table_stores_kind_only(env: SimpleNamespace) -> None:
    """R17: no instance id / credential column anywhere on the declaration table."""
    assert _columns(env, "project_connectors") == {
        "id",
        "project_id",
        "kind",
        "created_by",
        "created_at",
    }
    for path in (
        "src/octop/infra/db/repos/project_connectors.py",
        "src/octop/infra/db/migrations/021_project_config.sql",
        "src/octop/infra/db/migrations/021_project_config.pg.sql",
    ):
        assert "instance_id" not in Path(path).read_text(encoding="utf-8"), path


async def test_declare_then_read_back_resolves_the_owners_instance(env: SimpleNamespace) -> None:
    kinds = [entry.kind for entry in list_catalog()]
    assert kinds, "the catalog must not be empty"
    kind = kinds[0]
    instance_id = _connector(env, user_id=env.owner.id, kind=kind, name="我的账号")

    body = await _put(env, env.owner, [kind])
    assert body == [
        {
            "kind": kind,
            "available": True,
            "resolved_instance_id": instance_id,
            "display_name": "我的账号",
        }
    ]
    assert _rows(env, env.project_id) == [kind], "the declaration row must exist"
    assert await _list(env, env.owner) == body


async def test_unknown_kind_is_400(env: SimpleNamespace) -> None:
    with pytest.raises(OctopError) as err:
        await _put(env, env.owner, ["not-a-real-kind"])
    assert err.value.code is ErrorCode.PROJECT_CONNECTOR_INVALID
    assert err.value.status == 400
    assert _rows(env, env.project_id) == []


async def test_s11_duplicate_is_409_and_replacement_drops_omitted(env: SimpleNamespace) -> None:
    kinds = [entry.kind for entry in list_catalog()][:2]
    await _put(env, env.owner, kinds)
    assert _rows(env, env.project_id) == kinds

    with pytest.raises(OctopError) as err:
        await _put(env, env.owner, [kinds[0], kinds[0]])
    assert err.value.code is ErrorCode.PROJECT_CONNECTOR_INVALID
    assert err.value.status == 409
    assert err.value.status != 500
    assert _rows(env, env.project_id) == kinds, "a refused request must not write"

    await _put(env, env.owner, [kinds[1]])
    assert _rows(env, env.project_id) == [kinds[1]], "full replacement detaches the rest"


async def test_two_users_resolve_one_declaration_differently(env: SimpleNamespace) -> None:
    kind = [entry.kind for entry in list_catalog()][0]
    owner_instance = _connector(env, user_id=env.owner.id, kind=kind, name="owner-account")
    await _put(env, env.owner, [kind])

    as_owner = await _list(env, env.owner)
    assert as_owner[0]["resolved_instance_id"] == owner_instance

    as_member = await _list(env, env.member)
    assert as_member[0]["available"] is False, "the member has no instance of that kind"
    assert as_member[0]["resolved_instance_id"] is None
    assert owner_instance not in str(as_member), "another user's instance id must never leak"

    member_instance = _connector(env, user_id=env.member.id, kind=kind, name="member-account")
    assert (await _list(env, env.member))[0]["resolved_instance_id"] == member_instance


async def test_s1_all_instances_inactive_is_available_false(env: SimpleNamespace) -> None:
    """S1: declared, but nothing active → unavailable; **not** an error (no 4xx/5xx)."""
    kind = [entry.kind for entry in list_catalog()][0]
    _connector(env, user_id=env.owner.id, kind=kind, name="disabled", status="disabled")
    _connector(env, user_id=env.owner.id, kind=kind, name="pending", status="pending")
    await _put(env, env.owner, [kind])

    body = await _list(env, env.owner)
    assert body[0] == {
        "kind": kind,
        "available": False,
        "resolved_instance_id": None,
        "display_name": None,
    }


async def test_s1_picks_the_newest_active_instance(env: SimpleNamespace) -> None:
    """§1.2: ``id DESC`` — "most recently created" is deterministic."""
    kind = [entry.kind for entry in list_catalog()][0]
    _connector(env, user_id=env.owner.id, kind=kind, name="older")
    newest = _connector(env, user_id=env.owner.id, kind=kind, name="newer")
    await _put(env, env.owner, [kind])

    body = await _list(env, env.owner)
    assert body[0]["resolved_instance_id"] == newest
    assert body[0]["display_name"] == "newer"


async def test_s2_shared_instances_do_not_resolve(env: SimpleNamespace) -> None:
    """S2: a shared instance is global and must not serve a project declaration."""
    kind = [entry.kind for entry in list_catalog()][0]
    _connector(env, user_id=env.owner.id, kind=kind, name="shared", shared=True)
    await _put(env, env.owner, [kind])

    body = await _list(env, env.owner)
    assert body[0]["available"] is False
    assert body[0]["resolved_instance_id"] is None


async def test_non_member_is_refused(env: SimpleNamespace) -> None:
    outsider = Actor(env.user_repo.create(username="outsider", password_hash="h", role="user"))
    with pytest.raises(OctopError) as err:
        await _list(env, outsider)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert err.value.status == 403


async def test_put_requires_manage_config(env: SimpleNamespace) -> None:
    """A plain member may read but not change the declaration (R18)."""
    kind = [entry.kind for entry in list_catalog()][0]
    await _put(env, env.owner, [kind])
    assert (await _list(env, env.member))[0]["kind"] == kind
    with pytest.raises(OctopError) as err:
        await _put(env, env.member, [])
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert err.value.status == 403


def test_repo_replaces_without_duplicating(env: SimpleNamespace) -> None:
    repo = ProjectConnectorRepo(env.db)
    repo.replace_all(env.project_id, ["notion", "slack"], created_by=env.owner.id)
    assert [row.kind for row in repo.list_by_project(env.project_id)] == ["notion", "slack"]
    assert repo.get(env.project_id, "notion") is not None
    assert repo.get(env.project_id, "linear") is None
    repo.replace_all(env.project_id, ["slack", "linear"], created_by=env.owner.id)
    assert [row.kind for row in repo.list_by_project(env.project_id)] == ["slack", "linear"]


def test_route_metadata_satisfies_the_openapi_contract() -> None:
    """FIND-3: summary + typed 2xx response, on project-scoped paths."""
    from octop.api.routers.project_connectors import router as connectors_router

    seen: set[tuple[str, str]] = set()
    for route in connectors_router.routes:
        path = getattr(route, "path", "")
        for method in sorted(getattr(route, "methods", set()) or set()):
            seen.add((method, path))
            assert getattr(route, "summary", "").strip(), f"{method} {path} has no summary"
            assert getattr(route, "response_model", None) is not None, f"{method} {path} untyped"
        assert "{" in path, "every route is project-scoped"
    assert seen == {
        ("GET", "/projects/{project_id}/connectors"),
        ("PUT", "/projects/{project_id}/connectors"),
    }


def test_project_actor_protocol_is_satisfied_by_the_test_actor() -> None:
    actor: ProjectActor = Actor(1)
    assert actor.id == 1 and actor.permissions
