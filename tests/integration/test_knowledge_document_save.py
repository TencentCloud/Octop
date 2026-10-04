"""Failed knowledge edits must preserve the original document and index state."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.api.routers import knowledge_bases
from octop.infra.knowledge.files import document_path


async def test_failed_edit_preserves_readable_content_and_can_be_retried(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, server, auth = env
    monkeypatch.setattr(knowledge_bases, "_require_usable", lambda *_a: None)
    monkeypatch.setattr("octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a: None)
    enqueue = MagicMock()
    monkeypatch.setattr(knowledge_bases, "enqueue_index_document", enqueue)
    base = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Docs"})
    assert base.status_code == 201, base.text
    kb_id = base.json()["knowledge_base_id"]
    created = await client.post(
        f"/api/knowledge-bases/{kb_id}/documents/text",
        headers=auth,
        json={"name": "notes", "format": "md", "content": "原文应完整保留"},
    )
    assert created.status_code == 201, created.text
    doc_id = created.json()["document_id"]
    target = document_path(kb_id, doc_id, "notes.md")
    server.services.knowledge_repo.update_document(doc_id, status="ready", chunk_count=7)
    real_open = Path.open

    @contextmanager
    def failing_open(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Iterator[Any]:
        with real_open(path, mode, *args, **kwargs) as stream:
            if mode in ("wb", "xb") and path.parent == target.parent:

                def write(data: bytes) -> int:
                    stream.write(data[:3])
                    stream.flush()
                    raise OSError("simulated disk failure")

                yield SimpleNamespace(write=write)
            else:
                yield stream

    endpoint = f"/api/knowledge-bases/{kb_id}/documents/{doc_id}/content"
    with monkeypatch.context() as fault:
        fault.setattr(Path, "open", failing_open)
        failed = await client.put(endpoint, headers=auth, json={"content": "new content"})
        assert failed.status_code == 500, failed.text
        readable = await client.get(endpoint, headers=auth)
        assert readable.status_code == 200, readable.text
        assert readable.json()["text"] == "原文应完整保留"
    stored = server.services.knowledge_repo.get_document(doc_id)
    assert (stored.status, stored.chunk_count) == ("ready", 7)
    assert enqueue.call_count == 1
    assert set(target.parent.iterdir()) == {target}

    retried = await client.put(endpoint, headers=auth, json={"content": "complete new content"})
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"
    assert enqueue.call_count == 2
    assert target.read_bytes() == b"complete new content"
