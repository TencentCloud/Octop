"""In-process document indexing jobs."""

from __future__ import annotations

import asyncio
from typing import Any

from octop.infra.knowledge.chunk import chunk_text
from octop.infra.knowledge.embed import embed_knowledge_texts
from octop.infra.knowledge.files import document_path
from octop.infra.knowledge.gate import assert_knowledge_usable
from octop.infra.knowledge.index import KnowledgeIndex
from octop.infra.knowledge.ocr import optional_ocr_extractor
from octop.infra.knowledge.params import get_advanced_settings
from octop.infra.knowledge.parse import parse_document

INDEX_CONCURRENCY = 2
_index_semaphore: asyncio.Semaphore | None = None


def reset_index_semaphore_for_tests() -> None:
    """Drop the cached semaphore so tests can change INDEX_CONCURRENCY."""
    global _index_semaphore
    _index_semaphore = None


def _get_index_semaphore() -> asyncio.Semaphore:
    global _index_semaphore
    if _index_semaphore is None:
        _index_semaphore = asyncio.Semaphore(INDEX_CONCURRENCY)
    return _index_semaphore


def process_document(services: Any, kb_id: str, doc_id: str) -> None:
    """Synchronously parse, embed, and atomically replace one document's chunks."""
    repo = services.knowledge_repo
    assert_knowledge_usable(services.settings_repo.get, getattr(services, "provider_repo", None))
    document = repo.get_document(doc_id)
    base = repo.get_base(kb_id)
    if document is None or document.kb_id != kb_id or base is None:
        raise LookupError("knowledge document or base not found")
    if document.is_dir:
        return
    repo.update_document(doc_id, status="processing", error_message="")
    try:
        path = document_path(kb_id, doc_id, document.filename)
        text = parse_document(path, ocr=optional_ocr_extractor(services))
        knobs = get_advanced_settings(services.settings_repo.get)
        chunks = chunk_text(text, size=knobs["chunk_size"], overlap=knobs["chunk_overlap"])
        if not (text or "").strip() or not chunks:
            raise ValueError("knowledge document has no extractable text")
        embeddings = embed_knowledge_texts(services, chunks)
        KnowledgeIndex(kb_id).replace_doc_chunks(doc_id, chunks, embeddings)
        dimension = len(embeddings[0]) if embeddings else 0
        repo.update_document(doc_id, status="ready", error_message="", chunk_count=len(chunks))
        if dimension and base.embedding_dim != dimension:
            repo.update_base(kb_id, embedding_dim=dimension)
    except Exception as exc:
        repo.update_document(doc_id, status="failed", error_message=str(exc), chunk_count=0)
        raise


def enqueue_index_document(services: Any, kb_id: str, doc_id: str) -> asyncio.Task[None]:
    """Schedule CPU- and I/O-bound indexing outside the event loop."""
    loop = asyncio.get_running_loop()
    sem = _get_index_semaphore()

    async def _run() -> None:
        async with sem:
            await loop.run_in_executor(None, process_document, services, kb_id, doc_id)

    return asyncio.create_task(_run())


def reindex_all_documents(services: Any, embedding_model: str) -> None:
    """Reset every index to use ``embedding_model`` and schedule fresh work."""
    documents = services.knowledge_repo.reindex_all_documents(embedding_model)
    for document in documents:
        enqueue_index_document(services, document.kb_id, document.id)


def resume_pending_index_jobs(services: Any) -> None:
    """Resume pending work and jobs interrupted by a prior process shutdown."""
    documents = services.knowledge_repo.resume_pending_documents()
    for document in documents:
        enqueue_index_document(services, document.kb_id, document.id)
