"""Backup notes survive creation, download, and re-upload."""

from __future__ import annotations

import json
import tarfile
from io import BytesIO

import pytest


@pytest.mark.asyncio
async def test_backup_note_survives_download_and_upload(env) -> None:
    client, _server, auth = env
    note = "升级前的稳定版本\nBefore upgrading 🚀 <script>alert(1)</script>"
    response = await client.post(
        "/api/admin/backup/create",
        headers=auth,
        json={"note": f"  {note}  ", "include_workspaces": False},
    )
    assert response.status_code == 200, response.text
    item = response.json()["item"]
    assert item["note"] == note

    response = await client.get("/api/admin/backup/list", headers=auth)
    assert response.status_code == 200
    assert response.json()["items"][0]["note"] == note

    response = await client.get(f"/api/admin/backup/files/{item['name']}", headers=auth)
    assert response.status_code == 200
    downloaded = response.content
    with tarfile.open(fileobj=BytesIO(downloaded), mode="r:gz") as archive:
        first = archive.next()
        assert first is not None and first.name == "manifest.json"
        manifest_file = archive.extractfile(first)
        assert manifest_file is not None
        assert json.load(manifest_file)["note"] == note

    response = await client.delete(f"/api/admin/backup/files/{item['name']}", headers=auth)
    assert response.status_code == 204
    response = await client.post(
        "/api/admin/backup/import",
        headers=auth,
        files={"file": ("renamed-backup.tgz", downloaded, "application/gzip")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["item"]["note"] == note
    response = await client.get("/api/admin/backup/list", headers=auth)
    assert response.json()["items"][0]["note"] == note


@pytest.mark.asyncio
@pytest.mark.parametrize("note", [None, "", " " * 10, "a" * 500])
async def test_optional_backup_note(env, note: str | None) -> None:
    client, _server, auth = env
    # None here means an older client that does not send the field.
    payload = {} if note is None else {"note": note}
    response = await client.post("/api/admin/backup/create", headers=auth, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["item"]["note"] == (note or "").strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("note", ["a" * 501, None, 123])
async def test_invalid_backup_note_is_rejected_before_creation(env, note: object) -> None:
    client, server, auth = env
    response = await client.post("/api/admin/backup/create", headers=auth, json={"note": note})
    assert response.status_code == 422
    assert not list(server.paths.backups_dir.glob("*.tar.gz"))
