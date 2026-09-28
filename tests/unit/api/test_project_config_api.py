"""Real-HTTP end-to-end for the second-batch project config surface (T-INT2).

Exercises the four newly mounted routers through the real app: connector
declarations, project cron jobs, the project instruction, and the skill
projection. Each subsystem is asserted on its **status code and response shape**,
including the authorization refusals a non-member gets.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_user

PROJECTS = "/api/projects"
AGENT_ID = "ag-exec"


@pytest.fixture
async def api(tmp_octop_home: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, Any]]]:
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        bob = await create_user(client, admin, username="bob")
        created = await client.post(
            f"{PROJECTS}", headers=admin, json={"name": "Apollo", "status": "active"}
        )
        assert created.status_code == 201, created.text
        pid = created.json()["project_id"]
        srv.services.agent_repo.create(agent_id=AGENT_ID, user_id=1, name="Exec")
        member = await client.post(
            f"{PROJECTS}/{pid}/members",
            headers=admin,
            json={"subject_type": "agent", "subject_id": AGENT_ID, "role": "member"},
        )
        assert member.status_code == 201, member.text
        yield client, srv, {"admin": admin, "bob": bob, "pid": pid}


async def test_connectors_read_replace_and_duplicate(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid = ctx["pid"]

    listed = await client.get(f"{PROJECTS}/{pid}/connectors", headers=ctx["admin"])
    assert listed.status_code == 200, listed.text
    assert listed.json() == [], "a project with no declaration answers a bare array"

    replaced = await client.put(
        f"{PROJECTS}/{pid}/connectors", headers=ctx["admin"], json={"kinds": []}
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json() == []

    duplicate = await client.put(
        f"{PROJECTS}/{pid}/connectors",
        headers=ctx["admin"],
        json={"kinds": ["notion", "notion"]},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.status_code != 500
    assert duplicate.json()["error"]["code"] == "PROJECT_CONNECTOR_INVALID"

    unknown = await client.put(
        f"{PROJECTS}/{pid}/connectors", headers=ctx["admin"], json={"kinds": ["nope"]}
    )
    assert unknown.status_code == 400, unknown.text
    assert unknown.json()["error"]["code"] == "PROJECT_CONNECTOR_INVALID"


async def test_cron_full_cycle_and_delete_envelope(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, auth = ctx["pid"], ctx["admin"]

    assert (await client.get(f"{PROJECTS}/{pid}/cron", headers=auth)).json() == []

    created = await client.post(
        f"{PROJECTS}/{pid}/cron",
        headers=auth,
        json={"agent_id": AGENT_ID, "schedule_spec": "@every 1h", "prompt": "ping"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["owned_by_me"] is True and body["prompt"] == "ping"
    assert body["prompt_hidden"] is False
    cron_id = body["cron_id"]

    listed = await client.get(f"{PROJECTS}/{pid}/cron", headers=auth)
    assert [job["cron_id"] for job in listed.json()] == [cron_id]

    toggled = await client.patch(
        f"{PROJECTS}/{pid}/cron/{cron_id}", headers=auth, json={"enabled": False}
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["enabled"] is False

    non_member_agent = await client.post(
        f"{PROJECTS}/{pid}/cron",
        headers=auth,
        json={"agent_id": "ag-ghost", "schedule_spec": "@every 1h", "prompt": "x"},
    )
    assert non_member_agent.status_code == 409, non_member_agent.text
    assert non_member_agent.json()["error"]["code"] == "PROJECT_CRON_INVALID"

    deleted = await client.delete(f"{PROJECTS}/{pid}/cron/{cron_id}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}, "the delete envelope keeps the key name"
    assert (await client.get(f"{PROJECTS}/{pid}/cron", headers=auth)).json() == []


async def test_instruction_round_trip(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, auth = ctx["pid"], ctx["admin"]

    empty = await client.get(f"{PROJECTS}/{pid}/instruction", headers=auth)
    assert empty.status_code == 200, empty.text
    assert empty.json()["instruction"] == "", "an unset instruction is empty, not an error"

    written = await client.put(
        f"{PROJECTS}/{pid}/instruction", headers=auth, json={"instruction": "keep it short"}
    )
    assert written.status_code == 200, written.text
    assert written.json()["instruction"] == "keep it short"
    read_back = await client.get(f"{PROJECTS}/{pid}/instruction", headers=auth)
    assert read_back.json()["instruction"] == "keep it short"


async def test_skills_get_and_put_share_one_shape(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, auth = ctx["pid"], ctx["admin"]

    listed = await client.get(f"{PROJECTS}/{pid}/skills", headers=auth)
    assert listed.status_code == 200, listed.text
    assert set(listed.json()) == {"effective", "stale"}

    replaced = await client.put(f"{PROJECTS}/{pid}/skills", headers=auth, json={"skills": []})
    assert replaced.status_code == 200, replaced.text
    assert set(replaced.json()) == set(listed.json()), "PUT echoes the GET shape"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/connectors"),
        ("GET", "/cron"),
        ("GET", "/instruction"),
        ("GET", "/skills"),
    ],
)
async def test_non_member_is_refused_on_every_new_endpoint(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], method: str, path: str
) -> None:
    client, _, ctx = api
    response = await client.request(method, f"{PROJECTS}/{ctx['pid']}{path}", headers=ctx["bob"])
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


# ── F3: knowledge-base rebind over real HTTP (T-INT3, `-k kb`) ───────────────

KNOWLEDGE_NOT_FOUND = "KNOWLEDGE_NOT_FOUND"  # reused existing code (PLAN.md §4.2)
PROJECT_KB_FORBIDDEN = "PROJECT_KB_FORBIDDEN"


def _kb(srv: Any, *, owner_user_id: int, name: str, shared: bool = False) -> str:
    """Insert a knowledge base straight through the repo (the HTTP KB flow needs a
    configured embedding provider, which is not what these tests are about)."""
    return str(
        srv.services.knowledge_repo.create_base(
            owner_user_id=owner_user_id, name=name, shared=shared
        ).id
    )


async def _member(
    client: httpx.AsyncClient, auth: dict[str, str], pid: str, user_id: int, role: str
) -> None:
    response = await client.post(
        f"{PROJECTS}/{pid}/members",
        headers=auth,
        json={"subject_type": "user", "subject_id": str(user_id), "role": role},
    )
    assert response.status_code == 201, response.text


async def test_kb_rebind_three_states_and_idempotency(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    admin_id = (await client.get("/api/users", headers=auth)).json()
    admin_user_id = next(u["id"] for u in admin_id if u["username"] == "admin")
    first = _kb(srv, owner_user_id=admin_user_id, name="First")

    rebound = await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"kb_id": first})
    assert rebound.status_code == 200, rebound.text
    assert rebound.json()["kb_id"] == first

    # idempotent: the same value again is a 200 with the value unchanged
    again = await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"kb_id": first})
    assert again.status_code == 200, again.text
    assert again.json()["kb_id"] == first

    # the key absent: nothing is touched (RF-7)
    untouched = await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"goal": "new goal"})
    assert untouched.status_code == 200, untouched.text
    assert untouched.json()["kb_id"] == first

    # null: unbind (a 200, not an error face)
    unbound = await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"kb_id": None})
    assert unbound.status_code == 200, unbound.text
    assert unbound.json()["kb_id"] is None
    assert (await client.get(f"{PROJECTS}/{pid}", headers=auth)).json()["kb_id"] is None


async def test_kb_rebind_refusal_codes(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """404 for an invisible base; 403 for a visible-but-unwritable one.

    The 403 case needs a caller who is *not* a platform admin — a platform admin
    may write any base, so the KB-level refusal is only observable for a project
    admin whose own platform role is plain ``user``.
    """
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    users = (await client.get("/api/users", headers=auth)).json()
    ids = {u["username"]: u["id"] for u in users}
    carol = await create_user(client, auth, username="carol")
    carol_id = next(
        u["id"]
        for u in (await client.get("/api/users", headers=auth)).json()
        if u["username"] == "carol"
    )
    private = _kb(srv, owner_user_id=carol_id, name="Carol private")

    missing = await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"kb_id": "kb_missing"})
    assert missing.status_code == 404, missing.text
    assert missing.status_code != 500
    assert missing.json()["error"]["code"] == KNOWLEDGE_NOT_FOUND

    # bob: project admin (so MANAGE_CONFIG passes) but a plain platform user
    await _member(client, auth, pid, ids["bob"], "admin")
    forbidden = await client.patch(f"{PROJECTS}/{pid}", headers=ctx["bob"], json={"kb_id": private})
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.status_code != 500
    assert forbidden.json()["error"]["code"] == PROJECT_KB_FORBIDDEN
    assert carol is not None


async def test_kb_rebind_raises_the_whole_request_permission(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """A write-only member may edit plain fields, but a request carrying ``kb_id``
    is checked at the config level as a whole — no smuggling."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    bob_auth = ctx["bob"]
    bob_id = next(
        u["id"]
        for u in (await client.get("/api/users", headers=auth)).json()
        if u["username"] == "bob"
    )
    await _member(client, auth, pid, bob_id, "member")
    admin_user_id = next(
        u["id"]
        for u in (await client.get("/api/users", headers=auth)).json()
        if u["username"] == "admin"
    )
    kb_id = _kb(srv, owner_user_id=admin_user_id, name="Shared")

    plain = await client.patch(f"{PROJECTS}/{pid}", headers=bob_auth, json={"goal": "member goal"})
    assert plain.status_code == 200, plain.text

    smuggled = await client.patch(
        f"{PROJECTS}/{pid}", headers=bob_auth, json={"goal": "smuggled", "kb_id": kb_id}
    )
    assert smuggled.status_code == 403, smuggled.text
    assert smuggled.status_code != 500
    assert smuggled.json()["error"]["code"] == "PROJECT_ROLE_FORBIDDEN"
    assert (await client.get(f"{PROJECTS}/{pid}", headers=auth)).json()["goal"] == "member goal"


