"""Integration tests for dashboard chat attachments in agent workspace."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest


async def test_upload_and_workspace_download(env_with_agent: Any) -> None:
    client, _srv, auth, aid = env_with_agent
    files = {"file": ("note.txt", b"hello attachment", "text/plain")}
    r = await client.post(f"/api/agents/{aid}/upload", files=files, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == body["workspace_path"]
    assert body["access_url"].startswith(f"/api/agents/{aid}/workspace/download")
    assert body["filename"] == "note.txt"
    assert body["media_type"] == "text/plain"
    assert body["workspace_path"].endswith(".txt")
    assert body["workspace_path"].startswith("inbound/")
    assert re.search(r"inbound/[0-9a-f]{32}/\d{10,}_note\.txt$", body["workspace_path"])
    assert "file_id" not in body
    assert "legacy_url" not in body

    r2 = await client.get(body["access_url"], headers=auth)
    assert r2.status_code == 200, r2.text
    assert r2.content == b"hello attachment"


async def test_upload_pdf_workspace_path(env_with_agent: Any) -> None:
    client, _srv, auth, aid = env_with_agent
    files = {"file": ("report.pdf", b"%PDF-1.4", "application/pdf")}
    r = await client.post(f"/api/agents/{aid}/upload", files=files, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace_path"].endswith(".pdf")
    assert body["filename"] == "report.pdf"

    r2 = await client.get(body["access_url"], headers=auth)
    assert r2.status_code == 200, r2.text
    assert r2.content == b"%PDF-1.4"


async def test_upload_requires_auth(env: Any) -> None:
    client, _srv, _auth = env
    files = {"file": ("note.txt", b"x", "text/plain")}
    r = await client.post("/api/agents/NOPE/upload", files=files)
    assert r.status_code == 401, r.text


async def test_concurrent_same_name_uploads_preserve_both_files(
    env_with_agent: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, srv, auth, aid = env_with_agent
    workspace = srv.app_runtime.agent_registry.get_agent(aid).workspace
    upload = workspace.aupload_bytes
    ready = asyncio.Event()
    waiting = 0

    async def synchronized_upload(path: str, data: bytes) -> None:
        nonlocal waiting
        waiting += 1
        if waiting == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=10)
        await upload(path, data)

    # Schedule both real writes after path allocation, without replacing storage.
    monkeypatch.setattr(workspace, "aupload_bytes", synchronized_upload)
    monkeypatch.setattr("octop.infra.gateway.media.inbound_store.time.time", lambda: 1783510288)
    contents = (b"first document", b"second document")
    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/agents/{aid}/upload",
                headers=auth,
                files={"file": ("report.txt", data, "text/plain")},
            )
            for data in contents
        ]
    )
    assert [response.status_code for response in responses] == [200, 200]
    bodies = [response.json() for response in responses]
    assert bodies[0]["path"] != bodies[1]["path"]
    assert [body["filename"] for body in bodies] == ["report.txt", "report.txt"]
    downloads = [await client.get(body["access_url"], headers=auth) for body in bodies]
    assert [response.status_code for response in downloads] == [200, 200]
    assert [response.content for response in downloads] == list(contents)
