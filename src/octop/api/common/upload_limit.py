"""Cap multipart uploads before the whole body is assembled in memory."""

from __future__ import annotations

from typing import Protocol

from octop.infra.errors import ErrorCode, OctopError

_DEFAULT_CHUNK = 1024 * 1024


class AsyncByteReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def _too_large(max_bytes: int, code: ErrorCode) -> OctopError:
    max_mb = max(1, max_bytes // (1024 * 1024))
    return OctopError(
        code,
        f"file too large (max {max_mb}MB)",
        details={"max_mb": max_mb},
    )


def _declared_size(upload: object) -> int | None:
    raw = getattr(upload, "size", None)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return None
    return raw


async def read_upload_capped(
    upload: AsyncByteReader,
    *,
    max_bytes: int,
    chunk_size: int = _DEFAULT_CHUNK,
    code: ErrorCode = ErrorCode.ATTACHMENT_TOO_LARGE,
) -> bytes:
    """Read *upload* in chunks and abort as soon as *max_bytes* is exceeded."""
    declared = _declared_size(upload)
    if declared is not None and declared > max_bytes:
        raise _too_large(max_bytes, code)
    chunks: list[bytes] = []
    total = 0
    step = chunk_size if chunk_size > 0 else _DEFAULT_CHUNK
    while True:
        chunk = await upload.read(step)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _too_large(max_bytes, code)
        chunks.append(chunk)
    return b"".join(chunks)