async def test_kb_rebind_on_an_archived_project_is_forbidden(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    admin_user_id = next(
        u["id"]
        for u in (await client.get("/api/users", headers=auth)).json()
        if u["username"] == "admin"
    )
    kb_id = _kb(srv, owner_user_id=admin_user_id, name="Late")
    await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"status": "archived"})

    response = await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"kb_id": kb_id})
    assert response.status_code == 403, response.text
    assert response.status_code != 500
    assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


# ── F4: task editing over real HTTP (T-INT3, `-k task_edit`) ────────────────


async def _new_task(
    client: httpx.AsyncClient, auth: dict[str, str], pid: str, **fields: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{PROJECTS}/{pid}/tasks", headers=auth, json={"title": "T", **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _board_task(
    client: httpx.AsyncClient, auth: dict[str, str], pid: str, task_id: str
) -> dict[str, Any]:
    rows = (await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)).json()
    return next(row for row in rows if row["task_id"] == task_id)


async def test_task_edit_fields_round_trip(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    task = await _new_task(client, auth, pid, description="old", priority=1, deps=["dep-a"])

    patched = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task['task_id']}",
        headers=auth,
        json={
            "title": "Renamed",
            "description": "new",
            "priority": 5,
            "start_at": 1_700_000_000,
            "due_at": 1_700_003_600,
            "status": "todo",
        },
    )
    assert patched.status_code == 200, patched.text
    row = await _board_task(client, auth, pid, task["task_id"])
    assert (row["title"], row["description"], row["priority"]) == ("Renamed", "new", 5)
    assert (row["start_at"], row["due_at"]) == (1_700_000_000, 1_700_003_600)
    assert row["status"] == "todo"


