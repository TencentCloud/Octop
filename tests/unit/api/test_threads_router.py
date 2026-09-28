"""HTTP tests for the cross-agent inbox — ``GET /api/threads/summary`` (PLAN.md §2–§5).

Boots a real ``OctopServer`` behind an ASGI client and reads the endpoint the way
the dashboard does. Two kinds of test live here:

* **Aggregation / visibility** — seeded straight through the repos (thread rows
  are the data source, and creating real turns is out of scope for a unit test),
  then read over real HTTP.
* **Project sessions (AC-T26-1, hard requirement)** — the write side runs real
  HTTP end to end: ``POST /api/projects`` → ``POST .../tasks`` →
  ``POST .../tasks/{id}:dispatch``. Only the LLM turn is stubbed: the stub creates
  a real thread row and returns its id, so ``ProjectService.dispatch_task`` still
  performs the real ``project_tasks.thread_id`` write. Every read is real HTTP.

The endpoint has no query parameters by contract (PLAN.md §2.1), so the OpenAPI
schema is asserted empty of them and the body is asserted identical with and
without unknown parameters.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_user, resolve_user_id

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo
from octop.infra.db.repos.projects import ProjectRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry

SUMMARY = "/api/threads/summary"
SUMMARY_ROW_KEYS = {"agent_id", "session_count", "has_activity", "last_active", "pinned"}
SESSION_ROW_KEYS = {
    "agent_id",
    "thread_id",
    "title",
    "channel_type",
    "last_active",
    "created_at",
    "has_messages",
    "pinned",
    "project_id",
    "project_name",
}


@dataclass
class Api:
    client: httpx.AsyncClient
    srv: Any
    admin: dict[str, str]
    bob: dict[str, str]
    admin_id: int
    bob_id: int


@pytest.fixture
async def api(tmp_octop_home: Path) -> AsyncIterator[Api]:
    """Admin plus a second regular user, over a freshly migrated instance."""
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        bob = await create_user(client, admin, username="bob")
        yield Api(
            client=client,
            srv=srv,
            admin=admin,
            bob=bob,
            admin_id=await resolve_user_id(client, admin, "admin"),
            bob_id=await resolve_user_id(client, admin, "bob"),
        )


def _seed_agent(api: Api, agent_id: str, *, user_id: int) -> str:
    """``threads.agent_id`` is a hard foreign key, so the agent row must exist."""
    api.srv.services.agent_repo.create(agent_id=agent_id, user_id=user_id, name=agent_id)
    return agent_id


def _seed_thread(
    api: Api,
    thread_id: str,
    *,
    agent_id: str,
    user_id: int,
    title: str | None = None,
    last_active: int = 0,
    pinned: bool = False,
) -> str:
    api.srv.services.thread_repo.insert(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id),
        title=title,
        last_active=last_active,
    )
    if pinned:
        api.srv.services.thread_repo.set_pinned(thread_id, True)
    return thread_id


def _rows_by_agent(payload: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["agent_id"]: row for row in payload}


# ── aggregation semantics (PLAN.md §2.3 / §2.4) ──────────────────────────────


async def test_summary_is_an_empty_list_without_conversations(api: Api) -> None:
    response = await api.client.get(SUMMARY, headers=api.admin)

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_summary_groups_by_agent_and_omits_agents_without_threads(api: Api) -> None:
    _seed_agent(api, "ag-talkative", user_id=api.admin_id)
    _seed_agent(api, "ag-quiet", user_id=api.admin_id)
    _seed_agent(api, "ag-unused", user_id=api.admin_id)
    _seed_thread(api, "thr_titled", agent_id="ag-talkative", user_id=api.admin_id, title="Hello")
    _seed_thread(api, "thr_active", agent_id="ag-talkative", user_id=api.admin_id, last_active=100)
    _seed_thread(api, "thr_created_only", agent_id="ag-quiet", user_id=api.admin_id)

    response = await api.client.get(SUMMARY, headers=api.admin)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {row["agent_id"] for row in payload} == {"ag-talkative", "ag-quiet"}
    for row in payload:
        assert set(row) == SUMMARY_ROW_KEYS

    rows = _rows_by_agent(payload)
    assert rows["ag-talkative"]["session_count"] == 2
    assert rows["ag-talkative"]["has_activity"] is True
    assert rows["ag-talkative"]["last_active"] == 100
    assert rows["ag-talkative"]["pinned"] == []
    # A thread row without a single turn still counts — the agent is not dropped.
    assert rows["ag-quiet"]["session_count"] == 1
    assert rows["ag-quiet"]["has_activity"] is False
    assert rows["ag-quiet"]["last_active"] == 0


async def test_summary_sorts_agents_by_last_active_desc_then_agent_id(api: Api) -> None:
    for agent_id, last_active in (("ag-a", 5), ("ag-b", 30), ("ag-c", 5)):
        _seed_agent(api, agent_id, user_id=api.admin_id)
        _seed_thread(
            api, f"thr_{agent_id}", agent_id=agent_id, user_id=api.admin_id, last_active=last_active
        )

    response = await api.client.get(SUMMARY, headers=api.admin)

    assert [row["agent_id"] for row in response.json()] == ["ag-b", "ag-a", "ag-c"]


async def test_summary_pinned_rows_keep_inbox_order_and_the_session_shape(api: Api) -> None:
    _seed_agent(api, "ag-pinned", user_id=api.admin_id)
    _seed_thread(api, "thr_stale_pin", agent_id="ag-pinned", user_id=api.admin_id, last_active=1)
    _seed_thread(api, "thr_fresh_pin", agent_id="ag-pinned", user_id=api.admin_id, last_active=90)
    _seed_thread(api, "thr_plain", agent_id="ag-pinned", user_id=api.admin_id, last_active=50)
    api.srv.services.thread_repo.set_pinned("thr_stale_pin", True)
    api.srv.services.thread_repo.set_pinned("thr_fresh_pin", True)

    response = await api.client.get(SUMMARY, headers=api.admin)

    row = _rows_by_agent(response.json())["ag-pinned"]
    assert [p["thread_id"] for p in row["pinned"]] == ["thr_fresh_pin", "thr_stale_pin"]
    assert row["session_count"] == 3  # pinned rows are listed, not moved out of the count
    for entry in row["pinned"]:
        assert set(entry) == SESSION_ROW_KEYS
        assert entry["pinned"] is True
        assert entry["agent_id"] == "ag-pinned"
        assert (entry["project_id"], entry["project_name"]) == (None, None)


# ── visibility: the current user only, admins included (PLAN.md §5) ──────────


async def test_summary_never_leaks_another_users_threads_not_even_for_admin(api: Api) -> None:
    _seed_agent(api, "ag-admin", user_id=api.admin_id)
    _seed_agent(api, "ag-bob", user_id=api.bob_id)
    _seed_thread(
        api,
        "thr_admin_own",
        agent_id="ag-admin",
        user_id=api.admin_id,
        title="Admin's own chat",
        pinned=True,
    )
    _seed_thread(
        api,
        "thr_bob_secret",
        agent_id="ag-bob",
        user_id=api.bob_id,
        title="Bob's secret chat",
        last_active=999,
        pinned=True,
    )

    as_admin = await api.client.get(SUMMARY, headers=api.admin)
    assert as_admin.status_code == 200, as_admin.text
    admin_text = as_admin.text
    assert [row["agent_id"] for row in as_admin.json()] == ["ag-admin"]
    assert "thr_bob_secret" not in admin_text
    assert "Bob's secret chat" not in admin_text

    as_bob = await api.client.get(SUMMARY, headers=api.bob)
    assert [row["agent_id"] for row in as_bob.json()] == ["ag-bob"]
    assert "thr_admin_own" not in as_bob.text


async def test_summary_requires_authentication(api: Api) -> None:
    response = await api.client.get(SUMMARY)

    assert response.status_code == 401, response.text


# ── no query parameters, ever (PLAN.md §2.1 / SPEC §越权) ─────────────────────


async def test_summary_ignores_unknown_query_parameters(api: Api) -> None:
    _seed_agent(api, "ag-ignore", user_id=api.admin_id)
    _seed_thread(api, "thr_one", agent_id="ag-ignore", user_id=api.admin_id, last_active=10)
    _seed_thread(api, "thr_two", agent_id="ag-ignore", user_id=api.admin_id, last_active=20)

    plain = await api.client.get(SUMMARY, headers=api.admin)
    noisy = await api.client.get(
        f"{SUMMARY}?limit=1&offset=1&as_user={api.bob_id}&user_id={api.bob_id}&unknown=1",
        headers=api.admin,
    )

    assert plain.status_code == noisy.status_code == 200
    assert plain.text == noisy.text
    assert len(plain.json()[0]["pinned"]) == 0 and plain.json()[0]["session_count"] == 2


async def test_openapi_summary_route_declares_no_parameters(api: Api) -> None:
    operation = api.client._octop_app.openapi()["paths"][SUMMARY]["get"]  # type: ignore[attr-defined]

    assert operation["summary"] == "Cross-agent session inbox"
    forbidden = {"limit", "offset", "as_user", "user_id"}
    declared = {p["name"] for p in operation.get("parameters", [])}
    assert not (declared & forbidden), declared
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["items"]["$ref"].endswith("ThreadSummaryRow")


# ── project sessions: real dispatch write, real HTTP reads (AC-T26-1) ────────


async def test_project_session_flows_from_http_dispatch_to_both_read_routes(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id = _seed_agent(api, "ag-dispatch", user_id=api.admin_id)

    created_project = await api.client.post(
        "/api/projects", headers=api.admin, json={"name": "Apollo", "goal": "land it"}
    )
    assert created_project.status_code == 201, created_project.text
    project = created_project.json()

    created_task = await api.client.post(
        f"/api/projects/{project['project_id']}/tasks",
        headers=api.admin,
        json={"title": "Ship it", "assignee_type": "agent", "assignee_id": agent_id},
    )
    assert created_task.status_code == 201, created_task.text
    task_id = created_task.json()["task_id"]

    real_threads: list[str] = []

    async def _stub_turn(**kwargs: Any) -> str:
        """The LLM turn is the only stub: a real thread row and its id come back."""
        task = kwargs["task"]
        gateway = kwargs["gateway"]
        dispatcher_user_id = kwargs["dispatcher_user_id"]
        thread_id = gateway.thread_registry.create_thread(
            agent_id=task.assignee_id,
            user_id=dispatcher_user_id,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            session_key=ThreadRegistry.dashboard_key(
                agent_id=task.assignee_id, user_id=dispatcher_user_id
            ),
            title=task.title,
        )
        real_threads.append(thread_id)
        return thread_id

    monkeypatch.setattr("octop.infra.projects.service.run_dispatch_turn", _stub_turn)

    dispatched = await api.client.post(
        f"/api/projects/{project['project_id']}/tasks/{task_id}:dispatch", headers=api.admin
    )
    assert dispatched.status_code == 200, dispatched.text
    thread_id = dispatched.json()["thread_id"]
    assert thread_id and thread_id == real_threads[0]

    # The write landed on the real column, not on a stub.
    stored = api.srv.services.project_task_repo.get(task_id)
    assert stored is not None and stored.thread_id == thread_id

    # ① per-agent thread list: the row carries the project it was dispatched from.
    listed = await api.client.get(f"/api/agents/{agent_id}/threads", headers=api.admin)
    assert listed.status_code == 200, listed.text
    listed_rows = {r["thread_id"]: r for r in listed.json()}
    assert listed_rows[thread_id]["project_id"] == project["project_id"]
    assert listed_rows[thread_id]["project_name"] == project["name"]

    # ② pinned inbox row: same two fields, from the same reverse lookup.
    pinned = await api.client.patch(
        f"/api/agents/{agent_id}/threads/{thread_id}", headers=api.admin, json={"pinned": True}
    )
    assert pinned.status_code == 200, pinned.text
    manual = await api.client.post(f"/api/agents/{agent_id}/threads", headers=api.admin)
    assert manual.status_code == 201, manual.text
    manual_thread_id = manual.json()["thread_id"]
    await api.client.patch(
        f"/api/agents/{agent_id}/threads/{manual_thread_id}",
        headers=api.admin,
        json={"pinned": True},
    )

    inbox = await api.client.get(SUMMARY, headers=api.admin)
    assert inbox.status_code == 200, inbox.text
    entry = _rows_by_agent(inbox.json())[agent_id]
    pinned_rows = {p["thread_id"]: p for p in entry["pinned"]}
    assert set(pinned_rows) == {thread_id, manual_thread_id}
    assert pinned_rows[thread_id]["project_id"] == project["project_id"]
    assert pinned_rows[thread_id]["project_name"] == project["name"]
    # A conversation opened by hand is not a project chat — both fields stay null.
    assert pinned_rows[manual_thread_id]["project_id"] is None
    assert pinned_rows[manual_thread_id]["project_name"] is None


# ── the reverse lookup itself (PLAN.md §4.2) ─────────────────────────────────


@pytest.fixture
def repos(tmp_path: Path) -> tuple[ProjectRepo, ProjectTaskRepo, ThreadRepo, SqlitePool, int]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    owner = UserRepo(db).create(username="owner", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=owner, name="Agent 1")
    threads = ThreadRepo(db)
    threads.insert(
        thread_id="thr_bound",
        agent_id="a1",
        user_id=owner,
        channel_type="dashboard",
        session_key=ThreadRegistry.dashboard_key(agent_id="a1", user_id=owner),
    )
    return ProjectRepo(db), ProjectTaskRepo(db), threads, db, owner


def test_projects_by_thread_returns_empty_without_issuing_sql() -> None:
    class _NoConnect:
        def connect(self) -> Any:  # pragma: no cover - only reached on a bug
            raise AssertionError("empty input must not query the database")

    assert ProjectRepo(_NoConnect()).projects_by_thread([]) == {}  # type: ignore[arg-type]


def test_projects_by_thread_prefers_the_most_recent_task(
    repos: tuple[ProjectRepo, ProjectTaskRepo, ThreadRepo, SqlitePool, int],
) -> None:
    projects, tasks, _, db, owner = repos
    first = projects.create(owner_user_id=owner, name="First")
    second = projects.create(owner_user_id=owner, name="Second")
    older = tasks.create(
        project_id=first.id, title="older", created_by=owner, thread_id="thr_bound"
    )
    newer = tasks.create(
        project_id=second.id, title="newer", created_by=owner, thread_id="thr_bound"
    )
    with db.transaction() as conn:
        conn.execute("UPDATE project_tasks SET updated_at = 100 WHERE task_id = ?", (older.id,))
        conn.execute("UPDATE project_tasks SET updated_at = 200 WHERE task_id = ?", (newer.id,))

    refs = projects.projects_by_thread(["thr_bound", "thr_unknown"])

    assert set(refs) == {"thr_bound"}
    assert (refs["thr_bound"].project_id, refs["thr_bound"].project_name) == (second.id, "Second")


def test_projects_by_thread_breaks_updated_at_ties_on_task_id_desc(
    repos: tuple[ProjectRepo, ProjectTaskRepo, ThreadRepo, SqlitePool, int],
) -> None:
    projects, tasks, _, db, owner = repos
    first = projects.create(owner_user_id=owner, name="First")
    second = projects.create(owner_user_id=owner, name="Second")
    a = tasks.create(project_id=first.id, title="a", created_by=owner, thread_id="thr_bound")
    b = tasks.create(project_id=second.id, title="b", created_by=owner, thread_id="thr_bound")
    with db.transaction() as conn:
        conn.execute("UPDATE project_tasks SET updated_at = 500")

    refs = projects.projects_by_thread(["thr_bound"])

    winner = first if a.id > b.id else second
    assert refs["thr_bound"].project_id == winner.id
    assert refs["thr_bound"].project_name == winner.name


def test_projects_by_thread_ignores_task_and_project_status(
    repos: tuple[ProjectRepo, ProjectTaskRepo, ThreadRepo, SqlitePool, int],
) -> None:
    projects, tasks, _, db, owner = repos
    archived = projects.create(owner_user_id=owner, name="Archived")
    task = tasks.create(
        project_id=archived.id,
        title="dropped",
        created_by=owner,
        thread_id="thr_bound",
        status="cancelled",
    )
    projects.update(archived.id, status="archived")

    assert projects.projects_by_thread(["thr_bound"])["thr_bound"].project_id == archived.id
    assert task.status == "cancelled"
