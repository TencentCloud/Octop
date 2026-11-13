"""Shared HTTP mapping for authorized Office → PDF preview."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import quote, unquote

from fastapi import Request
from fastapi.responses import Response

from octop.api.common.content_disposition import content_disposition
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.formats import is_convertible_filename
from octop.infra.office_preview.service import get_office_preview_service

MISSING_FONTS_HEADER = "X-Octop-Office-Missing-Fonts"


def encode_missing_fonts_header(fonts: Sequence[str]) -> str:
    """Percent-encode font names so Starlette can send the header as Latin-1."""
    return ",".join(quote(name, safe="") for name in fonts[:8] if name)


def decode_missing_fonts_header(value: str) -> list[str]:
    """Inverse of :func:`encode_missing_fonts_header`."""
    out: list[str] = []
    for item in value.split(","):
        token = item.strip()
        if not token:
            continue
        out.append(unquote(token))
    return out


def pdf_preview_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "preview"
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return f"{name}.pdf"


async def office_preview_pdf_response(
    *,
    request: Request,
    filename: str,
    cache_scope: str,
    source_id: str,
    load_bytes: Callable[[], Awaitable[bytes]],
    known_size: int | None = None,
) -> Response:
    """Convert an already-authorized source to ``application/pdf``."""
    if not is_convertible_filename(filename):
        raise OctopError(
            ErrorCode.OFFICE_PREVIEW_UNSUPPORTED,
            "this file type cannot be converted for preview",
        )
    service = get_office_preview_service()
    result = await service.convert(
        cache_scope=cache_scope,
        source_id=source_id,
        filename=filename,
        load_bytes=load_bytes,
        known_size=known_size,
        is_disconnected=request.is_disconnected,
    )
    headers = {
        "Content-Disposition": content_disposition(
            pdf_preview_filename(filename), disposition="inline"
        ),
        "Cache-Control": "private, no-store",
        "ETag": f'"{result.digest}"',
        "X-Octop-Office-Preview-Digest": result.digest,
    }
    if result.missing_fonts:
        headers[MISSING_FONTS_HEADER] = encode_missing_fonts_header(result.missing_fonts)
    return Response(content=result.pdf, media_type="application/pdf", headers=headers)