async def test_task_edit_illegal_status_is_409(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    task = await _new_task(client, auth, pid)  # planning

    response = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task['task_id']}", headers=auth, json={"status": "done"}
    )
    assert response.status_code == 409, response.text
    assert response.status_code != 500
    assert response.json()["error"]["code"] == "PROJECT_TASK_STATUS_INVALID"
    assert (await _board_task(client, auth, pid, task["task_id"]))["status"] == "planning"


async def test_task_edit_parent_four_way_split(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """Self / missing / cross-project stay 404; only the indirect cycle is 400."""
    client, _, ctx = api
    auth = ctx["admin"]
    pid = ctx["pid"]
    other = (await client.post(f"{PROJECTS}", headers=auth, json={"name": "Borealis"})).json()[
        "project_id"
    ]

    task_a = await _new_task(client, auth, pid, title="A")
    task_b = await _new_task(client, auth, pid, title="B")
    foreign = await _new_task(client, auth, other, title="Foreign")

    cases = [
        (task_a["task_id"], task_a["task_id"], 404, "PROJECT_TASK_NOT_FOUND"),
        (task_a["task_id"], "tsk_missing", 404, "PROJECT_TASK_NOT_FOUND"),
        (task_a["task_id"], foreign["task_id"], 404, "PROJECT_TASK_NOT_FOUND"),
    ]
    for target, parent, expected_status, expected_code in cases:
        response = await client.patch(
            f"{PROJECTS}/{pid}/tasks/{target}", headers=auth, json={"parent_id": parent}
        )
        assert response.status_code == expected_status, response.text
        assert response.status_code != 500
        assert response.json()["error"]["code"] == expected_code

    # A → B is legal, then B → A closes the loop and must be refused as an indirect cycle
    legal = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task_a['task_id']}",
        headers=auth,
        json={"parent_id": task_b["task_id"]},
    )
    assert legal.status_code == 200, legal.text
    cycle = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task_b['task_id']}",
        headers=auth,
        json={"parent_id": task_a["task_id"]},
    )
    assert cycle.status_code == 400, cycle.text
    assert cycle.status_code != 500
    assert cycle.json()["error"]["code"] == "PROJECT_TASK_PARENT_INVALID"


