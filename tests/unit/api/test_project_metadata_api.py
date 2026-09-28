"""End-to-end HTTP contract for project tags and custom fields (plan T-INT).

Real server, real HTTP, real SQLite — no mocks in the request path. The point is
to prove two things that unit tests on the service cannot:

* the routers are actually **mounted** (an unmounted router is a 404, which looks
  identical to a missing feature);
* the authorization boundary holds over HTTP (401 without a token, 403 for a
  non-member), not only inside the service.

Every ring ends with a row count taken from the database, because this
repository has twice shipped a table that nothing read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client, write_octop_config
from tests.support.auth import auth_header, bootstrap_admin, create_user

from octop.infra.server import OctopServer

pytestmark = pytest.mark.asyncio

PROJECTS = "/api/projects"


async def _new_project(
    client: httpx.AsyncClient, auth: dict[str, str], name: str
) -> dict[str, Any]:
    response = await client.post(f"{PROJECTS}", headers=auth, json={"name": name, "goal": "ship"})
    assert response.status_code == 201, response.text
    return response.json()


async def _new_task(
    client: httpx.AsyncClient, auth: dict[str, str], project_id: str, title: str
) -> dict[str, Any]:
    response = await client.post(
        f"{PROJECTS}/{project_id}/tasks", headers=auth, json={"title": title}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _rows(srv: OctopServer, sql: str, params: tuple[object, ...] = ()) -> int:
    assert srv.services is not None
    with srv.services.db.connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


# ── mounting (the difference between "implemented" and "reachable") ──────────


async def test_the_new_routers_are_mounted_and_reachable(tmp_octop_home: Path) -> None:
    """A mounted route answers 200; an unmounted one answers 404 — both authed.

    Without a token every path answers 401 (the middleware runs before routing),
    so the contrast has to be taken with a valid token.
    """
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]

        mounted = await client.get(f"{PROJECTS}/{pid}/tags", headers=auth)
        assert mounted.status_code == 200, mounted.text

        # Live contrast from the same app: a path no router claims answers 404,
        # which is exactly what a *forgotten* mount looks like too. (The
        # attachments router used to serve as this example; it is mounted now, so
        # a literal unknown path is the honest control.)
        unmounted = await client.get(f"{PROJECTS}/{pid}/no-such-subresource", headers=auth)
        assert unmounted.status_code == 404, unmounted.text


async def test_the_new_routes_appear_in_openapi(tmp_octop_home: Path) -> None:
    """Every frozen route shape is registered with a summary and a typed model."""
    write_octop_config(tmp_octop_home, enable_api_docs=True)
    async with octop_client(tmp_octop_home) as (client, _srv):
        spec = (await client.get("/api/openapi.json")).json()
        for path in (
            f"{PROJECTS}/{{project_id}}/tags",
            f"{PROJECTS}/{{project_id}}/tags/{{tag_id}}",
            f"{PROJECTS}/{{project_id}}/tasks/{{task_id}}/tags",
            f"{PROJECTS}/{{project_id}}/custom-fields",
            f"{PROJECTS}/{{project_id}}/custom-fields/{{field_id}}",
            f"{PROJECTS}/{{project_id}}/tasks/{{task_id}}/custom-fields",
        ):
            assert path in spec["paths"], f"{path} missing from OpenAPI"

        for path, operations in spec["paths"].items():
            if "/tags" not in path and "/custom-fields" not in path:
                continue
            for method, operation in operations.items():
                if method not in {"get", "post", "patch", "put", "delete"}:
                    continue
                assert operation.get("summary", "").strip(), (
                    f"{method.upper()} {path} has no summary"
                )
                assert "projects" in operation.get("tags", []), f"{method.upper()} {path} untagged"


# ── authorization over HTTP ──────────────────────────────────────────────────


async def test_endpoints_require_a_token(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]

        unauthenticated = (
            await client.get(f"{PROJECTS}/{pid}/tags"),
            await client.post(f"{PROJECTS}/{pid}/tags", json={"name": "x"}),
            await client.get(f"{PROJECTS}/{pid}/custom-fields"),
            await client.put(f"{PROJECTS}/{pid}/tags/AAAAAA/x", json={}),
        )
        for response in unauthenticated:
            assert response.status_code == 401, f"{response.request.url}: {response.status_code}"


async def test_a_non_member_is_refused_with_403_and_its_code(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        stranger = await create_user(client, admin, username="stranger")
        project = await _new_project(client, admin, "Alpha")

        pid = project["project_id"]
        responses = (
            await client.get(f"{PROJECTS}/{pid}/tags", headers=stranger),
            await client.post(f"{PROJECTS}/{pid}/tags", headers=stranger, json={"name": "urgent"}),
            await client.get(f"{PROJECTS}/{pid}/custom-fields", headers=stranger),
            await client.post(
                f"{PROJECTS}/{pid}/custom-fields",
                headers=stranger,
                json={"key": "k", "label": "L", "type": "text"},
            ),
        )
        for response in responses:
            assert response.status_code == 403, f"{response.request.url}: {response.text}"
            assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


# ── tags: definition → link → read back, with real rows ──────────────────────


async def test_tags_end_to_end_over_http(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")
        tid = task["task_id"]

        created = await client.post(
            f"{PROJECTS}/{pid}/tags", headers=auth, json={"name": "urgent", "color": "#ff0000"}
        )
        assert created.status_code == 201, created.text
        tag = created.json()
        assert tag["name"] == "urgent"
        assert tag["color"] == "#ff0000"

        listed = await client.get(f"{PROJECTS}/{pid}/tags", headers=auth)
        assert listed.status_code == 200
        assert [t["tag_id"] for t in listed.json()] == [tag["tag_id"]]

        tagged = await client.put(
            f"{PROJECTS}/{pid}/tasks/{tid}/tags",
            headers=auth,
            json={"tags": [tag["tag_id"]]},
        )
        assert tagged.status_code == 200, tagged.text
        assert [t["tag_id"] for t in tagged.json()["tags"]] == [tag["tag_id"]]

        # ★ "table has data" — read the counts from SQLite, not from the response.
        assert _rows(srv, "SELECT COUNT(*) FROM project_tags WHERE project_id = ?", (pid,)) == 1
        assert _rows(srv, "SELECT COUNT(*) FROM project_task_tags WHERE task_id = ?", (tid,)) == 1
        assert _rows(srv, "SELECT COUNT(*) FROM project_task_tags") == 1
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_task_tags AS l "
                "LEFT JOIN project_tags AS t ON t.tag_id = l.tag_id "
                "WHERE t.tag_id IS NULL",
            )
            == 0
        ), "no orphan link may exist"

        # Deleting the definition cascades the link away.
        deleted = await client.delete(f"{PROJECTS}/{pid}/tags/{tag['tag_id']}", headers=auth)
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}
        assert _rows(srv, "SELECT COUNT(*) FROM project_task_tags WHERE task_id = ?", (tid,)) == 0
        assert _rows(srv, "SELECT COUNT(*) FROM project_tags WHERE project_id = ?", (pid,)) == 0


async def test_tag_name_conflict_is_409_over_http(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]

        body = {"name": "urgent"}
        assert (
            await client.post(f"{PROJECTS}/{pid}/tags", headers=auth, json=body)
        ).status_code == 201
        conflict = await client.post(f"{PROJECTS}/{pid}/tags", headers=auth, json=body)
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"]["code"] == "PROJECT_TASK_TAG_INVALID"


async def test_cross_project_tag_id_is_409_over_http(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        alpha = await _new_project(client, auth, "Alpha")
        beta = await _new_project(client, auth, "Beta")
        task = await _new_task(client, auth, alpha["project_id"], "Task of Alpha")
        foreign = (
            await client.post(
                f"{PROJECTS}/{beta['project_id']}/tags", headers=auth, json={"name": "urgent"}
            )
        ).json()

        response = await client.put(
            f"{PROJECTS}/{alpha['project_id']}/tasks/{task['task_id']}/tags",
            headers=auth,
            json={"tags": [foreign["tag_id"]]},
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "PROJECT_TASK_TAG_INVALID"


# ── custom fields: definition → value → read back, with real rows ────────────


async def test_custom_fields_end_to_end_over_http(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")
        tid = task["task_id"]

        # ① define
        stage = await client.post(
            f"{PROJECTS}/{pid}/custom-fields",
            headers=auth,
            json={
                "key": "stage",
                "label": "Stage",
                "type": "select",
                "options": ["todo", "doing"],
            },
        )
        assert stage.status_code == 201, stage.text
        points = await client.post(
            f"{PROJECTS}/{pid}/custom-fields",
            headers=auth,
            json={"key": "points", "label": "Points", "type": "number"},
        )
        assert points.status_code == 201, points.text
        stage_id, points_id = stage.json()["field_id"], points.json()["field_id"]

        listed = await client.get(f"{PROJECTS}/{pid}/custom-fields", headers=auth)
        assert listed.status_code == 200
        assert [f["key"] for f in listed.json()] == ["stage", "points"]

        # ② enter
        written = await client.put(
            f"{PROJECTS}/{pid}/tasks/{tid}/custom-fields",
            headers=auth,
            json={"values": {stage_id: "doing", points_id: 5}},
        )
        assert written.status_code == 200, written.text
        assert written.json()["values"] == {stage_id: "doing", points_id: "5"}

        # ★ "table has data" — both tables, from SQLite.
        assert (
            _rows(srv, "SELECT COUNT(*) FROM project_custom_fields WHERE project_id = ?", (pid,))
            == 2
        )
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_task_field_values WHERE task_id = ?",
                (tid,),
            )
            == 2
        )

        # ③ read
        read = await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/custom-fields", headers=auth)
        assert read.status_code == 200, read.text
        payload = read.json()
        assert payload["values"] == {stage_id: "doing", points_id: "5"}
        assert {f["key"] for f in payload["definitions"]} == {"stage", "points"}
        # ④ the shape the UI renders
        by_key = {f["key"]: f for f in payload["definitions"]}
        assert by_key["stage"]["options"] == ["todo", "doing"]
        assert by_key["stage"]["required"] is False
        assert by_key["points"]["options"] == []


async def test_required_value_missing_is_400_over_http(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")
        tid = task["task_id"]

        await client.post(
            f"{PROJECTS}/{pid}/custom-fields",
            headers=auth,
            json={"key": "owner_name", "label": "Owner", "type": "text", "required": True},
        )
        response = await client.put(
            f"{PROJECTS}/{pid}/tasks/{tid}/custom-fields", headers=auth, json={"values": {}}
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "PROJECT_CUSTOM_FIELD_VALUE_INVALID"


async def test_unknown_field_id_is_404_over_http(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")

        response = await client.put(
            f"{PROJECTS}/{pid}/tasks/{task['task_id']}/custom-fields",
            headers=auth,
            json={"values": {"ZZZZZZ": "x"}},
        )
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "PROJECT_CUSTOM_FIELD_NOT_FOUND"


async def test_s2_removing_a_referenced_option_is_409_and_keeps_the_value(
    tmp_octop_home: Path,
) -> None:
    """The S-2 boundary, end to end: refusal is atomic, the value survives."""
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")
        tid = task["task_id"]

        field = (
            await client.post(
                f"{PROJECTS}/{pid}/custom-fields",
                headers=auth,
                json={
                    "key": "stage",
                    "label": "Stage",
                    "type": "select",
                    "options": ["todo", "doing", "done"],
                },
            )
        ).json()
        field_id = field["field_id"]
        await client.put(
            f"{PROJECTS}/{pid}/tasks/{tid}/custom-fields",
            headers=auth,
            json={"values": {field_id: "doing"}},
        )

        refused = await client.patch(
            f"{PROJECTS}/{pid}/custom-fields/{field_id}",
            headers=auth,
            json={"options": ["todo", "done"]},
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "PROJECT_CUSTOM_FIELD_INVALID"

        # ★ the stored value is still there, and the definition is unchanged
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_task_field_values WHERE task_id = ?",
                (tid,),
            )
            == 1
        )
        after = await client.get(f"{PROJECTS}/{pid}/custom-fields", headers=auth)
        assert after.json()[0]["options"] == ["todo", "doing", "done"]
        read = await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/custom-fields", headers=auth)
        assert read.json()["values"] == {field_id: "doing"}


# ── attachments: staged → bound → listed → downloaded → deleted ──────────────
#
# These exercise the attachment subsystem on its own. The "create a task with
# attachment_ids" path belongs to §2.3 and is covered separately once that
# orchestration lands; nothing here goes through TaskCreate.

PDF = ("brief.pdf", b"%PDF-1.4 staged bytes", "application/pdf")


async def test_attachment_staged_upload_bind_list_download_delete(
    tmp_octop_home: Path,
) -> None:
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")
        tid = task["task_id"]

        # ① stage: uploaded before any task exists (the create dialog's 📎 path)
        staged = await client.post(
            f"{PROJECTS}/{pid}/attachments", headers=auth, files={"file": PDF}
        )
        assert staged.status_code == 201, staged.text
        artifact = staged.json()
        assert artifact["task_id"] is None, "a staged attachment has no task yet"
        assert artifact["name"] == "brief.pdf"
        assert artifact["mime"] == "application/pdf"
        assert artifact["size"] == len(PDF[1])
        assert artifact["uploader"].startswith("user:")

        # ② bind explicitly
        bound = await client.patch(
            f"{PROJECTS}/{pid}/attachments/{artifact['artifact_id']}",
            headers=auth,
            json={"task_id": tid},
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["task_id"] == tid

        # ③ list
        listed = await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/attachments", headers=auth)
        assert listed.status_code == 200, listed.text
        assert [a["artifact_id"] for a in listed.json()] == [artifact["artifact_id"]]

        # ★ "table has data" — the metadata row is real, and it holds the size/mime
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_artifacts WHERE project_id = ? AND kind = 'attachment'",
                (pid,),
            )
            == 1
        )
        assert _rows(
            srv,
            "SELECT size FROM project_artifacts WHERE artifact_id = ?",
            (artifact["artifact_id"],),
        ) == len(PDF[1])

        # ④ download returns the exact bytes
        download = await client.get(
            f"{PROJECTS}/{pid}/attachments/{artifact['artifact_id']}/download", headers=auth
        )
        assert download.status_code == 200, download.text
        assert download.content == PDF[1]

        # ⑤ delete removes the row, and the attachment is gone afterwards
        deleted = await client.delete(
            f"{PROJECTS}/{pid}/attachments/{artifact['artifact_id']}", headers=auth
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"deleted": True}
        assert (
            _rows(srv, "SELECT COUNT(*) FROM project_artifacts WHERE project_id = ?", (pid,)) == 0
        )
        assert (
            await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/attachments", headers=auth)
        ).json() == []
        gone = await client.get(
            f"{PROJECTS}/{pid}/attachments/{artifact['artifact_id']}/download", headers=auth
        )
        assert gone.status_code == 404, gone.text


async def test_attachment_upload_rejects_a_non_whitelisted_type(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]

        for payload in (
            ("evil.sh", b"#!/bin/sh\n", "application/x-sh"),
            ("sneaky.pdf", b"%PDF", "application/x-sh"),  # MIME and extension disagree
        ):
            response = await client.post(
                f"{PROJECTS}/{pid}/attachments", headers=auth, files={"file": payload}
            )
            assert response.status_code == 400, f"{payload[0]}: {response.text}"
            assert response.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"


async def test_rebinding_a_bound_attachment_is_409(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Draft the plan")
        tid = task["task_id"]

        # Uploaded straight onto the task, so it is already bound.
        created = await client.post(
            f"{PROJECTS}/{pid}/tasks/{tid}/attachments", headers=auth, files={"file": PDF}
        )
        assert created.status_code == 201, created.text
        artifact_id = created.json()["artifact_id"]

        again = await client.patch(
            f"{PROJECTS}/{pid}/attachments/{artifact_id}", headers=auth, json={"task_id": tid}
        )
        assert again.status_code == 409, again.text
        assert again.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"


async def test_attachment_endpoints_refuse_a_non_member(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        stranger = await create_user(client, admin, username="stranger")
        project = await _new_project(client, admin, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, admin, pid, "Draft the plan")
        tid = task["task_id"]
        artifact = (
            await client.post(f"{PROJECTS}/{pid}/attachments", headers=admin, files={"file": PDF})
        ).json()

        responses = (
            await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/attachments", headers=stranger),
            await client.post(
                f"{PROJECTS}/{pid}/attachments", headers=stranger, files={"file": PDF}
            ),
            await client.get(
                f"{PROJECTS}/{pid}/attachments/{artifact['artifact_id']}/download",
                headers=stranger,
            ),
            await client.delete(
                f"{PROJECTS}/{pid}/attachments/{artifact['artifact_id']}", headers=stranger
            ),
        )
        for response in responses:
            assert response.status_code == 403, f"{response.request.url}: {response.text}"
            assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


async def test_attachment_from_another_project_is_not_found(tmp_octop_home: Path) -> None:
    """The ``{project_id}`` segment is part of the resource's identity."""
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        alpha = await _new_project(client, auth, "Alpha")
        beta = await _new_project(client, auth, "Beta")
        beta_task = await _new_task(client, auth, beta["project_id"], "Task of Beta")
        artifact = (
            await client.post(
                f"{PROJECTS}/{alpha['project_id']}/attachments", headers=auth, files={"file": PDF}
            )
        ).json()

        # Alpha's attachment is unreachable through Beta's path.
        cross = await client.get(
            f"{PROJECTS}/{beta['project_id']}/attachments/{artifact['artifact_id']}/download",
            headers=auth,
        )
        assert cross.status_code == 404, cross.text

        # And Beta's task cannot adopt it.
        foreign = await client.patch(
            f"{PROJECTS}/{beta['project_id']}/attachments/{artifact['artifact_id']}",
            headers=auth,
            json={"task_id": beta_task["task_id"]},
        )
        assert foreign.status_code == 404, foreign.text


