"""Filesystem layout and safe document persistence for knowledge bases."""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from contextlib import suppress
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


def write_document(kb_id: str, doc_id: str, filename: str, content: bytes) -> Path:
    path = document_path(kb_id, doc_id, filename)
    existing_mode = None
    if os.name == "posix" and path.exists():
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    stream = temporary.open("xb")
    try:
        with stream as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        if existing_mode is not None:
            os.chmod(temporary, existing_mode)
        # Same-directory replacement publishes complete bytes after the file is closed.
        os.replace(temporary, path)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
    return path


def delete_document_file(kb_id: str, doc_id: str, filename: str) -> None:
    document_path(kb_id, doc_id, filename).unlink(missing_ok=True)


def delete_knowledge_base_files(kb_id: str) -> None:
    shutil.rmtree(knowledge_base_dir(kb_id), ignore_errors=True)
