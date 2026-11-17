from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.service import ConvertedPdf, reset_office_preview_service


class _Service:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def status(self) -> dict[str, object]:
        return {"available": False, "reason": "kit_missing", "kit_version": "0.2.3"}

    async def convert(self, **kwargs: object) -> ConvertedPdf:
        load_bytes = kwargs["load_bytes"]
        assert callable(load_bytes)
        data = await load_bytes()  # type: ignore[misc]
        assert data == b"office-bytes"
        self.calls.append(
            {
                "scope": str(kwargs["cache_scope"]),
                "source": str(kwargs["source_id"]),
                "filename": str(kwargs["filename"]),
            }
        )
        return ConvertedPdf(pdf=b"%PDF-1.7\n", digest="abc", missing_fonts=("Arial",))


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.fixture(autouse=True)
def _reset_service() -> None:
    reset_office_preview_service()
    yield
    reset_office_preview_service()


@pytest.mark.asyncio
async def test_status_endpoint() -> None:
    from octop.api.routers import office_preview as router

    reset_office_preview_service(_Service())  # type: ignore[arg-type]
    payload = await router.office_preview_status(_=SimpleNamespace())
    assert payload["available"] is False
    assert payload["reason"] == "kit_missing"


@pytest.mark.asyncio
async def test_unsupported_filename_rejected_before_convert() -> None:
    from octop.api.common.office_preview import office_preview_pdf_response

    with pytest.raises(OctopError) as raised:
        await office_preview_pdf_response(
            request=_request(),
            filename="notes.csv",
            cache_scope="u",
            source_id="notes.csv",
            load_bytes=lambda: _never(),
        )
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_UNSUPPORTED


async def _never() -> bytes:
    raise AssertionError("should not read source for unsupported types")


@pytest.mark.asyncio
async def test_pdf_response_headers() -> None:
    from octop.api.common.office_preview import office_preview_pdf_response

    reset_office_preview_service(_Service())  # type: ignore[arg-type]

    async def load() -> bytes:
        return b"office-bytes"

    response = await office_preview_pdf_response(
        request=_request(),
        filename="报告.docx",
        cache_scope="workspace:1:agent",
        source_id="报告.docx",
        load_bytes=load,
    )
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert response.headers["X-Octop-Office-Preview-Digest"] == "abc"
    assert "Arial" in response.headers["X-Octop-Office-Missing-Fonts"]
    assert "inline" in response.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_pdf_response_missing_fonts_header_is_latin1() -> None:
    from octop.api.common.office_preview import (
        decode_missing_fonts_header,
        office_preview_pdf_response,
    )

    class _CjkService:
        async def convert(self, **kwargs: object) -> ConvertedPdf:
            load_bytes = kwargs["load_bytes"]
            assert callable(load_bytes)
            await load_bytes()  # type: ignore[misc]
            return ConvertedPdf(
                pdf=b"%PDF-1.7\n",
                digest="abc",
                missing_fonts=("宋体", "Noto Sans"),
            )

    reset_office_preview_service(_CjkService())  # type: ignore[arg-type]

    async def load() -> bytes:
        return b"office-bytes"

    response = await office_preview_pdf_response(
        request=_request(),
        filename="报告.docx",
        cache_scope="workspace:1:agent",
        source_id="报告.docx",
        load_bytes=load,
    )
    raw = response.headers["X-Octop-Office-Missing-Fonts"]
    raw.encode("latin-1")
    assert decode_missing_fonts_header(raw) == ["宋体", "Noto Sans"]
