"""Bounded reads for Office preview sources."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.limits import MAX_INPUT_BYTES

_CHUNK = 1024 * 1024


def too_large_error() -> OctopError:
    return OctopError(
        ErrorCode.OFFICE_PREVIEW_TOO_LARGE,
        "office document exceeds the preview size limit",
    )


def file_size_if_present(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def assert_not_too_large(size: int, *, max_bytes: int = MAX_INPUT_BYTES) -> None:
    if size > max_bytes:
        raise too_large_error()


def read_stream_capped(fh: BinaryIO, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    """Read *fh* in chunks and abort as soon as *max_bytes* is exceeded."""
    chunks: list[bytes] = []
    total = 0
    step = _CHUNK if _CHUNK > 0 else max_bytes
    while True:
        chunk = fh.read(step)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise too_large_error()
        chunks.append(chunk)
    return b"".join(chunks)


def read_path_capped(path: Path, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    """Stat *path* when possible, then read with a hard byte cap."""
    size = file_size_if_present(path)
    if size is not None:
        assert_not_too_large(size, max_bytes=max_bytes)
    with path.open("rb") as fh:
        return read_stream_capped(fh, max_bytes)