# ── dispatch (FIND-2): a human assignee is a 4xx, never a 500 ────────────────


async def test_dispatching_a_human_assignee_is_409_not_500(tmp_octop_home: Path) -> None:
    """FIND-2: ``require_dispatchable`` must raise ``OctopError``, not ``ValueError``.

    A ``ValueError`` would fall through to the catch-all handler and surface as a
    500, which is why this asserts the code *and* the status explicitly.
    """
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]

        created = await client.post(
            f"{PROJECTS}/{pid}/tasks",
            headers=auth,
            json={"title": "Assigned to a person", "assignee_type": "user", "assignee_id": "1"},
        )
        assert created.status_code == 201, created.text
        tid = created.json()["task_id"]

        response = await client.post(f"{PROJECTS}/{pid}/tasks/{tid}:dispatch", headers=auth)
        assert response.status_code == 409, response.text
        assert response.status_code != 500, "a human assignee is a caller error, not a fault"
        assert response.json()["error"]["code"] == "PROJECT_TASK_DISPATCH_INVALID"


async def test_dispatching_a_task_without_an_assignee_is_409(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, auth, pid, "Nobody owns this")

        response = await client.post(
            f"{PROJECTS}/{pid}/tasks/{task['task_id']}:dispatch", headers=auth
        )
        assert response.status_code == 409, response.text
        assert response.status_code != 500
        assert response.json()["error"]["code"] == "PROJECT_TASK_DISPATCH_INVALID"


