"""Knowledge parsing must not freeze unrelated HTTP requests."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from octop.api.routers import knowledge_bases
from octop.infra.knowledge import service
from tests.support.auth import create_user


@pytest.mark.parametrize("parser_fails", [False, True])
async def test_preview_parsing_keeps_http_responsive(
    env: Any, monkeypatch: pytest.MonkeyPatch, parser_fails: bool
) -> None:
    client, _server, auth = env
    monkeypatch.setattr(knowledge_bases, "_require_usable", lambda *_a: None)
    monkeypatch.setattr(service, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(knowledge_bases, "enqueue_index_document", lambda *_a: None)
    base = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Docs"})
    assert base.status_code == 201, base.text
    kb = base.json()["knowledge_base_id"]
    doc = await client.post(
        f"/api/knowledge-bases/{kb}/documents/text",
        headers=auth,
        json={"name": "notes", "format": "md", "content": "需要保留的正文"},
    )
    assert doc.status_code == 201, doc.text
    doc_id = doc.json()["document_id"]
    specification = client._octop_app.openapi()
    assert (
        specification["paths"]["/api/knowledge-bases/{kb_id}/documents/{doc_id}/preview"]["get"][
            "summary"
        ]
        == "Preview extracted document text"
    )
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    real_parse = service.parse_document
    observed: list[tuple[bool, bool]] = []

    def parse(*args: Any, **kwargs: Any) -> str:
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
        if parser_fails:
            raise ValueError("unsupported knowledge document content type")
        return real_parse(*args, **kwargs)

    monkeypatch.setattr(service, "parse_document", parse)
    other = await create_user(client, auth, username="preview_other")
    denied = await client.get(
        f"/api/knowledge-bases/{kb}/documents/{doc_id}/preview", headers=other
    )
    assert denied.status_code == 403, denied.text
    assert observed == []
    response = await client.get(
        f"/api/knowledge-bases/{kb}/documents/{doc_id}/preview", headers=auth
    )
    assert response.status_code == (400 if parser_fails else 200), response.text
    if not parser_fails:
        assert response.json()["text"] == "需要保留的正文"
    else:
        assert response.json()["error"]["code"]
    assert observed == [(True, True)], "preview parsing blocked the shared event loop"
