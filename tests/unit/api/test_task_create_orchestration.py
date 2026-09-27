"""The create-task orchestration: four steps, reverse-order compensation (§2.3).

Drives the real ``POST /api/projects/{pid}/tasks`` route and then checks the
**rows** (``project_task_tags`` / ``project_task_field_values`` /
``project_artifacts.task_id``) — a request that carries metadata must either apply
all of it or leave no task behind. HTTP read-back endpoints are asserted where
they exist; the SQL counts are the "table has data" evidence.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin

PROJECTS = "/api/projects"


@pytest.fixture
async def api(tmp_octop_home: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, Any]]]:
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        yield client, srv, {"admin": admin}


async def _project(client: httpx.AsyncClient, auth: dict[str, str], name: str) -> str:
    response = await client.post(PROJECTS, headers=auth, json={"name": name, "status": "active"})
    assert response.status_code == 201, response.text
    return str(response.json()["project_id"])


async def _tag(client: httpx.AsyncClient, auth: dict[str, str], pid: str, name: str) -> str:
    response = await client.post(f"{PROJECTS}/{pid}/tags", headers=auth, json={"name": name})
    assert response.status_code == 201, response.text
    return str(response.json()["tag_id"])


async def _field(client: httpx.AsyncClient, auth: dict[str, str], pid: str, key: str) -> str:
    response = await client.post(
        f"{PROJECTS}/{pid}/custom-fields",
        headers=auth,
        json={"key": key, "label": key.title(), "type": "text"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["field_id"])


async def _staged(
    client: httpx.AsyncClient, auth: dict[str, str], pid: str, name: str = "spec.txt"
) -> str:
    response = await client.post(
        f"{PROJECTS}/{pid}/attachments",
        headers=auth,
        files={"file": (name, b"payload", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["artifact_id"])


def _count(srv: Any, sql: str, params: tuple[object, ...]) -> int:
    with srv.services.db.connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row["c"])


def _tasks(srv: Any, pid: str) -> int:
    return _count(srv, "SELECT COUNT(*) AS c FROM project_tasks WHERE project_id = ?", (pid,))


async def test_create_applies_tags_custom_fields_and_attachments(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    tag_id = await _tag(client, auth, pid, "urgent")
    field_id = await _field(client, auth, pid, "risk")
    artifact_id = await _staged(client, auth, pid)

    created = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={
            "title": "Ship it",
            "status": "todo",
            "tags": [tag_id],
            "custom_fields": {field_id: "high"},
            "attachment_ids": [artifact_id],
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["task_id"]

    # Rows, not just a 201: every step left real data behind.
    assert (
        _count(srv, "SELECT COUNT(*) AS c FROM project_task_tags WHERE task_id = ?", (task_id,))
        == 1
    )
    assert (
        _count(
            srv,
            "SELECT COUNT(*) AS c FROM project_task_field_values WHERE task_id = ? AND value = ?",
            (task_id, "high"),
        )
        == 1
    )
    assert (
        _count(
            srv,
            "SELECT COUNT(*) AS c FROM project_artifacts WHERE artifact_id = ? AND task_id = ?",
            (artifact_id, task_id),
        )
        == 1
    )

    # And the HTTP read-back rings agree.
    values = await client.get(f"{PROJECTS}/{pid}/tasks/{task_id}/custom-fields", headers=auth)
    assert values.status_code == 200, values.text
    assert values.json()["values"] == {field_id: "high"}

    listed = await client.get(f"{PROJECTS}/{pid}/tasks/{task_id}/attachments", headers=auth)
    assert listed.status_code == 200, listed.text
    assert [a["artifact_id"] for a in listed.json()] == [artifact_id]
    assert listed.json()[0]["task_id"] == task_id


async def test_patch_applies_tags_and_custom_fields_too(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """The same silent-drop must not exist on the edit path (PLAN.md §2.1)."""
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    tag_id = await _tag(client, auth, pid, "urgent")
    field_id = await _field(client, auth, pid, "risk")
    created = await client.post(f"{PROJECTS}/{pid}/tasks", headers=auth, json={"title": "T"})
    task_id = created.json()["task_id"]

    patched = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task_id}",
        headers=auth,
        json={"title": "Renamed", "tags": [tag_id], "custom_fields": {field_id: "low"}},
    )
    assert patched.status_code == 200, patched.text
    assert (
        _count(srv, "SELECT COUNT(*) AS c FROM project_task_tags WHERE task_id = ?", (task_id,))
        == 1
    )
    assert (
        _count(
            srv,
            "SELECT COUNT(*) AS c FROM project_task_field_values WHERE task_id = ? AND value = ?",
            (task_id, "low"),
        )
        == 1
    )

    # An explicit empty set clears; an omitted key leaves the stored value alone.
    cleared = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task_id}", headers=auth, json={"tags": []}
    )
    assert cleared.status_code == 200, cleared.text
    assert (
        _count(srv, "SELECT COUNT(*) AS c FROM project_task_tags WHERE task_id = ?", (task_id,))
        == 0
    )
    untouched = await client.patch(
        f"{PROJECTS}/{pid}/tasks/{task_id}", headers=auth, json={"priority": 3}
    )
    assert untouched.status_code == 200, untouched.text
    assert (
        _count(
            srv, "SELECT COUNT(*) AS c FROM project_task_field_values WHERE task_id = ?", (task_id,)
        )
        == 1
    )


async def test_plain_create_is_unchanged(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    pid = await _project(client, ctx["admin"], "Apollo")
    created = await client.post(
        f"{PROJECTS}/{pid}/tasks", headers=ctx["admin"], json={"title": "T"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "planning"
    assert _tasks(srv, pid) == 1


async def test_a_foreign_attachment_rolls_everything_back(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """Step ④ fails → the task, its tag links and its field values are all gone,
    while the staged file stays staged (compensation never deletes user files)."""
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    other = await _project(client, auth, "Borealis")
    tag_id = await _tag(client, auth, pid, "urgent")
    field_id = await _field(client, auth, pid, "risk")
    ours = await _staged(client, auth, pid, "ours.txt")
    foreign = await _staged(client, auth, other, "theirs.txt")

    response = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={
            "title": "Doomed",
            "tags": [tag_id],
            "custom_fields": {field_id: "high"},
            "attachment_ids": [ours, foreign],
        },
    )
    assert response.status_code == 404, response.text
    assert response.status_code != 500
    assert response.json()["error"]["code"] == "NOT_FOUND"

    assert _tasks(srv, pid) == 0, "the task row must not survive compensation"
    assert _count(srv, "SELECT COUNT(*) AS c FROM project_task_tags", ()) == 0
    assert _count(srv, "SELECT COUNT(*) AS c FROM project_task_field_values", ()) == 0
    # Both staged files are back to pending, files still on disk.
    for artifact_id in (ours, foreign):
        row = srv.services.project_artifact_repo.get(artifact_id)
        assert row is not None and row.task_id is None, artifact_id
        path = (
            srv.services.paths.projects_dir
            / row.project_id
            / "attachments"
            / row.uri.rsplit("/", 1)[-1]
        )
        assert path.is_file(), f"{artifact_id} lost its file"


async def test_a_foreign_tag_is_refused_and_leaves_no_task(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    other = await _project(client, auth, "Borealis")
    foreign_tag = await _tag(client, auth, other, "theirs")

    response = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={"title": "Doomed", "tags": [foreign_tag]},
    )
    assert response.status_code == 409, response.text
    assert response.status_code != 500
    assert response.json()["error"]["code"] == "PROJECT_TASK_TAG_INVALID"
    assert _tasks(srv, pid) == 0


async def test_an_unknown_custom_field_is_refused_and_leaves_no_task(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")

    response = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={"title": "Doomed", "custom_fields": {"fld_missing": "x"}},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "PROJECT_CUSTOM_FIELD_NOT_FOUND"
    assert _tasks(srv, pid) == 0
    assert _count(srv, "SELECT COUNT(*) AS c FROM project_task_field_values", ()) == 0


async def test_missing_required_custom_field_is_400_and_leaves_no_task(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    field_id = await _field(client, auth, pid, "risk")
    patched = await client.patch(
        f"{PROJECTS}/{pid}/custom-fields/{field_id}", headers=auth, json={"required": True}
    )
    assert patched.status_code == 200, patched.text

    response = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={"title": "Doomed", "custom_fields": {}},
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PROJECT_CUSTOM_FIELD_VALUE_INVALID"
    assert _tasks(srv, pid) == 0


# ── TaskOut must carry the three resolved collections (PLAN.md §2.1/§4/§6.3) ──


async def test_board_rows_carry_tags_and_custom_fields(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    """A 201 is not enough: the board's own read must show what was written."""
    client, _, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    first_tag = await _tag(client, auth, pid, "urgent")
    second_tag = await _tag(client, auth, pid, "backend")
    risk = await _field(client, auth, pid, "risk")
    owner_field = await _field(client, auth, pid, "owner")

    created = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={
            "title": "Board card",
            "tags": [first_tag, second_tag],
            "custom_fields": {risk: "high", owner_field: "amy"},
        },
    )
    assert created.status_code == 201, created.text

    board = await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)
    assert board.status_code == 200, board.text
    row = board.json()[0]

    assert row["tags"] == [
        {"tag_id": first_tag, "name": "urgent", "color": ""},
        {"tag_id": second_tag, "name": "backend", "color": ""},
    ]
    assert [entry["field_id"] for entry in row["custom_fields"]] == [risk, owner_field]
    for entry in row["custom_fields"]:
        assert set(entry) == {"field_id", "key", "label", "type", "value"}
    assert {entry["field_id"]: entry["value"] for entry in row["custom_fields"]} == {
        risk: "high",
        owner_field: "amy",
    }
    assert row["attachments"] == []


