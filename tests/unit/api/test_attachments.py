"""Unit tests for chat attachment workspace paths."""

from __future__ import annotations

import re
import tempfile

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace
from harness_gateway.models import FileContent, InboundMessage

from octop.api.common.attachments import save_attachment
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.media.attachment_hints import (
    hints_from_content_parts,
    sniff_image_media_type,
)
from octop.infra.gateway.media.inbound_store import (
    MAX_INBOUND_BYTES,
    inbound_extension,
    validate_inbound_media_type,
    validate_inbound_size,
)
from octop.infra.gateway.media.ingress import AgentBackedMediaBackend
from octop.infra.gateway.process.harness_request import build_content_from_message


def _workspace(root: str) -> BackendWorkspace:
    backend = LocalShellBackend(root_dir=root, virtual_mode=False)
    return BackendWorkspace(backend, root)


def test_inbound_extension_from_filename() -> None:
    assert inbound_extension("report.pdf", "application/pdf") == ".pdf"
    assert inbound_extension("data.PDF", "application/pdf") == ".pdf"


def test_inbound_extension_from_media_type() -> None:
    assert inbound_extension("upload", "application/pdf") == ".pdf"


def test_inbound_extension_fallback_bin() -> None:
    assert inbound_extension("upload", "application/octet-stream") == ".bin"


def test_sniff_png_from_clipboard_blob() -> None:
    from octop.api.routers.uploads import _resolve_media_type

    png = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
    assert sniff_image_media_type(png) == "image/png"
    assert _resolve_media_type("blob", "application/octet-stream", png) == "image/png"


def test_unknown_mime_falls_back_to_extension() -> None:
    assert (
        validate_inbound_media_type("application/x-zip-compressed", "bundle.zip")
        == "application/zip"
    )
    assert validate_inbound_media_type("application/vnd.ms-excel", "data.csv") == "text/csv"
    assert validate_inbound_media_type("image/x-png", "photo.png") == "image/png"


def test_unknown_mime_without_known_extension_is_rejected() -> None:
    with pytest.raises(OctopError) as exc_info:
        validate_inbound_media_type("application/x-zip-compressed", "bundle")
    assert exc_info.value.code is ErrorCode.ATTACHMENT_UNSUPPORTED_TYPE
    # ``details.reason`` survives i18n localization; the raw message does not.
    assert "application/x-zip-compressed" in str(exc_info.value.details["reason"])
    envelope = exc_info.value.to_envelope(locale="zh")
    assert envelope["error"]["details"]["reason"] == exc_info.value.details["reason"]


def test_allowed_mime_is_kept_even_if_extension_differs() -> None:
    assert validate_inbound_media_type("application/pdf", "notes.txt") == "application/pdf"


def test_inbound_over_size_limit_is_rejected() -> None:
    with pytest.raises(OctopError) as exc_info:
        validate_inbound_size(b"x" * (MAX_INBOUND_BYTES + 1))
    assert exc_info.value.code is ErrorCode.ATTACHMENT_TOO_LARGE
    assert exc_info.value.status == 413
    max_mb = MAX_INBOUND_BYTES // (1024 * 1024)
    assert exc_info.value.details["max_mb"] == max_mb
    envelope = exc_info.value.to_envelope(locale="zh")
    assert str(max_mb) in envelope["error"]["message"]
    assert "{max_mb}" not in envelope["error"]["message"]


@pytest.mark.asyncio
async def test_save_attachment_zip_from_windows_browser() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="bundle.zip",
            media_type="application/x-zip-compressed",
            data=b"PK\x03\x04",
        )
        assert stored.media_type == "application/zip"
        assert stored.data_path.endswith(".zip")


@pytest.mark.asyncio
async def test_save_attachment_pdf_uses_extension() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="report.pdf",
            media_type="application/pdf",
            data=b"%PDF-1.4",
        )
        assert re.fullmatch(r"inbound/\d{10,}_report\.pdf", stored.data_path)
        assert stored.filename == "report.pdf"
        assert stored.data_path.endswith(".pdf")

        on_disk = await workspace.adownload_bytes(stored.data_path)
        assert on_disk == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_build_content_from_file_part_uses_resolved_path() -> None:
    from harness_gateway.models import TextContent

    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        backend = AgentBackedMediaBackend(workspace)
        msg = InboundMessage(
            channel_id="c",
            channel_type="dashboard",
            content=[
                TextContent(text="summarize"),
                FileContent(
                    filename="report.pdf",
                    mime_type="application/pdf",
                    local_path="inbound/01JTEST.pdf",
                ),
            ],
        )
        out = await build_content_from_message(msg, media_backend=backend)
        assert isinstance(out, str)
        from octop.infra.gateway.media.inbound_store import resolve_inbound_attachment_path

        resolved = resolve_inbound_attachment_path(workspace, "inbound/01JTEST.pdf")
        assert resolved in out
        assert "pdf" in out.lower()


@pytest.mark.asyncio
async def test_hints_from_saved_attachment_path() -> None:
    with tempfile.TemporaryDirectory() as ws_dir:
        workspace = _workspace(ws_dir)
        stored = await save_attachment(
            workspace,
            owner_id=1,
            filename="report.pdf",
            media_type="application/pdf",
            data=b"%PDF-1.4",
        )
        hints = hints_from_content_parts(
            [
                FileContent(
                    filename="report.pdf",
                    mime_type="application/pdf",
                    local_path=stored.data_path,
                )
            ],
            workspace=workspace,
        )
        assert len(hints) == 1
        from octop.infra.gateway.media.inbound_store import resolve_inbound_attachment_path

        resolved = resolve_inbound_attachment_path(workspace, stored.data_path)
        assert resolved in hints[0]
