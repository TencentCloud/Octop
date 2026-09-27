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
    client: httpx.AsyncClient, auth: dict[str, str], project_id: str, title: str
) -> str:
    r = await client.post(f"{PROJECTS}/{project_id}/tasks", headers=auth, json={"title": title})
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
    tid_a = await _create_task(client, alice, pid_a, "Draft the flight plan")

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
