"""HTTP integration tests for the project-management feature (S2).

Boots a real ``OctopServer`` behind an ASGI ``httpx`` client (``tests/support/app.py``
via the ``env`` fixture in ``tests/integration/conftest.py``) and drives
``/api/projects`` end to end:

* **AC-13** — a non-member is refused every project-scoped resource, and a platform
  admin who is not a member is refused as well (membership is the only way in).
* **AC-16** — an expert shared into project A stays unreachable from project B.
* **Permission matrix (§4.6)** — viewer writes are role-forbidden, ``admin`` cannot
  archive, an archived project is read-only.
* The project and task state machines, and the error codes they report.

Every refusal asserts the error **code**, not just the status: a 403 carrying
``FORBIDDEN`` would mean the coarse ``projects`` key rejected the caller before the
membership gate ran, i.e. the guard under test never fired.

Two deliberate scoping decisions:

* ``kb_id`` is never asserted. On a fresh instance the knowledge feature is off, so
  ``POST /api/projects`` legitimately succeeds with ``kb_id = NULL``; asserting that a
  knowledge base exists would re-introduce the deployment bug this suite guards against.
* ``POST /api/projects/{id}/tasks/{tid}:dispatch`` is out of scope here — it belongs to
  the T2.5 dispatch work, not the CRUD / board surface this suite covers.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.support.auth import ensure_users, resolve_user_id

PROJECTS = "/api/projects"


# ── helpers ──────────────────────────────────────────────────────────────────


def _error_code(response: httpx.Response) -> str:
    """Code from the standard ``{"error": {"code": ...}}`` envelope."""
    return str(response.json()["error"]["code"])


async def _create_project(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    name: str,
    *,
    goal: str = "",
) -> dict[str, Any]:
    r = await client.post(PROJECTS, headers=auth, json={"name": name, "goal": goal})
    assert r.status_code == 201, r.text
    return r.json()


async def _create_task(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    project_id: str,
    title: str,
    **fields: Any,
) -> dict[str, Any]:
    r = await client.post(
        f"{PROJECTS}/{project_id}/tasks",
        headers=auth,
        json={"title": title, **fields},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _add_member(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    project_id: str,
    *,
    subject_id: str,
    role: str,
    subject_type: str = "user",
) -> dict[str, Any]:
    r = await client.post(
        f"{PROJECTS}/{project_id}/members",
        headers=auth,
        json={"subject_type": subject_type, "subject_id": subject_id, "role": role},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _set_project_status(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    project_id: str,
    target: str,
) -> httpx.Response:
    return await client.patch(f"{PROJECTS}/{project_id}", headers=auth, json={"status": target})


async def _activate(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    project_id: str,
) -> dict[str, Any]:
    """``draft -> active``; archiving is only legal from ``active`` / ``paused``."""
    r = await _set_project_status(client, auth, project_id, "active")
    assert r.status_code == 200, r.text
    return r.json()


async def _task(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    project_id: str,
    task_id: str,
) -> dict[str, Any]:
    """One task as the board shows it (there is no single-task GET route)."""
    r = await client.get(f"{PROJECTS}/{project_id}/tasks", headers=auth)
    assert r.status_code == 200, r.text
    rows = [t for t in r.json() if t["task_id"] == task_id]
    assert rows, f"task {task_id} is missing from the board"
    return rows[0]


async def _create_expert(client: httpx.AsyncClient, auth: dict[str, str], name: str) -> str:
    """Create an agent to share into a project — an "expert" in plan terms."""
    r = await client.post("/api/agents", headers=auth, json={"name": name})
    assert r.status_code == 201, r.text
    return str(r.json()["agent_id"])


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def users(env: Any) -> dict[str, Any]:
    """alice / bob / carol — regular users, all holding the baseline ``projects`` key."""
    client, _srv, admin_auth = env
    auths = await ensure_users(client, admin_auth, "alice", "bob", "carol")
    ids = {name: await resolve_user_id(client, admin_auth, name) for name in auths}
    assert len(set(ids.values())) == len(ids), "usernames must map to distinct user ids"
    return {"auth": auths, "id": ids}


@pytest.fixture
async def owned(env: Any, users: dict[str, Any]) -> dict[str, Any]:
    """Project ``Apollo`` (owner: alice) in ``draft``, holding one ``planning`` task."""
    client = env[0]
    alice = users["auth"]["alice"]
    project = await _create_project(client, alice, "Apollo", goal="Ship the lunar board")
    task = await _create_task(client, alice, project["project_id"], "Draft the flight plan")
    return {
        "project": project,
        "project_id": project["project_id"],
        "task": task,
        "task_id": task["task_id"],
    }


# ── AC-13: a non-member gets nothing ─────────────────────────────────────────


async def test_ac13_non_member_refused_every_project_resource(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """Non-member vs. 5 resource kinds × every verb they expose — all 403.

    The plan words AC-13 as "5 resource kinds × 4 methods". A kind that exposes
    fewer verbs than four is listed with the verbs that exist (``timeline`` is
    read-only; ``POST /api/projects/{id}`` is not a route, and a 405 would prove
    nothing about the membership gate), while ``tasks`` + ``task`` together carry
    all four verbs. The per-case id names the exact failure.
    """
    client = env[0]
    carol = users["auth"]["carol"]
    alice = users["auth"]["alice"]
    pid = owned["project_id"]
    tid = owned["task_id"]
    uid = str(users["id"]["bob"])

    cases: tuple[tuple[str, str, str, dict[str, Any] | None], ...] = (
        # kind: project — detail / edit / archive (3 verbs)
        ("project.detail", "GET", f"{PROJECTS}/{pid}", None),
        ("project.edit", "PATCH", f"{PROJECTS}/{pid}", {"goal": "hijacked by a non-member"}),
        ("project.archive", "DELETE", f"{PROJECTS}/{pid}", None),
        # kind: members — list / add / remove (3 verbs)
        ("members.list", "GET", f"{PROJECTS}/{pid}/members", None),
        (
            "members.add",
            "POST",
            f"{PROJECTS}/{pid}/members",
            {"subject_type": "user", "subject_id": uid, "role": "admin"},
        ),
        ("members.remove", "DELETE", f"{PROJECTS}/{pid}/members/user/{uid}", None),
        # kind: tasks — the board collection (2 verbs)
        ("tasks.list", "GET", f"{PROJECTS}/{pid}/tasks", None),
        ("tasks.create", "POST", f"{PROJECTS}/{pid}/tasks", {"title": "planted by a non-member"}),
        # kind: task — item mutation (2 verbs)
        ("task.patch_title", "PATCH", f"{PROJECTS}/{pid}/tasks/{tid}", {"title": "hijacked"}),
        ("task.patch_status", "PATCH", f"{PROJECTS}/{pid}/tasks/{tid}", {"status": "done"}),
        ("task.delete", "DELETE", f"{PROJECTS}/{pid}/tasks/{tid}", None),
        # kind: timeline — read-only (1 verb)
        ("timeline.list", "GET", f"{PROJECTS}/{pid}/timeline", None),
    )
    assert len({case_id.split(".")[0] for case_id, *_ in cases}) == 5, "5 resource kinds"
    assert len(cases) == 12, "12 verb cases"

    for case_id, method, path, body in cases:
        response = await client.request(method, path, headers=carol, json=body)
        assert response.status_code == 403, (
            f"{case_id}: expected 403 for a non-member, got {response.status_code}: {response.text}"
        )
        assert _error_code(response) == "PROJECT_FORBIDDEN", (
            f"{case_id}: refused by the wrong guard (want the membership gate): {response.text}"
        )

    # The list endpoint (the one read that is not project-scoped) must not leak it either.
    listed = await client.get(PROJECTS, headers=carol)
    assert listed.status_code == 200, listed.text
    assert [p["project_id"] for p in listed.json()] == [], "a non-member sees no projects"

    # A refused write must not have applied: the owner still sees the original rows.
    detail = await client.get(f"{PROJECTS}/{pid}", headers=alice)
    assert detail.status_code == 200, detail.text
    assert (detail.json()["goal"], detail.json()["status"]) == ("Ship the lunar board", "draft")
    after = await _task(client, alice, pid, tid)
    assert (after["title"], after["status"]) == ("Draft the flight plan", "planning")


async def test_ac13_platform_admin_is_not_a_membership_bypass(
    env: Any,
    owned: dict[str, Any],
) -> None:
    """The bootstrap admin is not a project member, so project data stays shut.

    ``is_admin`` bypasses the coarse ``projects`` permission key, so this test
    proves the 403 comes from the membership gate rather than the key.
    """
    client, _srv, admin_auth = env
    pid = owned["project_id"]

    for method, body in (("GET", None), ("PATCH", {"name": "renamed by the platform admin"})):
        response = await client.request(method, f"{PROJECTS}/{pid}", headers=admin_auth, json=body)
        assert response.status_code == 403, f"{method}: {response.status_code} {response.text}"
        assert _error_code(response) == "PROJECT_FORBIDDEN", response.text

    archived = await client.delete(f"{PROJECTS}/{pid}", headers=admin_auth)
    assert archived.status_code == 403, archived.text
    assert _error_code(archived) == "PROJECT_FORBIDDEN", archived.text

    listed = await client.get(PROJECTS, headers=admin_auth)
    assert pid not in [p["project_id"] for p in listed.json()], "admin list is mine-only"


# ── AC-16: cross-project isolation ───────────────────────────────────────────


async def test_ac16_project_a_expert_unreachable_from_project_b(
    env: Any,
    users: dict[str, Any],
) -> None:
    """Project A's shared expert is not reachable by an unauthorized project B.

    alice owns A and shares her expert (an agent) into it as a member, plus a task
    assigned to that expert. bob is authorized in B only. Every route that could
    disclose or touch A's data — including A's task addressed through B's own path —
    must refuse bob, and nothing may change.
    """
    client = env[0]
    alice = users["auth"]["alice"]
    bob = users["auth"]["bob"]

    project_a = await _create_project(client, alice, "Apollo", goal="Ship the lunar board")
    pid_a = project_a["project_id"]
    expert_id = await _create_expert(client, alice, "apollo-expert")
    await _add_member(
        client, alice, pid_a, subject_id=expert_id, role="member", subject_type="agent"
    )
    task_a = await _create_task(
        client,
        alice,
        pid_a,
        "Draft the flight plan",
        assignee_type="agent",
        assignee_id=expert_id,
    )
    project_b = await _create_project(client, bob, "Borealis")
    pid_b = project_b["project_id"]

    # Contrast 1: alice (member of A) sees the expert and its task; A is intact.
    members = await client.get(f"{PROJECTS}/{pid_a}/members", headers=alice)
    assert members.status_code == 200, members.text
    assert any(
        m["subject_type"] == "agent" and m["subject_id"] == expert_id for m in members.json()
    ), "the expert is shared into project A"
    assert (await _task(client, alice, pid_a, task_a["task_id"]))["assignee_id"] == expert_id

    # Contrast 2: bob (authorized in B, not in A) is refused every A resource.
    for path in (
        f"{PROJECTS}/{pid_a}",
        f"{PROJECTS}/{pid_a}/members",
        f"{PROJECTS}/{pid_a}/tasks",
        f"{PROJECTS}/{pid_a}/timeline",
    ):
        response = await client.get(path, headers=bob)
        assert response.status_code == 403, f"{path}: {response.status_code} {response.text}"
        assert _error_code(response) == "PROJECT_FORBIDDEN", response.text
        assert expert_id not in response.text, f"{path} leaked the shared expert"

    # Reaching A's expert through B's own task path is refused too. Today the role
    # check on the task's real project answers 403; a 404 (as the dispatch path
    # deliberately returns) is an equally valid refusal — either way bob gets no
    # data and no write.
    reach_through_b = await client.patch(
        f"{PROJECTS}/{pid_b}/tasks/{task_a['task_id']}",
        headers=bob,
        json={"title": "hijacked through project B"},
    )
    assert reach_through_b.status_code in (403, 404), reach_through_b.text
    assert _error_code(reach_through_b) in ("PROJECT_FORBIDDEN", "PROJECT_TASK_NOT_FOUND")
    assert task_a["task_id"] not in reach_through_b.text

    # The refused write left A's task exactly as it was.
    unchanged = await _task(client, alice, pid_a, task_a["task_id"])
    assert unchanged["title"] == "Draft the flight plan"
    assert unchanged["assignee_id"] == expert_id

    # Contrast 3: the isolation is symmetric — bob's own project is fully usable,
    # and alice (not a member of B) cannot read it.
    own_members = await client.get(f"{PROJECTS}/{pid_b}/members", headers=bob)
    assert own_members.status_code == 200, own_members.text
    assert [m["subject_id"] for m in own_members.json()] == [str(users["id"]["bob"])]
    cross = await client.get(f"{PROJECTS}/{pid_b}/tasks", headers=alice)
    assert cross.status_code == 403, cross.text
    assert _error_code(cross) == "PROJECT_FORBIDDEN", cross.text
    listed = await client.get(PROJECTS, headers=bob)
    assert [p["project_id"] for p in listed.json()] == [pid_b], "bob sees only his project"


# ── permission matrix (§4.6) ─────────────────────────────────────────────────


async def test_viewer_reads_but_every_write_is_role_forbidden(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """A ``viewer`` reads the whole project and is refused every write (§4.6)."""
    client = env[0]
    alice = users["auth"]["alice"]
    carol = users["auth"]["carol"]
    pid = owned["project_id"]
    tid = owned["task_id"]
    await _add_member(client, alice, pid, subject_id=str(users["id"]["carol"]), role="viewer")
    await _activate(client, alice, pid)

    for path in (
        f"{PROJECTS}/{pid}",
        f"{PROJECTS}/{pid}/members",
        f"{PROJECTS}/{pid}/tasks",
        f"{PROJECTS}/{pid}/timeline",
    ):
        response = await client.get(path, headers=carol)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"

    writes: tuple[tuple[str, str, dict[str, Any] | None], ...] = (
        ("project.edit", "PATCH", f"{PROJECTS}/{pid}", {"goal": "viewer edit"}),
        ("project.archive", "DELETE", f"{PROJECTS}/{pid}", None),
        (
            "members.add",
            "POST",
            f"{PROJECTS}/{pid}/members",
            {"subject_type": "user", "subject_id": str(users["id"]["bob"]), "role": "member"},
        ),
        (
            "members.remove",
            "DELETE",
            f"{PROJECTS}/{pid}/members/user/{users['id']['bob']}",
            None,
        ),
        ("tasks.create", "POST", f"{PROJECTS}/{pid}/tasks", {"title": "viewer task"}),
        ("task.patch_title", "PATCH", f"{PROJECTS}/{pid}/tasks/{tid}", {"title": "viewer edit"}),
        ("task.patch_status", "PATCH", f"{PROJECTS}/{pid}/tasks/{tid}", {"status": "doing"}),
        ("task.delete", "DELETE", f"{PROJECTS}/{pid}/tasks/{tid}", None),
    )
    for case_id, method, path, body in writes:
        response = await client.request(method, path, headers=carol, json=body)
        assert response.status_code == 403, (
            f"{case_id}: expected 403 for a viewer, got {response.status_code}: {response.text}"
        )
        assert _error_code(response) == "PROJECT_ROLE_FORBIDDEN", (
            f"{case_id}: a viewer is a member whose role is too weak: {response.text}"
        )

    detail = await client.get(f"{PROJECTS}/{pid}", headers=alice)
    assert detail.json()["goal"] == "Ship the lunar board"
    assert detail.json()["status"] == "active"
    after = await _task(client, alice, pid, tid)
    assert (after["title"], after["status"]) == ("Draft the flight plan", "planning")


async def test_member_writes_tasks_but_not_membership_or_archive(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """``member`` has ``write`` but neither ``manage_members`` nor ``archive``."""
    client = env[0]
    alice = users["auth"]["alice"]
    bob = users["auth"]["bob"]
    pid = owned["project_id"]
    await _add_member(client, alice, pid, subject_id=str(users["id"]["bob"]), role="member")
    await _activate(client, alice, pid)

    created = await _create_task(client, bob, pid, "Bob's task")
    assert created["status"] == "planning", "new tasks start unscheduled (AC-U-3)"
    scheduled = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{created['task_id']}", headers=bob, json={"status": "todo"}
    )
    assert scheduled.status_code == 200, scheduled.text
    moved = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{created['task_id']}", headers=bob, json={"status": "doing"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "doing"
    timeline = await client.get(f"{PROJECTS}/{pid}/timeline", headers=bob)
    assert timeline.status_code == 200, timeline.text

    add = await client.post(
        f"{PROJECTS}/{pid}/members",
        headers=bob,
        json={"subject_type": "user", "subject_id": str(users["id"]["carol"]), "role": "viewer"},
    )
    assert add.status_code == 403, add.text
    assert _error_code(add) == "PROJECT_ROLE_FORBIDDEN", add.text
    archived = await client.delete(f"{PROJECTS}/{pid}", headers=bob)
    assert archived.status_code == 403, archived.text
    assert _error_code(archived) == "PROJECT_ROLE_FORBIDDEN", archived.text


async def test_admin_manages_members_but_cannot_archive(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """``admin`` reaches ``manage_members`` but not ``archive`` — owner only (§4.6)."""
    client = env[0]
    alice = users["auth"]["alice"]
    carol = users["auth"]["carol"]
    pid = owned["project_id"]
    await _add_member(client, alice, pid, subject_id=str(users["id"]["carol"]), role="admin")
    await _activate(client, alice, pid)

    edited = await client.patch(f"{PROJECTS}/{pid}", headers=carol, json={"goal": "admin goal"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["goal"] == "admin goal"
    added = await _add_member(client, carol, pid, subject_id=str(users["id"]["bob"]), role="member")
    assert added["role"] == "member"
    removed = await client.delete(
        f"{PROJECTS}/{pid}/members/user/{users['id']['bob']}", headers=carol
    )
    assert removed.status_code == 200, removed.text

    denied = await client.delete(f"{PROJECTS}/{pid}", headers=carol)
    assert denied.status_code == 403, denied.text
    assert _error_code(denied) == "PROJECT_ROLE_FORBIDDEN", denied.text
    still_active = await client.get(f"{PROJECTS}/{pid}", headers=alice)
    assert still_active.json()["status"] == "active", "a denied archive must change nothing"

    archived = await client.delete(f"{PROJECTS}/{pid}", headers=alice)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"


async def test_archived_project_is_read_only(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """``archived`` is terminal: reads stay 200, every write is refused as archived."""
    client = env[0]
    alice = users["auth"]["alice"]
    pid = owned["project_id"]
    tid = owned["task_id"]
    await _add_member(client, alice, pid, subject_id=str(users["id"]["bob"]), role="member")
    await _activate(client, alice, pid)
    archived = await client.delete(f"{PROJECTS}/{pid}", headers=alice)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    for path in (
        f"{PROJECTS}/{pid}",
        f"{PROJECTS}/{pid}/members",
        f"{PROJECTS}/{pid}/tasks",
        f"{PROJECTS}/{pid}/timeline",
    ):
        response = await client.get(path, headers=alice)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"

    writes: tuple[tuple[str, str, str, dict[str, Any] | None], ...] = (
        ("owner", "PATCH", f"{PROJECTS}/{pid}", {"name": "renamed after archive"}),
        ("owner", "PATCH", f"{PROJECTS}/{pid}", {"status": "active"}),
        ("owner", "POST", f"{PROJECTS}/{pid}/tasks", {"title": "task after archive"}),
        ("owner", "PATCH", f"{PROJECTS}/{pid}/tasks/{tid}", {"title": "edit after archive"}),
        ("owner", "PATCH", f"{PROJECTS}/{pid}/tasks/{tid}", {"status": "doing"}),
        ("owner", "DELETE", f"{PROJECTS}/{pid}/tasks/{tid}", None),
        ("member", "POST", f"{PROJECTS}/{pid}/tasks", {"title": "member task after archive"}),
    )
    for who, method, path, body in writes:
        headers = alice if who == "owner" else users["auth"]["bob"]
        response = await client.request(method, path, headers=headers, json=body)
        assert response.status_code == 403, (
            f"{who} {method} {path}: expected 403 on an archived project, "
            f"got {response.status_code}: {response.text}"
        )
        assert _error_code(response) == "PROJECT_FORBIDDEN", (
            f"archive refusal is 'not writable', not 'wrong role': {response.text}"
        )

    detail = await client.get(f"{PROJECTS}/{pid}", headers=alice)
    assert (detail.json()["name"], detail.json()["status"]) == ("Apollo", "archived")
    after = await _task(client, alice, pid, tid)
    assert (after["title"], after["status"]) == ("Draft the flight plan", "planning")
    listed = await client.get(PROJECTS, headers=alice)
    assert pid in [p["project_id"] for p in listed.json()], "archived is not deleted"


# ── state machines ───────────────────────────────────────────────────────────


async def test_task_status_machine(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """``planning -> todo -> doing`` is legal and persists; ``planning -> review`` is a 409.

    Reflects PLAN.md §1.2: ``planning``'s only working exit is ``todo``, so a new
    task cannot jump straight into ``doing`` — the suite walks the frozen graph.
    """
    client = env[0]
    alice = users["auth"]["alice"]
    pid = owned["project_id"]
    tid = owned["task_id"]

    # planning 出边 = {todo, cancelled}: ``review`` is not reachable from it.
    illegal = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{tid}", headers=alice, json={"status": "review"}
    )
    assert illegal.status_code == 409, illegal.text
    assert _error_code(illegal) == "PROJECT_TASK_STATUS_INVALID", illegal.text
    assert (await _task(client, alice, pid, tid))["status"] == "planning", "409 must not write"
    timeline = await client.get(f"{PROJECTS}/{pid}/timeline", headers=alice)
    assert [e["action"] for e in timeline.json()] == ["task.created"], (
        "a refused transition must not append a timeline row"
    )

    planning = await client.get(f"{PROJECTS}/{pid}/tasks?status=planning", headers=alice)
    assert [t["task_id"] for t in planning.json()] == [tid], "the new task sits in planning"

    scheduled = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{tid}", headers=alice, json={"status": "todo"}
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["status"] == "todo"

    legal = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{tid}", headers=alice, json={"status": "doing"}
    )
    assert legal.status_code == 200, legal.text
    assert legal.json()["status"] == "doing"
    assert (await _task(client, alice, pid, tid))["status"] == "doing", "the transition persists"

    doing = await client.get(f"{PROJECTS}/{pid}/tasks?status=doing", headers=alice)
    assert [t["task_id"] for t in doing.json()] == [tid]
    todo = await client.get(f"{PROJECTS}/{pid}/tasks?status=todo", headers=alice)
    assert todo.json() == []
    events = (await client.get(f"{PROJECTS}/{pid}/timeline", headers=alice)).json()
    assert [e["action"] for e in events] == [
        "task.created",
        "task.status_changed",
        "task.status_changed",
    ]
    assert events[1]["task_id"] == tid
    assert events[1]["payload"] == {"from": "planning", "to": "todo"}
    assert events[2]["payload"] == {"from": "todo", "to": "doing"}


async def test_project_status_machine_and_missing_ids(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """Illegal project transitions are 409; unknown project / task ids are 404."""
    client = env[0]
    alice = users["auth"]["alice"]
    pid = owned["project_id"]

    illegal = await _set_project_status(client, alice, pid, "paused")
    assert illegal.status_code == 409, illegal.text
    assert _error_code(illegal) == "PROJECT_STATUS_INVALID", illegal.text
    assert (await client.get(f"{PROJECTS}/{pid}", headers=alice)).json()["status"] == "draft"

    assert (await _activate(client, alice, pid))["status"] == "active"
    again = await _set_project_status(client, alice, pid, "active")
    assert again.status_code == 409, again.text
    assert _error_code(again) == "PROJECT_STATUS_INVALID", again.text

    missing = "prj_does_not_exist"
    for method, body in (("GET", None), ("PATCH", {"goal": "x"}), ("DELETE", None)):
        response = await client.request(method, f"{PROJECTS}/{missing}", headers=alice, json=body)
        assert response.status_code == 404, f"{method}: {response.status_code} {response.text}"
        assert _error_code(response) == "PROJECT_NOT_FOUND", response.text

    missing_task = "tsk_does_not_exist"
    for method, body in (
        ("PATCH", {"title": "x"}),
        ("PATCH", {"status": "doing"}),
        ("DELETE", None),
    ):
        response = await client.request(
            method, f"{PROJECTS}/{pid}/tasks/{missing_task}", headers=alice, json=body
        )
        assert response.status_code == 404, f"{method}: {response.status_code} {response.text}"
        assert _error_code(response) == "PROJECT_TASK_NOT_FOUND", response.text


async def test_non_member_cannot_reach_a_task_by_guessing_its_id(
    env: Any,
    users: dict[str, Any],
    owned: dict[str, Any],
) -> None:
    """Guessing a ``task_id`` buys a non-member nothing: refused, and the task survives."""
    client = env[0]
    alice = users["auth"]["alice"]
    carol = users["auth"]["carol"]
    pid = owned["project_id"]
    tid = owned["task_id"]

    for method, body in (
        ("PATCH", {"title": "hijacked by id guessing"}),
        ("PATCH", {"status": "done"}),
        ("DELETE", None),
    ):
        response = await client.request(
            method, f"{PROJECTS}/{pid}/tasks/{tid}", headers=carol, json=body
        )
        assert response.status_code == 403, f"{method}: {response.status_code} {response.text}"
        assert _error_code(response) == "PROJECT_FORBIDDEN", response.text
        assert tid not in response.text, "a refused response must not echo the task"

    after = await _task(client, alice, pid, tid)
    assert (after["title"], after["status"]) == ("Draft the flight plan", "planning")
