"""Filesystem layout and safe document persistence for knowledge bases."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from octop.infra.utils.paths import PathLayout


def knowledge_base_dir(kb_id: str) -> Path:
    return PathLayout.from_env().knowledge_dir / kb_id


def documents_dir(kb_id: str) -> Path:
    path = knowledge_base_dir(kb_id) / "docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def document_path(kb_id: str, doc_id: str, filename: str) -> Path:
    suffix = Path(filename).suffix.lower()
    return documents_dir(kb_id) / f"{doc_id}{suffix}"


def _write_bytes_atomically(path: Path, content: bytes) -> None:
    """Publish *content* at *path* so a failed write cannot destroy the old file.

    ``write_bytes`` truncates first, so a disk error part-way through replaced an
    existing document with a prefix of the new one while the row still reported
    the previous size, and readers could see the fragment.
    """
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_document(kb_id: str, doc_id: str, filename: str, content: bytes) -> Path:
    path = document_path(kb_id, doc_id, filename)
    _write_bytes_atomically(path, content)
    return path


def delete_document_file(kb_id: str, doc_id: str, filename: str) -> None:
    document_path(kb_id, doc_id, filename).unlink(missing_ok=True)


def delete_knowledge_base_files(kb_id: str) -> None:
    shutil.rmtree(knowledge_base_dir(kb_id), ignore_errors=True)