async def test_dispatch_refuses_a_non_member(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (client, _srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        stranger = await create_user(client, admin, username="stranger")
        project = await _new_project(client, admin, "Alpha")
        pid = project["project_id"]
        task = await _new_task(client, admin, pid, "Assigned to a person")

        response = await client.post(
            f"{PROJECTS}/{pid}/tasks/{task['task_id']}:dispatch", headers=stranger
        )
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "PROJECT_FORBIDDEN"


# ── §2.3 create orchestration: three metadata kinds written on create ────────


async def test_create_task_writes_tags_custom_fields_and_attachments(
    tmp_octop_home: Path,
) -> None:
    """One POST writes the task, its tags, its field values and its attachments."""
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        project = await _new_project(client, auth, "Alpha")
        pid = project["project_id"]

        tag = (
            await client.post(f"{PROJECTS}/{pid}/tags", headers=auth, json={"name": "urgent"})
        ).json()
        field = (
            await client.post(
                f"{PROJECTS}/{pid}/custom-fields",
                headers=auth,
                json={"key": "stage", "label": "Stage", "type": "select", "options": ["todo"]},
            )
        ).json()
        staged = (
            await client.post(f"{PROJECTS}/{pid}/attachments", headers=auth, files={"file": PDF})
        ).json()

        created = await client.post(
            f"{PROJECTS}/{pid}/tasks",
            headers=auth,
            json={
                "title": "Everything at once",
                "tags": [tag["tag_id"]],
                "custom_fields": {field["field_id"]: "todo"},
                "attachment_ids": [staged["artifact_id"]],
            },
        )
        assert created.status_code == 201, created.text
        tid = created.json()["task_id"]

        # Read the values and attachments back over HTTP. (A task's tags have no
        # GET route by design — PLAN §4 reads them back through ``TaskOut.tags``,
        # which is the projects router's field to wire.)
        values = await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/custom-fields", headers=auth)
        assert values.status_code == 200, values.text
        assert values.json()["values"] == {field["field_id"]: "todo"}
        attachments = await client.get(f"{PROJECTS}/{pid}/tasks/{tid}/attachments", headers=auth)
        assert [a["artifact_id"] for a in attachments.json()] == [staged["artifact_id"]]

        # ★ "table has data" for all four tables touched by the orchestration.
        assert _rows(srv, "SELECT COUNT(*) FROM project_tasks WHERE project_id = ?", (pid,)) == 1
        assert _rows(srv, "SELECT COUNT(*) FROM project_task_tags WHERE task_id = ?", (tid,)) == 1
        assert (
            _rows(srv, "SELECT COUNT(*) FROM project_task_field_values WHERE task_id = ?", (tid,))
            == 1
        )
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_artifacts WHERE task_id = ? AND kind = 'attachment'",
                (tid,),
            )
            == 1
        )


