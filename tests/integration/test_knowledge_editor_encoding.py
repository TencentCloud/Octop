"""Uploaded Chinese text supported by indexing must also open in the editor."""

from __future__ import annotations

from typing import Any

import pytest

from octop.api.routers import knowledge_bases
from octop.infra.knowledge import service
from octop.infra.knowledge.files import document_path
from tests.support.auth import create_user


@pytest.mark.parametrize("encoding", ["gbk", "gb18030"])
async def test_uploaded_chinese_document_can_be_read_and_saved(
    env: Any, monkeypatch: pytest.MonkeyPatch, encoding: str
) -> None:
    client, _server, auth = env
    monkeypatch.setattr(knowledge_bases, "_require_usable", lambda *_a: None)
    monkeypatch.setattr(service, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(knowledge_bases, "enqueue_index_document", lambda *_a: None)
    base = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Docs"})
    assert base.status_code == 201, base.text
    kb = base.json()["knowledge_base_id"]
    text = "# 中文标题\r\n完整正文。\r\n"
    if encoding == "gb18030":
        text += "扩展汉字：𠀀\r\n"
    created = await client.post(
        f"/api/knowledge-bases/{kb}/documents",
        headers=auth,
        files={"upload": ("notes.md", text.encode(encoding), "text/markdown")},
    )
    assert created.status_code == 201, created.text
    doc = created.json()["document_id"]
    endpoint = f"/api/knowledge-bases/{kb}/documents/{doc}/content"
    other = await create_user(
        client, auth, username="other_editor", permissions=["knowledge_bases"]
    )
    denied = await client.get(endpoint, headers=other)
    assert denied.status_code == 403, denied.text
    readable = await client.get(endpoint, headers=auth)
    assert readable.status_code == 200, readable.text
    assert readable.json()["text"] == text
    edited = text + "新增文字\n"
    saved = await client.put(endpoint, headers=auth, json={"content": edited})
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "pending"
    assert document_path(kb, doc, "notes.md").read_bytes() == edited.encode("utf-8")
