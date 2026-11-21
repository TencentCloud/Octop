"""Knowledge-base original files: local directory or PostgreSQL file table.

PostgreSQL mode stores bytes in ``public.knowledge_files`` and keeps a local
copy so parsers and ``FileResponse`` can keep reading a path. The table is
the source of truth; the local file is refreshed from it on read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop_harness.backends.postgres import PostgresBackend

from octop.config import DatabaseConfig
from octop.infra.db.file_store import KNOWLEDGE_FILES, open_postgres_files
from octop.infra.knowledge.files import (
    delete_document_file,
    delete_knowledge_base_files,
    document_path,
    write_document,
)
from octop.infra.knowledge.plane import postgres_database


class KnowledgeBlobs:
    """Read and write one document's original bytes."""

    def __init__(self, database: DatabaseConfig | None) -> None:
        self._backend: PostgresBackend | None = None
        if database is not None and database.is_postgresql:
            self._backend = open_postgres_files(database, schema="public", table=KNOWLEDGE_FILES)

    @classmethod
    def from_services(cls, services: Any) -> KnowledgeBlobs:
        return cls(postgres_database(services))

    def _key(self, kb_id: str, doc_id: str, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        return f"/{kb_id}/docs/{doc_id}{suffix}"

    def _read_remote(self, kb_id: str, doc_id: str, filename: str) -> bytes | None:
        backend = self._backend
        if backend is None:
            return None
        downloaded = backend.download_files([self._key(kb_id, doc_id, filename)])
        if not downloaded:
            return None
        item = downloaded[0]
        if getattr(item, "error", None) or getattr(item, "content", None) is None:
            return None
        content = item.content
        return content if isinstance(content, bytes) else None

    def write(self, kb_id: str, doc_id: str, filename: str, content: bytes) -> Path:
        path = write_document(kb_id, doc_id, filename, content)
        backend = self._backend
        if backend is not None:
            results = backend.upload_files([(self._key(kb_id, doc_id, filename), content)])
            failed = [item for item in results if getattr(item, "error", None)]
            if failed:
                raise OSError(f"failed to store knowledge document: {failed[0].error}")
        return path

    def ensure_local(self, kb_id: str, doc_id: str, filename: str) -> Path:
        """Return a local path whose bytes match the source of truth."""
        path = document_path(kb_id, doc_id, filename)
        if self._backend is None:
            return path
        payload = self._read_remote(kb_id, doc_id, filename)
        if payload is None:
            path.unlink(missing_ok=True)
            return path
        path.write_bytes(payload)
        return path

    def exists(self, kb_id: str, doc_id: str, filename: str) -> bool:
        if self._backend is None:
            return document_path(kb_id, doc_id, filename).is_file()
        return self._read_remote(kb_id, doc_id, filename) is not None

    def read_bytes(self, kb_id: str, doc_id: str, filename: str) -> bytes:
        if self._backend is not None:
            payload = self._read_remote(kb_id, doc_id, filename)
            if payload is None:
                raise FileNotFoundError("knowledge document original file not found")
            return payload
        return document_path(kb_id, doc_id, filename).read_bytes()

    def delete(self, kb_id: str, doc_id: str, filename: str) -> None:
        delete_document_file(kb_id, doc_id, filename)
        backend = self._backend
        if backend is not None:
            backend.delete_object(self._key(kb_id, doc_id, filename))

    def delete_base(self, kb_id: str) -> None:
        backend = self._backend
        if backend is not None:
            backend.delete_prefix(f"/{kb_id}")
        delete_knowledge_base_files(kb_id)