async def test_task_edit_full_replacement_and_deps_are_never_cleared(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """``tags`` / ``custom_fields`` are whole-set writes; ``deps`` only changes when
    the key is actually sent (the UI has no deps control this round)."""
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    tag = (
        await client.post(f"{PROJECTS}/{pid}/tags", headers=auth, json={"name": "urgent"})
    ).json()["tag_id"]
    field = (
        await client.post(
            f"{PROJECTS}/{pid}/custom-fields",
            headers=auth,
            json={"key": "risk", "label": "Risk", "type": "text"},
        )
    ).json()["field_id"]
    task = await _new_task(client, auth, pid, deps=["dep-a"])
    tid = task["task_id"]

    filled = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{tid}",
        headers=auth,
        json={"tags": [tag], "custom_fields": {field: "high"}},
    )
    assert filled.status_code == 200, filled.text
    row = await _board_task(client, auth, pid, tid)
    assert [t["tag_id"] for t in row["tags"]] == [tag]
    assert row["custom_fields"][0]["value"] == "high"
    assert row["deps"] == ["dep-a"], "deps must survive a patch that omits the key"

    # A patch without the keys changes none of the three collections.
    plain = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{tid}", headers=auth, json={"title": "Only the title"}
    )
    assert plain.status_code == 200, plain.text
    row = await _board_task(client, auth, pid, tid)
    assert [t["tag_id"] for t in row["tags"]] == [tag]
    assert row["custom_fields"][0]["value"] == "high"
    assert row["deps"] == ["dep-a"]

    # Explicit empty values clear them (full replacement, not a merge).
    cleared = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{tid}",
        headers=auth,
        json={"tags": [], "custom_fields": {}, "deps": []},
    )
    assert cleared.status_code == 200, cleared.text
    row = await _board_task(client, auth, pid, tid)
    assert row["tags"] == []
    assert row["custom_fields"] == []
    assert row["deps"] == []


# ── batch 4 (T-INT4): G4 diff-submit over HTTP + the G3 HTTP-reachable face ──
#
# G3's *send* travels over the dashboard WS (`buildDashboardChatWsUrl`), not HTTP,
# and PLAN.md §3.5 registers the project-side authorisation as **not implemented**
# this round — the boundary is the WS ``assert_agent_access``. What HTTP can prove
# is covered here: the refusal codes around the project/task surface and the
# zero-agent non-error face the UI keys its disabled state off.


async def test_task_edit_submits_only_changed_fields_and_rereads(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """A one-field patch must not disturb the rest of the row (diff submission)."""
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    task = await _new_task(
        client,
        auth,
        pid,
        title="Untouched",
        description="keep me",
        priority=2,
        deps=["dep-a"],
        start_at=1_700_000_000,
    )

    single = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task['task_id']}", headers=auth, json={"priority": 4}
    )
    assert single.status_code == 200, single.text

    row = await _board_task(client, auth, pid, task["task_id"])
    assert row["priority"] == 4
    assert row["title"] == "Untouched"
    assert row["description"] == "keep me"
    assert row["deps"] == ["dep-a"]
    assert row["start_at"] == 1_700_000_000
    # The socket for the batch-3 regression: an omitted `deps` key never clears it.
    assert row["deps"] != []


