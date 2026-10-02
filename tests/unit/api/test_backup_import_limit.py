"""The backup import route must cap the upload before the body is fully assembled.

``POST /backup/import`` is the only multipart upload in the backup surface that
still called ``await file.read()`` and compared ``len(raw)`` afterwards, so a
512MB-over-limit archive was pulled into memory in full before the guard fired.
``read_upload_capped`` already exists for exactly this and is used by the
attachment and knowledge-base upload routes.
"""

from __future__ import annotations

import pytest

from octop.api.routers import backup as backup_router
from octop.infra.backup.store import BackupFileInfo
from octop.infra.errors import ErrorCode, OctopError

CHUNK = 1024 * 1024


def _stored(name: str, size: int) -> BackupFileInfo:
    return BackupFileInfo(
        name=name,
        size=size,
        modified_at="2026-01-01T00:00:00+00:00",
        created_at="2026-01-01T00:00:00+00:00",
    )


class _CountingUpload:
    """Minimal ``UploadFile`` stand-in that records how much was pulled."""

    def __init__(self, data: bytes, *, size: int | None = None, filename: str = "b.tar.gz") -> None:
        self._data = data
        self._pos = 0
        self.filename = filename
        self.content_type = "application/gzip"
        self.size = size
        self.bytes_pulled = 0
        self.read_sizes: list[int] = []

    async def read(self, n: int = -1) -> bytes:
        self.read_sizes.append(n)
        remaining = self._data[self._pos :]
        chunk = remaining if n < 0 else remaining[:n]
        self._pos += len(chunk)
        self.bytes_pulled += len(chunk)
        return chunk


def _server() -> object:
    class _Paths:
        backups_dir = None

    class _Server:
        paths = _Paths()

    return _Server()


@pytest.mark.asyncio
async def test_import_stops_reading_once_the_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An oversize declared size must be refused before the body is assembled."""
    monkeypatch.setattr(backup_router, "_MAX_IMPORT_BYTES", 8)
    monkeypatch.setattr(backup_router, "write_backup_file", lambda *a, **k: None)

    upload = _CountingUpload(b"x" * (3 * CHUNK), size=3 * CHUNK)

    with pytest.raises(OctopError) as exc_info:
        await backup_router.import_backup(file=upload, _=None, server=_server())  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.SLASH_BAD_ARGS
    # The whole point: the body must never be pulled into memory.
    assert upload.bytes_pulled == 0
    assert upload.read_sizes == []


@pytest.mark.asyncio
async def test_import_stops_mid_stream_when_the_limit_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a declared size the read must still abort early, not at the end."""
    monkeypatch.setattr(backup_router, "_MAX_IMPORT_BYTES", 8)
    monkeypatch.setattr(backup_router, "write_backup_file", lambda *a, **k: None)

    # Body spans several chunks, so "abort once the cap is passed" is observable:
    # the old code drained all of it, the capped read stops after the first chunk.
    upload = _CountingUpload(b"x" * (3 * CHUNK), size=None)

    with pytest.raises(OctopError) as exc_info:
        await backup_router.import_backup(file=upload, _=None, server=_server())  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.SLASH_BAD_ARGS
    assert upload.bytes_pulled <= 8 + CHUNK
    assert upload.bytes_pulled < 3 * CHUNK


@pytest.mark.asyncio
async def test_import_reads_in_bounded_chunks_and_stores_the_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body under the limit is read in chunks and handed to the store unchanged."""
    monkeypatch.setattr(backup_router, "_MAX_IMPORT_BYTES", 4096)
    stored: list[tuple[str, bytes]] = []

    def _fake_write(paths: object, filename: str, data: bytes) -> BackupFileInfo:
        stored.append((filename, data))
        return _stored(filename, len(data))

    monkeypatch.setattr(backup_router, "write_backup_file", _fake_write)

    upload = _CountingUpload(b"payload", size=None)

    result = await backup_router.import_backup(file=upload, _=None, server=_server())  # type: ignore[arg-type]

    assert result["ok"] is True
    assert stored == [("b.tar.gz", b"payload")]
    # No single unbounded read: every read is capped at the chunk size.
    assert upload.read_sizes and all(0 < size <= CHUNK for size in upload.read_sizes)


@pytest.mark.asyncio
async def test_import_still_rejects_an_empty_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-existing empty-body guard must survive the change."""
    monkeypatch.setattr(backup_router, "_MAX_IMPORT_BYTES", 4096)
    monkeypatch.setattr(backup_router, "write_backup_file", lambda *a, **k: None)

    upload = _CountingUpload(b"", size=None)

    with pytest.raises(OctopError) as exc_info:
        await backup_router.import_backup(file=upload, _=None, server=_server())  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.SLASH_BAD_ARGS
    assert "empty" in exc_info.value.message
