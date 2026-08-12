"""Unit tests for in-process document indexing jobs."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import jobs
from octop.infra.knowledge.files import write_document
from octop.infra.knowledge.index import KnowledgeIndex


def test_enqueue_index_document_limits_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs.reset_index_semaphore_for_tests()
    monkeypatch.setattr(jobs, "INDEX_CONCURRENCY", 1)

    lock = threading.Lock()
    active = 0
    peak = 0
    entered = threading.Event()
    hold = threading.Event()

    def blocking(_services: object, _kb: str, _doc: str) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        entered.set()
        assert hold.wait(timeout=2)
        with lock:
            active -= 1

    monkeypatch.setattr(jobs, "process_document", blocking)

    async def run() -> None:
        first = jobs.enqueue_index_document(object(), "kb", "d1")
        second = jobs.enqueue_index_document(object(), "kb", "d2")
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        assert peak == 1
        hold.set()
        await asyncio.gather(first, second)

    asyncio.run(run())
    assert peak == 1


def test_process_document_marks_empty_extract_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    owner_id = UserRepo(pool).create(username="owner", password_hash="h", role="user")
    kb = repo.create_base(
        owner_user_id=owner_id, name="Docs", embedding_model="BAAI/bge-small-zh-v1.5"
    )
    doc = repo.create_document(
        kb_id=kb.id, filename="blank.md", content_type="text/markdown", byte_size=0
    )
    write_document(kb.id, doc.id, doc.filename, b"   \n")
    services = SimpleNamespace(knowledge_repo=repo, settings_repo=SettingsRepo(pool))
    monkeypatch.setattr(jobs, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        jobs, "embed_knowledge_texts", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError())
    )

    with pytest.raises(ValueError, match="no extractable text"):
        jobs.process_document(services, kb.id, doc.id)

    updated = repo.get_document(doc.id)
    assert updated is not None
    assert updated.status == "failed"
    assert updated.chunk_count == 0


def test_process_document_indexes_chunks_and_marks_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    owner_id = UserRepo(pool).create(username="owner", password_hash="h", role="user")
    kb = repo.create_base(
        owner_user_id=owner_id, name="Docs", embedding_model="BAAI/bge-small-zh-v1.5"
    )
    doc = repo.create_document(
        kb_id=kb.id, filename="notes.md", content_type="text/markdown", byte_size=5
    )
    write_document(kb.id, doc.id, doc.filename, b"hello")
    services = SimpleNamespace(knowledge_repo=repo, settings_repo=SettingsRepo(pool))
    monkeypatch.setattr(jobs, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        jobs, "embed_knowledge_texts", lambda _services, texts: [[1.0, 0.0] for _ in texts]
    )

    jobs.process_document(services, kb.id, doc.id)

    updated = repo.get_document(doc.id)
    assert updated is not None
    assert updated.status == "ready"
    assert updated.chunk_count == 1
    assert KnowledgeIndex(kb.id).search([1.0, 0.0], 1)[0].doc_id == doc.id


def test_reindex_all_updates_base_model_marks_documents_pending_and_enqueues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    owner_id = UserRepo(pool).create(username="owner", password_hash="h", role="user")
    kb = repo.create_base(owner_user_id=owner_id, name="Docs", embedding_model="old-model")
    doc = repo.create_document(
        kb_id=kb.id, filename="notes.md", content_type="text/markdown", byte_size=5
    )
    repo.update_document(doc.id, status="ready", chunk_count=1)
    services = SimpleNamespace(knowledge_repo=repo)
    enqueued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        jobs,
        "enqueue_index_document",
        lambda _services, kb_id, doc_id: enqueued.append((kb_id, doc_id)),
    )

    jobs.reindex_all_documents(services, "new-model")

    assert repo.get_base(kb.id).embedding_model == "new-model"
    assert repo.get_base(kb.id).embedding_dim == 0
    assert repo.get_document(doc.id).status == "pending"
    assert enqueued == [(kb.id, doc.id)]


def test_resume_pending_index_jobs_resets_processing_and_enqueues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = KnowledgeRepo(pool)
    owner_id = UserRepo(pool).create(username="owner", password_hash="h", role="user")
    kb = repo.create_base(owner_user_id=owner_id, name="Docs")
    doc = repo.create_document(
        kb_id=kb.id, filename="notes.md", content_type="text/markdown", byte_size=5
    )
    repo.update_document(doc.id, status="processing")
    services = SimpleNamespace(knowledge_repo=repo)
    enqueued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        jobs,
        "enqueue_index_document",
        lambda _services, kb_id, doc_id: enqueued.append((kb_id, doc_id)),
    )

    jobs.resume_pending_index_jobs(services)

    assert repo.get_document(doc.id).status == "pending"
    assert enqueued == [(kb.id, doc.id)]