async def test_task_edit_legal_transition_persists_and_illegal_is_409(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """The state machine is the server's: a legal hop persists, an illegal one 409s."""
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    task = await _new_task(client, auth, pid)  # planning

    legal = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task['task_id']}", headers=auth, json={"status": "todo"}
    )
    assert legal.status_code == 200, legal.text
    assert (await _board_task(client, auth, pid, task["task_id"]))["status"] == "todo"

    illegal = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task['task_id']}", headers=auth, json={"status": "done"}
    )
    assert illegal.status_code == 409, illegal.text
    assert illegal.status_code != 500
    assert illegal.json()["error"]["code"] == "PROJECT_TASK_STATUS_INVALID"
    # The refused transition left the stored row untouched (no optimistic write).
    assert (await _board_task(client, auth, pid, task["task_id"]))["status"] == "todo"


async def test_g3_permission_matrix_on_the_http_face(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """viewer → role forbidden; non-member → project forbidden; both ``!= 500``."""
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    bob = ctx["bob"]
    bob_id = next(
        u["id"]
        for u in (await client.get("/api/users", headers=auth)).json()
        if u["username"] == "bob"
    )
    await _member(client, auth, pid, bob_id, "viewer")

    viewer_read = await client.get(f"{PROJECTS}/{pid}/tasks", headers=bob)
    assert viewer_read.status_code == 200, "a viewer may read the board"
    viewer_write = await client.post(
        f"{PROJECTS}/{pid}/tasks", headers=bob, json={"title": "viewer task"}
    )
    assert viewer_write.status_code == 403, viewer_write.text
    assert viewer_write.status_code != 500
    assert viewer_write.json()["error"]["code"] == "PROJECT_ROLE_FORBIDDEN"

    outsider = await create_user(client, auth, username="dave")
    non_member = await client.get(f"{PROJECTS}/{pid}/tasks", headers=outsider)
    assert non_member.status_code == 403, non_member.text
    assert non_member.status_code != 500
    assert non_member.json()["error"]["code"] == "PROJECT_FORBIDDEN"


async def test_archived_project_refuses_writes_but_still_reads(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    task = await _new_task(client, auth, pid)
    await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"status": "archived"})

    write = await client.post(f"{PROJECTS}/{pid}/tasks", headers=auth, json={"title": "late"})
    assert write.status_code == 403, write.text
    assert write.status_code != 500
    assert write.json()["error"]["code"] == "PROJECT_FORBIDDEN"
    read = await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)
    assert read.status_code == 200, "archived is read-only, not invisible"
    assert [row["task_id"] for row in read.json()] == [task["task_id"]]


async def test_zero_agent_project_is_not_an_error_face(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """The G3 disabled state is derived from member data — that read must be clean."""
    client, _, ctx = api
    auth = ctx["admin"]
    pid = (await client.post(PROJECTS, headers=auth, json={"name": "No agents"})).json()[
        "project_id"
    ]

    members = await client.get(f"{PROJECTS}/{pid}/members", headers=auth)
    assert members.status_code == 200, members.text
    assert [m for m in members.json() if m["subject_type"] == "agent"] == []
    board = await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)
    assert board.status_code == 200, board.text
    assert board.json() == []


# ── batch 6 (T-P6-INT): the display-name contract over real HTTP ─────────────
#
# Evidence layer: **proxy** — these run the real app, real router, real SQLite and
# real HTTP, so they prove the API shape and the join. They do NOT prove what the
# browser renders (that is the frontend's component layer).


async def _user_id(client: httpx.AsyncClient, auth: dict[str, str], username: str) -> int:
    rows = (await client.get("/api/users", headers=auth)).json()
    return next(row["id"] for row in rows if row["username"] == username)