async def test_board_rows_default_to_empty_arrays_not_null(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    await client.post(f"{PROJECTS}/{pid}/tasks", headers=auth, json={"title": "Bare"})

    row = (await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)).json()[0]
    assert row["tags"] == []
    assert row["custom_fields"] == []
    assert row["attachments"] == []


async def test_board_reads_stay_constant_time_in_row_count(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """N rows must not become N queries: one batch read per collection."""
    client, srv, ctx = api
    auth = ctx["admin"]
    pid = await _project(client, auth, "Apollo")
    tag_id = await _tag(client, auth, pid, "urgent")
    field_id = await _field(client, auth, pid, "risk")

    real_connect = srv.services.db.connect
    counter = {"n": 0}

    def counting_connect(*args: Any, **kwargs: Any) -> Any:
        counter["n"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(srv.services.db, "connect", counting_connect)

    one = await client.post(
        f"{PROJECTS}/{pid}/tasks",
        headers=auth,
        json={"title": "one", "tags": [tag_id], "custom_fields": {field_id: "high"}},
    )
    assert one.status_code == 201, one.text
    counter["n"] = 0
    assert (await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)).status_code == 200
    single_row_queries = counter["n"]

    for index in range(2):
        created = await client.post(
            f"{PROJECTS}/{pid}/tasks",
            headers=auth,
            json={
                "title": f"more-{index}",
                "tags": [tag_id],
                "custom_fields": {field_id: "low"},
            },
        )
        assert created.status_code == 201, created.text
    counter["n"] = 0
    board = await client.get(f"{PROJECTS}/{pid}/tasks", headers=auth)
    assert board.status_code == 200
    assert len(board.json()) == 3
    three_row_queries = counter["n"]

    assert three_row_queries == single_row_queries, (
        f"1 row used {single_row_queries} queries, 3 rows used {three_row_queries}"
    )
