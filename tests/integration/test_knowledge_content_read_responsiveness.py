"""Raw document reads must leave the shared HTTP loop responsive."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest

from octop.api.routers import knowledge_bases
from octop.infra.knowledge import service
from octop.infra.knowledge.files import document_path
from tests.support.auth import create_user


@pytest.mark.parametrize("invalid_utf8", [False, True])
async def test_raw_content_read_is_offloop_and_preserves_errors(
    env: Any, monkeypatch: pytest.MonkeyPatch, invalid_utf8: bool
) -> None:
    client, _server, auth = env
    monkeypatch.setattr(knowledge_bases, "_require_usable", lambda *_a: None)
    monkeypatch.setattr(service, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(knowledge_bases, "enqueue_index_document", lambda *_a: None)
    base = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Docs"})
    assert base.status_code == 201, base.text
    kb = base.json()["knowledge_base_id"]
    created = await client.post(
        f"/api/knowledge-bases/{kb}/documents/text",
        headers=auth,
        json={"name": "notes", "format": "md", "content": "需要完整读取的正文"},
    )
    assert created.status_code == 201, created.text
    doc = created.json()["document_id"]
    target = document_path(kb, doc, "notes.md")
    if invalid_utf8:
        target.write_bytes(b"\xff\xfe")
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    original = Path.read_bytes
    observed: list[tuple[bool, bool]] = []

    def read(path: Path) -> bytes:
        if path == target:
            pending = asyncio.run_coroutine_threadsafe(
                client.get("/api/settings/timezone", headers=auth), loop
            )
            try:
                responsive = pending.result(timeout=3).status_code == 200
            except TimeoutError:
                responsive = False
            finally:
                pending.cancel()
            observed.append((threading.get_ident() != loop_thread, responsive))
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    endpoint = f"/api/knowledge-bases/{kb}/documents/{doc}/content"
    specification = client._octop_app.openapi()
    assert (
        specification["paths"]["/api/knowledge-bases/{kb_id}/documents/{doc_id}/content"]["get"][
            "summary"
        ]
        == "Read raw editable text for a markdown or plain-text document"
    )
    other = await create_user(
        client, auth, username="other_reader", permissions=["knowledge_bases"]
    )
    denied = await client.get(endpoint, headers=other)
    assert denied.status_code == 403, denied.text
    assert observed == []
    response = await client.get(endpoint, headers=auth)
    assert response.status_code == (500 if invalid_utf8 else 200), response.text
    if not invalid_utf8:
        assert response.json()["text"] == "需要完整读取的正文"
        assert response.json()["filename"] == "notes.md"
    else:
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert (
            response.json()["error"]["details"]["cause"]
            == "knowledge document is not valid UTF-8 text"
        )
    assert observed == [(True, True)], "raw content read blocked the shared event loop"