async def test_member_rows_expose_name_for_every_subject_type(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """agent → agents.name · user → display_name/username · team → same agents row."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    bob_id = await _user_id(client, auth, "bob")
    srv.services.agent_repo.create(
        agent_id="EXPT01", user_id=1, name="AI 编程实战导师", kind="expert"
    )
    srv.services.agent_repo.create(agent_id="TEAM01", user_id=1, name="测试团队 T1", kind="team")
    for subject_type, subject_id in (
        ("user", str(bob_id)),
        ("agent", "EXPT01"),
        ("team", "TEAM01"),
        ("team", "team_ghost"),  # not an agents row → None, never an error
    ):
        created = await client.post(
            f"{PROJECTS}/{pid}/members",
            headers=auth,
            json={"subject_type": subject_type, "subject_id": subject_id, "role": "member"},
        )
        assert created.status_code == 201, created.text

    listed = await client.get(f"{PROJECTS}/{pid}/members", headers=auth)
    assert listed.status_code == 200, listed.text
    names = {row["subject_id"]: row["name"] for row in listed.json()}
    assert names[str(bob_id)] == "bob", "user → username when display_name is empty"
    assert names["1"] == "admin", "the owner row resolves too"
    assert names["EXPT01"] == "AI 编程实战导师"
    assert names["TEAM01"] == "测试团队 T1", "a team is an agents row with kind='team'"
    assert names["team_ghost"] is None, "unresolvable → null, and the call still 200s"


async def test_member_response_shape_is_additive(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """The five pre-existing fields keep their names and order; ``name`` is new."""
    client, _, ctx = api
    listed = await client.get(f"{PROJECTS}/{ctx['pid']}/members", headers=ctx["admin"])
    assert listed.status_code == 200, listed.text
    row = listed.json()[0]
    assert list(row)[:5] == ["subject_type", "subject_id", "user_id", "role", "created_at"]
    assert "name" in row
    assert row["name"] is None or isinstance(row["name"], str)
    assert isinstance(row["subject_id"], str) and isinstance(row["role"], str)


async def test_picker_sources_are_reachable(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """The picker's two sources answer on the real app (agent/team selection)."""
    client, srv, ctx = api
    auth = ctx["admin"]
    srv.services.agent_repo.create(agent_id="EXPT02", user_id=1, name="导师二号", kind="expert")
    srv.services.agent_repo.create(agent_id="TEAM02", user_id=1, name="团队二号", kind="team")

    agents = await client.get("/api/agents", headers=auth)
    assert agents.status_code == 200, agents.text
    team_rows = [row for row in agents.json() if row.get("kind") == "team"]
    assert any(row.get("name") == "导师二号" for row in agents.json()), "experts are listed"
    assert any(row.get("name") == "团队二号" for row in team_rows), "teams are listed too"

    teams = await client.get("/api/teams", headers=auth)
    assert teams.status_code == 200, teams.text
    assert isinstance(teams.json(), (list, dict)), teams.text


async def test_member_add_refusals_are_403_not_500(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """viewer / non-member / archived project: 403 + a code, never 500."""
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    bob_id = await _user_id(client, auth, "bob")
    await client.post(
        f"{PROJECTS}/{pid}/members",
        headers=auth,
        json={"subject_type": "user", "subject_id": str(bob_id), "role": "viewer"},
    )
    payload = {"subject_type": "user", "subject_id": "2", "role": "member"}

    as_viewer = await client.post(f"{PROJECTS}/{pid}/members", headers=ctx["bob"], json=payload)
    assert as_viewer.status_code == 403, as_viewer.text
    assert as_viewer.status_code != 500
    assert as_viewer.json()["error"]["code"] == "PROJECT_ROLE_FORBIDDEN"

    outsider = await create_user(client, auth, username="erin")
    as_outsider = await client.post(f"{PROJECTS}/{pid}/members", headers=outsider, json=payload)
    assert as_outsider.status_code == 403, as_outsider.text
    assert as_outsider.status_code != 500
    assert as_outsider.json()["error"]["code"] == "PROJECT_FORBIDDEN"

    await client.patch(f"{PROJECTS}/{pid}", headers=auth, json={"status": "archived"})
    archived = await client.post(f"{PROJECTS}/{pid}/members", headers=auth, json=payload)
    assert archived.status_code == 403, archived.text
    assert archived.status_code != 500
    assert archived.json()["error"]["code"] == "PROJECT_FORBIDDEN"
