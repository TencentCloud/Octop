"""Invalid folder names must not corrupt the knowledge tree through HTTP."""

from __future__ import annotations

from typing import Any

import pytest

from octop.api.routers import knowledge_bases


async def test_dot_folder_rename_is_rejected_without_changing_tree(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _server, auth = env
    monkeypatch.setattr(knowledge_bases, "_require_usable", lambda *_a: None)
    monkeypatch.setattr("octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(knowledge_bases, "enqueue_index_document", lambda *_a: None)
    created = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Docs"})
    assert created.status_code == 201, created.text
    kb = created.json()["knowledge_base_id"]
    folder = await client.post(
        f"/api/knowledge-bases/{kb}/folders", headers=auth, json={"path": "notes"}
    )
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["document_id"]
    child = await client.post(
        f"/api/knowledge-bases/{kb}/documents/text",
        headers=auth,
        json={"name": "leaf", "format": "md", "path": "notes", "content": "重要内容"},
    )
    assert child.status_code == 201, child.text
    rejected = await client.post(
        f"/api/knowledge-bases/{kb}/documents/{folder_id}/rename",
        headers=auth,
        json={"new_name": "."},
    )
    assert rejected.status_code == 400, rejected.text
    rows = await client.get(f"/api/knowledge-bases/{kb}/documents", headers=auth)
    assert rows.status_code == 200, rows.text
    assert {row["path"] for row in rows.json()} == {"notes", "notes/leaf.md"}
    readable = await client.get(
        f"/api/knowledge-bases/{kb}/documents/{child.json()['document_id']}/content", headers=auth
    )
    assert readable.status_code == 200, readable.text
    assert readable.json()["text"] == "重要内容"
