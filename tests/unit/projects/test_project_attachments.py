"""Project attachments — real HTTP, real files, real rows (PLAN.md §7).

Boots a real ``OctopServer`` (whose repo bundle now carries
``project_artifact_repo``) and drives the mounted ``/api/projects/…/attachments``
routes. Every case writes into a temporary ``OCTOP_HOME``; nothing touches the
developer's real ``~/.octop``.

Covered: staging → bind → list → download (sha256) → delete; the four security
refusals (non-member 403, oversize 413, bad type 400, traversal 400); a foreign
task id; lazy 24h collection; same-name duplicates; id collisions in the DB and
on disk; and the per-task quota.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_user

import octop.infra.projects.attachments as attachments_mod
from octop.infra.projects.attachments import (
    PENDING_TTL_SECONDS,
    ProjectAttachmentService,
)

ATTACHMENTS = "/api/projects/{pid}/attachments"
TASK_ATTACHMENTS = "/api/projects/{pid}/tasks/{tid}/attachments"


@pytest.fixture
async def api(tmp_octop_home: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any, dict[str, Any]]]:
    """Admin (project owner) + a non-member user, plus one project and one task."""
    async with octop_client(tmp_octop_home) as (client, srv):
        await bootstrap_admin(client, tmp_octop_home)
        admin = await auth_header(client)
        bob = await create_user(client, admin, username="bob")
        created = await client.post("/api/projects", headers=admin, json={"name": "Apollo"})
        assert created.status_code == 201, created.text
        project_id = created.json()["project_id"]
        task = await client.post(
            f"/api/projects/{project_id}/tasks",
            headers=admin,
            json={"title": "Attach it", "status": "todo"},
        )
        assert task.status_code == 201, task.text
        yield (
            client,
            srv,
            {
                "admin": admin,
                "bob": bob,
                "project_id": project_id,
                "task_id": task.json()["task_id"],
            },
        )


def _upload(client: httpx.AsyncClient, auth: dict[str, str], pid: str, **kwargs: Any) -> Any:
    return client.post(
        ATTACHMENTS.format(pid=pid),
        headers=auth,
        files={"file": kwargs.pop("file", ("notes.txt", b"hello world", "text/plain"))},
        **kwargs,
    )


def _service(srv: Any) -> ProjectAttachmentService:
    return ProjectAttachmentService(srv.services)


async def test_positive_upload_bind_list_download_delete(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    auth, pid, tid = ctx["admin"], ctx["project_id"], ctx["task_id"]
    payload = b"hello world"

    staged = await _upload(client, auth, pid, file=("notes.txt", payload, "text/plain"))
    assert staged.status_code == 201, staged.text
    body = staged.json()
    assert body["task_id"] is None, "the staged upload must not be bound yet"
    assert body["name"] == "notes.txt" and body["size"] == len(payload)
    assert "uri" not in body and "path" not in body
    artifact_id = body["artifact_id"]

    # The metadata row exists (not just the file) — the "table has data" check.
    row = srv.services.project_artifact_repo.get(artifact_id)
    assert row is not None and row.task_id is None and row.mime == "text/plain"
    stored = _service(srv).attachments_dir(pid) / row.uri.rsplit("/", 1)[-1]
    assert stored.is_file(), "the file must be on disk inside the project dir"

    bound = await client.patch(
        f"{ATTACHMENTS.format(pid=pid)}/{artifact_id}", headers=auth, json={"task_id": tid}
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["task_id"] == tid

    listed = await client.get(TASK_ATTACHMENTS.format(pid=pid, tid=tid), headers=auth)
    assert listed.status_code == 200, listed.text
    assert [a["artifact_id"] for a in listed.json()] == [artifact_id]
    assert set(listed.json()[0]) == {
        "artifact_id",
        "task_id",
        "name",
        "size",
        "mime",
        "created_at",
        "uploader",
    }

    downloaded = await client.get(
        f"{ATTACHMENTS.format(pid=pid)}/{artifact_id}/download", headers=auth
    )
    assert downloaded.status_code == 200, downloaded.text
    assert hashlib.sha256(downloaded.content).hexdigest() == hashlib.sha256(payload).hexdigest()
    assert "attachment" in downloaded.headers["content-disposition"]

    deleted = await client.delete(f"{ATTACHMENTS.format(pid=pid)}/{artifact_id}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert not stored.exists(), "delete must remove the file too"
    assert srv.services.project_artifact_repo.get(artifact_id) is None


async def test_upload_onto_a_task_binds_immediately(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    response = await client.post(
        TASK_ATTACHMENTS.format(pid=ctx["project_id"], tid=ctx["task_id"]),
        headers=ctx["admin"],
        files={"file": ("shot.png", b"\x89PNG", "image/png")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["task_id"] == ctx["task_id"]


async def test_non_member_is_forbidden(api: tuple[httpx.AsyncClient, Any, dict[str, Any]]) -> None:
    client, _, ctx = api
    response = await _upload(client, ctx["bob"], ctx["project_id"])
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] in {"PROJECT_FORBIDDEN", "FORBIDDEN"}


async def test_oversize_is_413_with_the_attachment_code(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, ctx = api
    monkeypatch.setattr(ProjectAttachmentService, "max_file_bytes", lambda self: 4)

    response = await _upload(
        client, ctx["admin"], ctx["project_id"], file=("big.txt", b"1234567890", "text/plain")
    )
    assert response.status_code == 413, response.text
    assert response.status_code != 500
    assert response.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("page.html", "text/html"),
        ("vector.svg", "image/svg+xml"),
        ("script.js", "application/javascript"),
        ("notes.txt", "image/png"),  # extension and MIME must agree
    ],
)
async def test_type_whitelist_is_mime_and_extension_together(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], name: str, mime: str
) -> None:
    client, _, ctx = api
    response = await _upload(client, ctx["admin"], ctx["project_id"], file=(name, b"payload", mime))
    assert response.status_code == 400, response.text
    assert response.status_code != 500
    assert response.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"


@pytest.mark.parametrize("name", ["../evil.txt", "..%2fevil.txt", "/etc/passwd", "a\\b.txt"])
async def test_traversal_names_are_rejected_before_writing(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], name: str
) -> None:
    client, srv, ctx = api
    response = await _upload(
        client, ctx["admin"], ctx["project_id"], file=(name, b"x", "text/plain")
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"
    directory = _service(srv).attachments_dir(ctx["project_id"])
    assert list(directory.glob("*")) == [], "nothing may be written for a rejected name"


async def test_foreign_task_id_is_a_404(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    other = await client.post("/api/projects", headers=ctx["admin"], json={"name": "Borealis"})
    other_pid = other.json()["project_id"]
    foreign_task = await client.post(
        f"/api/projects/{other_pid}/tasks",
        headers=ctx["admin"],
        json={"title": "Elsewhere", "status": "todo"},
    )
    response = await client.post(
        TASK_ATTACHMENTS.format(pid=ctx["project_id"], tid=foreign_task.json()["task_id"]),
        headers=ctx["admin"],
        files={"file": ("notes.txt", b"x", "text/plain")},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_already_bound_attachment_cannot_be_rebound(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    pid, tid = ctx["project_id"], ctx["task_id"]
    staged = await _upload(client, ctx["admin"], pid)
    artifact_id = staged.json()["artifact_id"]

    first = await client.patch(
        f"{ATTACHMENTS.format(pid=pid)}/{artifact_id}", headers=ctx["admin"], json={"task_id": tid}
    )
    assert first.status_code == 200, first.text
    again = await client.patch(
        f"{ATTACHMENTS.format(pid=pid)}/{artifact_id}", headers=ctx["admin"], json={"task_id": tid}
    )
    assert again.status_code == 409, again.text
    assert again.status_code != 500
    assert again.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"


async def test_same_name_uploads_are_two_rows_with_two_files(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    pid = ctx["project_id"]
    first = await _upload(client, ctx["admin"], pid, file=("dup.txt", b"first", "text/plain"))
    second = await _upload(client, ctx["admin"], pid, file=("dup.txt", b"second", "text/plain"))
    assert first.status_code == second.status_code == 201

    ids = {first.json()["artifact_id"], second.json()["artifact_id"]}
    assert len(ids) == 2
    rows = [srv.services.project_artifact_repo.get(i) for i in ids]
    assert all(row is not None and row.name == "dup.txt" for row in rows)
    assert len({row.uri for row in rows if row}) == 2, "stored names must differ"
    for row in rows:
        assert row is not None
        stored = _service(srv).attachments_dir(pid) / row.uri.rsplit("/", 1)[-1]
        assert stored.read_bytes() in (b"first", b"second")


async def test_expired_pending_is_collected_on_the_next_write(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, srv, ctx = api
    pid = ctx["project_id"]
    staged = await _upload(client, ctx["admin"], pid, file=("old.txt", b"stale", "text/plain"))
    artifact_id = staged.json()["artifact_id"]
    row = srv.services.project_artifact_repo.get(artifact_id)
    assert row is not None
    stored = _service(srv).attachments_dir(pid) / row.uri.rsplit("/", 1)[-1]

    with srv.services.db.transaction() as conn:
        conn.execute(
            "UPDATE project_artifacts SET created_at = created_at - ? WHERE artifact_id = ?",
            (PENDING_TTL_SECONDS + 3600, artifact_id),
        )

    again = await _upload(client, ctx["admin"], pid, file=("fresh.txt", b"new", "text/plain"))
    assert again.status_code == 201, again.text
    assert srv.services.project_artifact_repo.get(artifact_id) is None
    assert not stored.exists(), "the expired file must be unlinked as well"


async def test_id_collision_retries_until_a_free_id_is_found(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, srv, ctx = api
    pid = ctx["project_id"]
    first = await _upload(client, ctx["admin"], pid, file=("a.txt", b"a", "text/plain"))
    taken = first.json()["artifact_id"]
    # The next attempt proposes an id already used by a row, then one already on
    # disk, and only then a free one.
    sequence = iter([taken, "ZZZZZZ", "YYYYYY"])
    monkeypatch.setattr(attachments_mod, "new_short_id", lambda: next(sequence))
    stored_collision = _service(srv).attachments_dir(pid) / "ZZZZZZ.txt"
    stored_collision.write_bytes(b"occupied")

    response = await _upload(client, ctx["admin"], pid, file=("b.txt", b"b", "text/plain"))
    assert response.status_code == 201, response.text
    assert response.json()["artifact_id"] == "YYYYYY"
    assert stored_collision.read_bytes() == b"occupied", "the colliding file is untouched"


async def test_per_task_quota_is_413(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, ctx = api
    pid, tid = ctx["project_id"], ctx["task_id"]
    monkeypatch.setattr(attachments_mod, "PROJECT_TASK_ATTACHMENT_TOTAL_MAX_BYTES", 8)

    seeded = await client.post(
        TASK_ATTACHMENTS.format(pid=pid, tid=tid),
        headers=ctx["admin"],
        files={"file": ("one.txt", b"12345", "text/plain")},
    )
    assert seeded.status_code == 201, seeded.text

    response = await client.post(
        TASK_ATTACHMENTS.format(pid=pid, tid=tid),
        headers=ctx["admin"],
        files={"file": ("two.txt", b"12345", "text/plain")},
    )
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "PROJECT_ATTACHMENT_INVALID"


async def test_staged_rows_are_not_listed_for_a_task(
    api: tuple[httpx.AsyncClient, Any, dict[str, Any]],
) -> None:
    client, _, ctx = api
    await _upload(client, ctx["admin"], ctx["project_id"])
    listed = await client.get(
        TASK_ATTACHMENTS.format(pid=ctx["project_id"], tid=ctx["task_id"]), headers=ctx["admin"]
    )
    assert listed.json() == []
