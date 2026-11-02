"""Tests for BinaryReadGuardMiddleware."""

from __future__ import annotations

from octop.infra.agents.middleware.binary_read_guard import read_file_block_reason


def test_blocks_inbound_pdf() -> None:
    reason = read_file_block_reason("inbound/01KWB9MG2Z570P7QB367KDJ75R.pdf")
    assert reason is not None
    assert "pdf" in reason.lower()
    assert "execute_shell_command" in reason


def test_allows_inbound_txt() -> None:
    assert read_file_block_reason("inbound/01JTEST.txt") is None


def test_allows_inbound_log() -> None:
    assert read_file_block_reason("inbound/1793071556_octop.log") is None


def test_allows_unlisted_text_suffix() -> None:
    assert read_file_block_reason("inbound/1793071556_app.conf") is None


def test_allows_text_suffix_labeled_octet_stream() -> None:
    assert (
        read_file_block_reason(
            "inbound/1793071556_app.conf",
            media_type="application/octet-stream",
        )
        is None
    )


def test_blocks_unlabeled_unknown_inbound_suffix() -> None:
    reason = read_file_block_reason(
        "inbound/payload.unknown",
        media_type="application/octet-stream",
    )
    assert reason is not None
    assert "inbound attachment" in reason


def test_blocks_inbound_without_suffix() -> None:
    assert read_file_block_reason("inbound/payload") is not None


def test_allows_unknown_inbound_suffix_with_text_media() -> None:
    assert read_file_block_reason("inbound/notes.go", media_type="text/x-go") is None


def test_allows_workspace_file_with_unknown_suffix() -> None:
    assert (
        read_file_block_reason(
            "src/payload.unknown",
            media_type="application/octet-stream",
        )
        is None
    )


def test_blocks_inbound_image() -> None:
    reason = read_file_block_reason("inbound/1793071556_shot.png")
    assert reason is not None
    assert "binary file" in reason


def test_blocks_binary_mime_with_an_unknown_extension() -> None:
    reason = read_file_block_reason(
        "inbound/1793071556_upload.dat",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert reason is not None
    assert "binary attachment" in reason


def test_blocks_pdf_anywhere() -> None:
    assert read_file_block_reason("docs/report.pdf") is not None
