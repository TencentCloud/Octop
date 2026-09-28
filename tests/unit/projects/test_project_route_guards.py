"""HTTP regressions for the task routes: the path's project is authoritative.

Both bugs were reported against the wire, so these tests boot a real
``OctopServer`` and drive ``/api/projects`` the way the dashboard does:

* ``PATCH`` / ``DELETE`` ``/projects/{B}/tasks/{task-of-A}`` used to answer 200 and
  mutate A's task, because the task routes resolved the task's *own* project and
  never validated the ``{project_id}`` segment (``:dispatch`` was the only route
  that guarded it).
* ``status`` / ``role`` values outside the known vocabularies escaped as an
  unhandled ``ValueError`` — HTTP 500 instead of the project error codes.
* a ``parent_id`` that cannot be used (missing, or belonging to another project)
  escaped the same way; it is now the ``PROJECT_TASK_NOT_FOUND`` 404 envelope.

Every refusal asserts the error **code** from the standard envelope, not just the
status: a 404 carrying ``PROJECT_NOT_FOUND`` (the project in the path) would mean
the path guard never fired.
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


def _error_code(response: httpx.Response) -> str:
    """Code from the standard ``{"error": {"code": ...}}`` envelope."""
    return str(response.json()["error"]["code"])


async def _create_project(client: httpx.AsyncClient, auth: dict[str, str], name: str) -> str:
    r = await client.post(PROJECTS, headers=auth, json={"name": name})
    assert r.status_code == 201, r.text
    return str(r.json()["project_id"])


async def _create_task(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    project_id: str,
    title: str,
    **fields: Any,
) -> str:
    r = await client.post(
        f"{PROJECTS}/{project_id}/tasks", headers=auth, json={"title": title, **fields}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["task_id"])


async def _board(
    client: httpx.AsyncClient, auth: dict[str, str], project_id: str
) -> list[dict[str, Any]]:
    r = await client.get(f"{PROJECTS}/{project_id}/tasks", headers=auth)
    assert r.status_code == 200, r.text
    return list(r.json())


@pytest.fixture
async def api(
    tmp_octop_home: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, dict[str, str]]]]:
    """Client plus two regular users — the cross-project owner/member split."""
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        yield (
            client,
            {
                "alice": await create_user(client, admin, username="alice"),
                "bob": await create_user(client, admin, username="bob"),
            },
        )


# ── bug 1: a task cannot be reached through another project's path ───────────


async def test_patch_and_delete_through_another_projects_path_are_not_found(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    client, users = api
    alice, bob = users["alice"], users["bob"]
    pid_a = await _create_project(client, alice, "Apollo")
    pid_b = await _create_project(client, bob, "Borealis")
    tid_a = await _create_task(client, alice, pid_a, "Draft the flight plan")

    patched = await client.patch(
        f"{PROJECTS}/{pid_b}/tasks/{tid_a}",
        headers=alice,
        json={"title": "hijacked through B"},
    )
    assert patched.status_code == 404, patched.text
    assert _error_code(patched) == "PROJECT_TASK_NOT_FOUND", patched.text

    deleted = await client.delete(f"{PROJECTS}/{pid_b}/tasks/{tid_a}", headers=alice)
    assert deleted.status_code == 404, deleted.text
    assert _error_code(deleted) == "PROJECT_TASK_NOT_FOUND", deleted.text

    # Both refusals left A's task exactly where it was — present and unrenamed.
    board = await _board(client, alice, pid_a)
    assert [t["task_id"] for t in board] == [tid_a]
    assert board[0]["title"] == "Draft the flight plan"


async def test_the_owning_projects_path_still_patches_and_deletes(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    client, users = api
    alice = users["alice"]
    pid_a = await _create_project(client, alice, "Apollo")
    # Created straight into ``todo`` so the patch below can exercise ``todo -> doing``
    # (a default-planned task must pass through ``todo`` first, PLAN.md §1.2).
    tid_a = await _create_task(client, alice, pid_a, "Draft the flight plan", status="todo")

    renamed = await client.patch(
        f"{PROJECTS}/{pid_a}/tasks/{tid_a}", headers=alice, json={"title": "Renamed"}
    )
    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["project_id"], renamed.json()["title"]) == (pid_a, "Renamed")

    moved = await client.patch(
        f"{PROJECTS}/{pid_a}/tasks/{tid_a}", headers=alice, json={"status": "doing"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "doing"

    deleted = await client.delete(f"{PROJECTS}/{pid_a}/tasks/{tid_a}", headers=alice)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert await _board(client, alice, pid_a) == []


# ── bug 2: an unknown enum value is a 4xx with its project error code ────────


async def test_bogus_project_status_is_a_client_error(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    client, users = api
    alice = users["alice"]
    pid_a = await _create_project(client, alice, "Apollo")

    response = await client.patch(f"{PROJECTS}/{pid_a}", headers=alice, json={"status": "bogus"})
    assert response.status_code == 409, response.text
    assert _error_code(response) == "PROJECT_STATUS_INVALID", response.text


async def test_bogus_task_status_is_a_client_error(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    client, users = api
    alice = users["alice"]
    pid_a = await _create_project(client, alice, "Apollo")
    tid_a = await _create_task(client, alice, pid_a, "Draft the flight plan")

    response = await client.patch(
        f"{PROJECTS}/{pid_a}/tasks/{tid_a}", headers=alice, json={"status": "bogus"}
    )
    assert response.status_code == 409, response.text
    assert _error_code(response) == "PROJECT_TASK_STATUS_INVALID", response.text


async def test_bogus_member_role_is_a_client_error(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    client, users = api
    alice = users["alice"]
    pid_a = await _create_project(client, alice, "Apollo")

    response = await client.post(
        f"{PROJECTS}/{pid_a}/members",
        headers=alice,
        json={"subject_type": "agent", "subject_id": "agent-1", "role": "bogus"},
    )
    assert response.status_code == 400, response.text
    assert _error_code(response) == "PROJECT_MEMBER_INVALID", response.text


# ── bug 3: a bad parent_id is a 404 envelope, never an unhandled 500 ─────────


async def test_unusable_parent_id_is_a_404_not_a_500(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    """``parent_id`` pointing outside the project (or nowhere) used to escape as an
    unhandled ``ValueError`` → 500. Both cases share ``PROJECT_TASK_NOT_FOUND``
    (the message is not asserted: PLAN.md §7 freezes the code, not the text)."""
    client, users = api
    alice = users["alice"]
    pid_a = await _create_project(client, alice, "Apollo")
    pid_b = await _create_project(client, alice, "Borealis")
    parent_in_b = await _create_task(client, alice, pid_b, "Parent in B")

    for parent_id in (parent_in_b, "tsk_does_not_exist"):
        response = await client.post(
            f"{PROJECTS}/{pid_a}/tasks",
            headers=alice,
            json={"title": "child", "parent_id": parent_id},
        )
        assert response.status_code == 404, response.text
        assert response.status_code != 500, response.text
        assert _error_code(response) == "PROJECT_TASK_NOT_FOUND", response.text

    # Nothing was created by the refused requests.
    assert await _board(client, alice, pid_a) == []


# ── a creation-time status is applied, never silently dropped (SPEC S-10) ────


async def test_project_status_on_create_is_applied_and_validated(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    """``ProjectCreate.status`` must reach the row (all six states selectable) and
    an unknown value must be a 409 envelope — never a silent default."""
    client, users = api
    alice = users["alice"]

    created = await client.post(
        f"{PROJECTS}", headers=alice, json={"name": "Apollo", "status": "active"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "active", "status was silently dropped"

    bogus = await client.post(
        f"{PROJECTS}", headers=alice, json={"name": "Borealis", "status": "bogus"}
    )
    assert bogus.status_code == 409, bogus.text
    assert bogus.status_code != 500, bogus.text
    assert _error_code(bogus) == "PROJECT_STATUS_INVALID", bogus.text

    listed = await client.get(f"{PROJECTS}", headers=alice)
    names = [p["name"] for p in listed.json()]
    assert names == ["Apollo"], "the rejected project must not exist"


# ── batch 8 (T-B8-API): comments over the wire ───────────────────────────────


async def _project(client: httpx.AsyncClient, auth: dict[str, str], name: str = "P8") -> str:
    created = await client.post(PROJECTS, headers=auth, json={"name": name, "status": "active"})
    assert created.status_code == 201, created.text
    return str(created.json()["project_id"])


async def test_a_blank_comment_body_is_a_422_like_a_blank_task_title(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """The request layer rejects blank text for both resources, in the same shape.

    ``""`` fails ``min_length``; ``"   "`` fails the field validator. Neither may
    reach the service (where a bare ``ValueError`` would escape as a 500).
    """
    client, ctx = api[0], api[1]
    auth = ctx["admin"] if "admin" in ctx else next(iter(ctx.values()))
    pid = await _project(client, auth)

    for body in ("", "   "):
        comment = await client.post(f"{PROJECTS}/{pid}/comments", headers=auth, json={"body": body})
        assert comment.status_code == 422, (body, comment.text)
        assert comment.status_code != 500
        detail = comment.json()["detail"][0]
        assert detail["loc"] == ["body", "body"]
        if body == "":
            assert detail["type"] == "string_too_short"  # the min_length guard
        else:
            assert detail["type"] == "value_error"  # the blank-text validator
            assert "body" in detail["msg"]

    title = await client.post(f"{PROJECTS}/{pid}/tasks", headers=auth, json={"title": "   "})
    assert title.status_code == 422, title.text
    assert title.json()["detail"][0]["loc"] == ["body", "title"]
    assert "title" in title.json()["detail"][0]["msg"]


async def test_timeline_filters_in_sql_without_changing_the_default(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """No ``task_id`` ⇒ the previous result; with one ⇒ only that task's events.

    The filter is applied in SQL: were it a post-filter, ``limit`` would interact
    with it and drop rows.
    """
    client, ctx = api[0], api[1]
    auth = ctx["admin"] if "admin" in ctx else next(iter(ctx.values()))
    pid = await _project(client, auth, "P8-timeline")
    tasks = []
    for title in ("T1", "T2"):
        created = await client.post(f"{PROJECTS}/{pid}/tasks", headers=auth, json={"title": title})
        assert created.status_code == 201, created.text
        tasks.append(created.json()["task_id"])

    everything = await client.get(f"{PROJECTS}/{pid}/timeline", headers=auth)
    assert everything.status_code == 200, everything.text
    assert len(everything.json()) >= 2

    for task_id in tasks:
        narrowed = await client.get(
            f"{PROJECTS}/{pid}/timeline", headers=auth, params={"task_id": task_id}
        )
        assert narrowed.status_code == 200, narrowed.text
        rows = narrowed.json()
        assert rows, f"task {task_id} has no events"
        assert {row["task_id"] for row in rows} == {task_id}

    limited = await client.get(
        f"{PROJECTS}/{pid}/timeline", headers=auth, params={"limit": 1, "task_id": tasks[0]}
    )
    assert limited.status_code == 200, limited.text
    assert len(limited.json()) == 1


async def test_a_blank_project_name_is_a_422_not_a_500(
    api: tuple[httpx.AsyncClient, dict[str, dict[str, str]]],
) -> None:
    """Same shape as the comment/task blank-text case, for ``ProjectCreate.name``.

    ``""`` fails ``min_length``; ``"   "`` fails the field validator. Without the
    validator the request reaches the service's bare ``ValueError`` (no 4xx
    mapping) and the caller sees a 500-shaped failure — so this is the CI signal
    that the guard still exists. ``"ok"`` is the positive control.
    """
    client, users = api
    auth = next(iter(users.values()))

    empty = await client.post(PROJECTS, headers=auth, json={"name": ""})
    assert empty.status_code == 422, empty.text
    detail = empty.json()["detail"][0]
    assert detail["loc"] == ["body", "name"]
    assert detail["type"] == "string_too_short"

    blank = await client.post(PROJECTS, headers=auth, json={"name": "   "})
    assert blank.status_code == 422, blank.text
    detail = blank.json()["detail"][0]
    assert detail["loc"] == ["body", "name"]
    assert detail["type"] == "value_error"
    assert "name" in detail["msg"]

    ok = await client.post(PROJECTS, headers=auth, json={"name": "ok", "status": "active"})
    assert ok.status_code == 201, ok.text
