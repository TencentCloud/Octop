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

from octop.infra.projects.attachments import ProjectAttachmentService

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


# ── batch 9 (T-19-INT): Z1 + Y10 + the audit trail over real HTTP ────────────


async def test_z1_blank_project_name_is_a_422_not_a_500(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """Same structure as the route-guards case, on the in-process real app."""
    client, _, ctx = api
    auth = ctx["admin"]

    empty = await client.post(PROJECTS, headers=auth, json={"name": ""})
    assert empty.status_code == 422, empty.text
    detail = empty.json()["detail"][0]
    assert detail["loc"] == ["body", "name"] and detail["type"] == "string_too_short"

    blank = await client.post(PROJECTS, headers=auth, json={"name": "   "})
    assert blank.status_code == 422, blank.text
    detail = blank.json()["detail"][0]
    assert detail["loc"] == ["body", "name"] and detail["type"] == "value_error"

    ok = await client.post(PROJECTS, headers=auth, json={"name": "ok", "status": "active"})
    assert ok.status_code == 201, ok.text


async def test_y10_round_trip_and_the_audit_trail(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """Adopt → the three fields come back; un-adopt → they clear; audit keeps both."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    created = await client.post(
        f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "adopt me"}
    )
    assert created.status_code == 201, created.text
    cid = created.json()["comment_id"]

    adopted = await client.post(f"{PROJECTS}/{pid}/comments/{cid}/conclude", headers=auth)
    assert adopted.status_code == 200, adopted.text
    body = adopted.json()
    assert body["concluded"] is True
    assert body["concluded_by_type"] == "user"
    assert body["concluded_by_id"] == "1"
    assert body["concluded_by_name"], "the adopting actor's display name must resolve"

    only = await client.get(
        f"{PROJECTS}/{pid}/comments", headers=auth, params={"concluded": "true"}
    )
    assert [row["comment_id"] for row in only.json()] == [cid]
    rest = await client.get(
        f"{PROJECTS}/{pid}/comments", headers=auth, params={"concluded": "false"}
    )
    assert all(row["comment_id"] != cid for row in rest.json())

    cleared = await client.delete(f"{PROJECTS}/{pid}/comments/{cid}/conclude", headers=auth)
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["concluded"] is False
    assert body["concluded_by_type"] is None and body["concluded_by_id"] is None
    assert body["concluded_by_name"] is None

    with srv.services.db.connect() as conn:
        actions = [
            str(row["action"])
            for row in conn.execute(
                "SELECT action FROM audit_log WHERE target = ? ORDER BY ts, id", (cid,)
            ).fetchall()
        ]
    assert actions == ["project.comment.conclude", "project.comment.unconclude"]


async def test_a_failing_audit_write_makes_the_request_fail_and_the_state_stand(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP-layer evidence for PLAN.md §2.1c P6 (state and audit share a transaction).

    The probe patches ``audit_repo.write`` on the live service object — the request
    then travels the real ASGI path. Either the app answers non-2xx, or the
    unhandled error propagates out of the ASGI transport: both mean "not 2xx".
    """
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    created = await client.post(
        f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "roll back"}
    )
    cid = created.json()["comment_id"]

    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(srv.services.audit_repo, "write", _boom)
    failed = False
    try:
        response = await client.post(f"{PROJECTS}/{pid}/comments/{cid}/conclude", headers=auth)
        assert response.status_code >= 400, response.text
        failed = True
    except Exception:  # the ASGI transport re-raises an unhandled error
        failed = True
    finally:
        monkeypatch.undo()
    assert failed, "a failed audit write must not answer 2xx"

    listed = await client.get(f"{PROJECTS}/{pid}/comments", headers=auth)
    row = next(item for item in listed.json() if item["comment_id"] == cid)
    assert row["concluded"] is False
    assert row["concluded_by_type"] is None and row["concluded_by_id"] is None


# ── batch 11 (T-C2-API): comment edit / delete over real HTTP ────────────────


async def test_editing_and_deleting_a_comment_over_http(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """PATCH replaces the text (old text -> audit); DELETE removes row + attachments."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    created = await client.post(f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "v1"})
    assert created.status_code == 201, created.text
    cid = created.json()["comment_id"]

    patched = await client.patch(
        f"{PROJECTS}/{pid}/comments/{cid}", headers=auth, json={"body": "v2"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["body"] == "v2"
    assert patched.json()["created_at"] == created.json()["created_at"]

    with srv.services.db.connect() as conn:
        payload = conn.execute(
            "SELECT payload FROM audit_log WHERE target = ? AND action = 'project.comment.edit'",
            (cid,),
        ).fetchone()["payload"]
    assert '"old_body": "v1"' in payload, payload

    blank = await client.patch(
        f"{PROJECTS}/{pid}/comments/{cid}", headers=auth, json={"body": "  "}
    )
    assert blank.status_code == 422, blank.text

    # An attachment bound to the comment disappears with it (rows only).
    srv.services.project_artifact_repo.insert(
        artifact_id="ARTX",
        project_id=pid,
        task_id=None,
        name="a.txt",
        size=1,
        mime="text/plain",
        uri="local://a.txt",
        file_hash="h",
        created_by=1,
    )
    assert srv.services.project_artifact_repo.bind_comment("ARTX", comment_id=cid) is True

    deleted = await client.delete(f"{PROJECTS}/{pid}/comments/{cid}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert srv.services.project_artifact_repo.get("ARTX") is None, "attachment row must go"
    listed = await client.get(f"{PROJECTS}/{pid}/comments", headers=auth)
    assert all(row["comment_id"] != cid for row in listed.json())


async def test_the_concluded_comment_cannot_be_deleted_over_http(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """F-3 four items: 409 + verbatim code + the frozen zh guidance + state unchanged."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    created = await client.post(f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "keeper"})
    cid = created.json()["comment_id"]
    assert (
        await client.post(f"{PROJECTS}/{pid}/comments/{cid}/conclude", headers=auth)
    ).status_code == 200

    refused = await client.delete(f"{PROJECTS}/{pid}/comments/{cid}", headers=auth)
    assert refused.status_code == 409, refused.text
    assert refused.status_code != 500
    body = refused.json()["error"]
    assert body["code"] == "PROJECT_COMMENT_CONCLUDED"
    assert "先取消采纳" in body["message"], body["message"]

    # The row is still there and still the conclusion.
    listed = await client.get(f"{PROJECTS}/{pid}/comments", headers=auth)
    row = next(r for r in listed.json() if r["comment_id"] == cid)
    assert row["concluded"] is True and row["node_type"] == "conclusion"
    with srv.services.db.connect() as conn:
        still = conn.execute(
            "SELECT node_type FROM project_comments WHERE comment_id = ?", (cid,)
        ).fetchone()
    assert still["node_type"] == "conclusion"


async def test_a_non_member_cannot_edit_or_delete_comments(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    created = await client.post(f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "mine"})
    cid = created.json()["comment_id"]

    edited = await client.patch(
        f"{PROJECTS}/{pid}/comments/{cid}", headers=ctx["bob"], json={"body": "hijack"}
    )
    assert edited.status_code == 403, edited.text
    assert edited.status_code != 500
    assert edited.json()["error"]["code"] == "PROJECT_FORBIDDEN"

    removed = await client.request("DELETE", f"{PROJECTS}/{pid}/comments/{cid}", headers=ctx["bob"])
    assert removed.status_code == 403, removed.text
    assert removed.status_code != 500
    assert removed.json()["error"]["code"] == "PROJECT_FORBIDDEN"


# ── batch 11 (T-C2-API): binding attachments to a comment over real HTTP ─────


def _stage(srv: Any, pid: str, artifact_id: str, uri: str = "local://a.txt") -> None:
    srv.services.project_artifact_repo.insert(
        artifact_id=artifact_id,
        project_id=pid,
        task_id=None,
        name="a.txt",
        size=1,
        mime="text/plain",
        uri=uri,
        file_hash="h",
        created_by=1,
    )


async def test_binding_an_attachment_to_a_comment_over_http(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """bind takes comment_id, persists it, and the four error paths stay put."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    cid = (
        await client.post(f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "own it"})
    ).json()["comment_id"]
    _stage(srv, pid, "ARTA")

    bound = await client.patch(
        f"{PROJECTS}/{pid}/attachments/ARTA", headers=auth, json={"comment_id": cid}
    )
    assert bound.status_code == 200, bound.text
    with srv.services.db.connect() as conn:
        stored = conn.execute(
            "SELECT comment_id FROM project_artifacts WHERE artifact_id = ?", ("ARTA",)
        ).fetchone()["comment_id"]
    assert stored == cid, "the comment binding must be persisted"
    assert [
        a.artifact_id
        for a in srv.services.project_artifact_repo.list_by_comment(project_id=pid, comment_id=cid)
    ] == ["ARTA"]

    # already bound ⇒ 409 (same shape as the task face)
    again = await client.patch(
        f"{PROJECTS}/{pid}/attachments/ARTA", headers=auth, json={"comment_id": cid}
    )
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"
    assert again.status_code != 500

    # exactly one of task_id / comment_id
    _stage(srv, pid, "ARTB")
    for payload in ({"task_id": "tsk_x", "comment_id": cid}, {}):
        bad = await client.patch(f"{PROJECTS}/{pid}/attachments/ARTB", headers=auth, json=payload)
        assert bad.status_code == 400, (payload, bad.text)
        assert bad.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"
        assert bad.status_code != 500


async def test_deleting_a_comment_keeps_the_blob_file_on_disk(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """⑤ direct evidence for "blobs are kept" (debt O6): row gone, file still there."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    cid = (
        await client.post(f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": "has file"})
    ).json()["comment_id"]
    _stage(srv, pid, "ARTC", uri="local://keepme.bin")
    assert srv.services.project_artifact_repo.bind_comment("ARTC", comment_id=cid) is True

    service = ProjectAttachmentService(srv.services)
    path = service._absolute_path(pid, "local://keepme.bin")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"payload")
    assert path.exists()

    deleted = await client.delete(f"{PROJECTS}/{pid}/comments/{cid}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert srv.services.project_artifact_repo.get("ARTC") is None, "the row must go"
    assert path.exists(), "the blob file must survive (batch keeps blobs: debt O6)"
    path.unlink(missing_ok=True)


async def test_a_non_member_platform_admin_can_delete_another_users_comment(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """SPEC P1 end to end: governance is **parallel** to project membership.

    The admin here is not a member of bob's project, so a role-based check alone
    would answer 403 — only the governance gate lets this through. (Its mirror,
    "a plain member may not touch someone else's comment", is asserted at the
    service level in ``tests/unit/projects/test_project_discussion.py``.)
    """
    client, _, ctx = api
    pid = (
        await client.post(
            PROJECTS, headers=ctx["bob"], json={"name": "bob's project", "status": "active"}
        )
    ).json()["project_id"]
    cid = (
        await client.post(
            f"{PROJECTS}/{pid}/comments", headers=ctx["bob"], json={"body": "bob wrote"}
        )
    ).json()["comment_id"]

    # sanity: the admin is genuinely not a member of this project
    members = await client.get(f"{PROJECTS}/{pid}/members", headers=ctx["bob"])
    assert all(m["subject_id"] != "1" for m in members.json()), members.text

    removed = await client.request(
        "DELETE", f"{PROJECTS}/{pid}/comments/{cid}", headers=ctx["admin"]
    )
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"deleted": True}
    listed = await client.get(f"{PROJECTS}/{pid}/comments", headers=ctx["bob"])
    assert all(row["comment_id"] != cid for row in listed.json())


# ── batch 12 (T-F-API): the relevance filter on the comments feed ────────────


async def test_relevance_me_narrows_the_feed_to_the_caller(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """`?relevance=me` = mentioned **or** on a task assigned to me; subset of the feed."""
    client, srv, ctx = api
    auth, pid = ctx["admin"], ctx["pid"]
    bob_id = next(
        u["id"]
        for u in (await client.get("/api/users", headers=auth)).json()
        if u["username"] == "bob"
    )
    await _member(client, auth, pid, bob_id, "member")

    # End to end over HTTP: the dashboard submits the mention, the server stores it
    # verbatim, and `relevance=me` finds the row it stored.
    mention = await client.post(
        f"{PROJECTS}/{pid}/comments",
        headers=ctx["bob"],
        json={"body": "hey @admin", "mentions": [{"type": "user", "id": "1"}]},
    )
    assert mention.status_code == 201, mention.text
    plain = await client.post(
        f"{PROJECTS}/{pid}/comments", headers=ctx["bob"], json={"body": "unrelated"}
    )
    assert plain.status_code == 201, plain.text

    feed = await client.get(f"{PROJECTS}/{pid}/comments", headers=auth)
    assert len(feed.json()) >= 2, "precondition: the unfiltered feed is not empty"
    mine = await client.get(f"{PROJECTS}/{pid}/comments", headers=auth, params={"relevance": "me"})
    assert mine.status_code == 200, mine.text
    ids = {row["comment_id"] for row in mine.json()}
    assert ids == {mention.json()["comment_id"]}, ids
    assert ids <= {row["comment_id"] for row in feed.json()}, "must stay a subset"

    # an unknown value is refused, never silently ignored
    bad = await client.get(f"{PROJECTS}/{pid}/comments", headers=auth, params={"relevance": "them"})
    assert bad.status_code == 422, bad.text
