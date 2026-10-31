"""Filesystem layout and safe document persistence for knowledge bases."""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
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


def _default_file_mode() -> int:
    """The mode a plain ``write_bytes`` produced (``0o666 & ~umask``).

    POSIX has no get-only umask call, so read it by set-and-restore; ``mkstemp``
    would otherwise leave 0600 and silently tighten the permissions of a
    document created before this write path became atomic.
    """
    if os.name != "posix":
        return 0o644
    mask = os.umask(0o022)
    os.umask(mask)
    return 0o666 & ~mask


def write_document(kb_id: str, doc_id: str, filename: str, content: bytes) -> Path:
    """Write one document via temp file + ``os.replace``.

    Saving an edited text document rewrites the same path, and that file is the
    only copy of the content: an in-place ``write_bytes`` truncates it first, so
    a full disk, a kill, or a power loss leaves an empty or half-written
    document behind while its row still claims the previous size. Reindexing
    then reads the truncated text and the original is unrecoverable. Readers
    now observe either the old bytes or the new bytes, never a mix; the temp
    file is unique per call (``mkstemp``) so concurrent writers cannot share a
    ``.tmp`` name.

    Permissions follow the file being replaced, or the process umask for a new
    document, matching ``Path.write_bytes``.
    """
    path = document_path(kb_id, doc_id, filename)
    existing_mode: int | None = None
    if os.name == "posix" and path.exists():
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        if os.name == "posix":
            os.chmod(
                tmp_name,
                _default_file_mode() if existing_mode is None else existing_mode,
            )
        os.replace(tmp_name, path)
    except BaseException:  # also covers KeyboardInterrupt / SystemExit
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return path


def delete_document_file(kb_id: str, doc_id: str, filename: str) -> None:
    document_path(kb_id, doc_id, filename).unlink(missing_ok=True)


def delete_knowledge_base_files(kb_id: str) -> None:
    shutil.rmtree(knowledge_base_dir(kb_id), ignore_errors=True)