async def test_create_task_compensation_leaves_no_residue(tmp_octop_home: Path) -> None:
    """A failure in step ④ rolls back in reverse and never deletes the file.

    The staged attachment belongs to another project, so binding it must fail —
    and the half-built task, its tag link and its field value must all be gone,
    while the attachment itself goes back to *pending* untouched.
    """
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        alpha = await _new_project(client, auth, "Alpha")
        beta = await _new_project(client, auth, "Beta")
        pid, beta_pid = alpha["project_id"], beta["project_id"]

        tag = (
            await client.post(f"{PROJECTS}/{pid}/tags", headers=auth, json={"name": "urgent"})
        ).json()
        field = (
            await client.post(
                f"{PROJECTS}/{pid}/custom-fields",
                headers=auth,
                json={"key": "note", "label": "Note", "type": "text"},
            )
        ).json()
        # Uploaded into *Beta*, then offered to an Alpha task.
        foreign = (
            await client.post(
                f"{PROJECTS}/{beta_pid}/attachments", headers=auth, files={"file": PDF}
            )
        ).json()

        before = _rows(srv, "SELECT COUNT(*) FROM project_tasks WHERE project_id = ?", (pid,))

        response = await client.post(
            f"{PROJECTS}/{pid}/tasks",
            headers=auth,
            json={
                "title": "Doomed by step four",
                "tags": [tag["tag_id"]],
                "custom_fields": {field["field_id"]: "hello"},
                "attachment_ids": [foreign["artifact_id"]],
            },
        )
        assert response.status_code == 404, response.text

        # ★ no residue: the task row is gone, so its cascades took the rest
        after = _rows(srv, "SELECT COUNT(*) FROM project_tasks WHERE project_id = ?", (pid,))
        assert after == before, "the compensating delete must remove the task row"
        assert _rows(srv, "SELECT COUNT(*) FROM project_task_tags") == 0
        assert _rows(srv, "SELECT COUNT(*) FROM project_task_field_values") == 0

        # ★ the file/row survived and went back to pending — compensation never
        # deletes an upload, the user may retry.
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_artifacts WHERE artifact_id = ?",
                (foreign["artifact_id"],),
            )
            == 1
        )
        assert (
            _rows(
                srv,
                "SELECT COUNT(*) FROM project_artifacts WHERE artifact_id = ? AND task_id IS NULL",
                (foreign["artifact_id"],),
            )
            == 1
        ), "the attachment must return to pending"
