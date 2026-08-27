"""Capped multipart reads must stop before assembling an oversize body."""

from __future__ import annotations

import pytest

from octop.api.common.upload_limit import read_upload_capped
from octop.infra.errors import ErrorCode, OctopError


class _CountingReader:
    def __init__(self, data: bytes, *, size: int | None = None) -> None:
        self._data = data
        self._pos = 0
        self.size = size
        self.bytes_pulled = 0

    async def read(self, n: int = -1) -> bytes:
        remaining = self._data[self._pos :]
        chunk = remaining if n < 0 else remaining[:n]
        self._pos += len(chunk)
        self.bytes_pulled += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_read_upload_capped_returns_body_under_limit() -> None:
    reader = _CountingReader(b"hello")
    data = await read_upload_capped(reader, max_bytes=16)
    assert data == b"hello"


@pytest.mark.asyncio
async def test_read_upload_capped_stops_after_exceeding_chunk() -> None:
    reader = _CountingReader(b"x" * 50)
    with pytest.raises(OctopError) as exc_info:
        await read_upload_capped(reader, max_bytes=8, chunk_size=4)
    assert exc_info.value.code is ErrorCode.ATTACHMENT_TOO_LARGE
    assert reader.bytes_pulled <= 12


@pytest.mark.asyncio
async def test_read_upload_capped_skips_read_when_declared_size_is_over() -> None:
    class _Declared:
        size = 50

        async def read(self, n: int = -1) -> bytes:
            raise AssertionError("must not read when declared size exceeds the limit")

    with pytest.raises(OctopError) as exc_info:
        await read_upload_capped(_Declared(), max_bytes=8)
    assert exc_info.value.code is ErrorCode.ATTACHMENT_TOO_LARGE
    assert exc_info.value.details["max_mb"] == 1


@pytest.mark.asyncio
async def test_read_upload_capped_uses_caller_error_code() -> None:
    reader = _CountingReader(b"x" * 20)
    with pytest.raises(OctopError) as exc_info:
        await read_upload_capped(
            reader,
            max_bytes=4,
            chunk_size=4,
            code=ErrorCode.KNOWLEDGE_DOC_TOO_LARGE,
        )
    assert exc_info.value.code is ErrorCode.KNOWLEDGE_DOC_TOO_LARGE


def test_text_document_pydantic_ceiling_follows_hard_cap() -> None:
    from annotated_types import MaxLen

    from octop.api.routers.knowledge_bases import CreateTextDocumentBody, UpdateTextDocumentBody
    from octop.config import MAX_MAX_UPLOAD_MB, upload_mb_to_bytes

    ceiling = upload_mb_to_bytes(MAX_MAX_UPLOAD_MB)
    for model in (CreateTextDocumentBody, UpdateTextDocumentBody):
        field = model.model_fields["content"]
        max_len = next(item.max_length for item in field.metadata if isinstance(item, MaxLen))
        assert max_len == ceiling
