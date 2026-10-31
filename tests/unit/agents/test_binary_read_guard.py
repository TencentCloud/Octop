"""Tests for BinaryReadGuardMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop.infra.agents.middleware.binary_read_guard import (
    BinaryReadGuardMiddleware,
    _workspace_path,
    read_file_block_reason,
)


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


def test_workspace_path_accepts_inbound_prefix() -> None:
    assert _workspace_path("inbound/1793159656_iron-man.pptx") == "inbound/1793159656_iron-man.pptx"


def test_workspace_path_strips_virtual_prefix() -> None:
    assert (
        _workspace_path("/.octop/workspaces/C10WX7/inbound/1793159656_iron-man.pptx")
        == "inbound/1793159656_iron-man.pptx"
    )


@pytest.mark.asyncio
async def test_inbound_pptx_is_blocked_without_reading() -> None:
    request = ToolCallRequest(
        tool_call={
            "name": "read_file",
            "args": {"file_path": "inbound/1793159656_iron-man.pptx"},
            "id": "call-1",
        },
        tool=None,
        state={
            "messages": [
                HumanMessage(
                    content="看看",
                    additional_kwargs={
                        "octop_inbound_attachments": [
                            {
                                "workspace_path": "/.octop/workspaces/C10WX7/inbound/1793159656_iron-man.pptx",
                                "media_type": (
                                    "application/vnd.openxmlformats-officedocument"
                                    ".presentationml.presentation"
                                ),
                            }
                        ]
                    },
                )
            ]
        },
        runtime=None,  # type: ignore[arg-type]
    )
    handler = AsyncMock()

    result = await BinaryReadGuardMiddleware().awrap_tool_call(request, handler)

    handler.assert_not_awaited()
    assert getattr(result, "status", None) == "error"
    assert "binary" in str(getattr(result, "content", "")).lower()


@pytest.mark.asyncio
async def test_inbound_text_still_reaches_read_file() -> None:
    request = ToolCallRequest(
        tool_call={"name": "read_file", "args": {"file_path": "inbound/notes.txt"}, "id": "call-1"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )
    handler = AsyncMock(return_value="ok")

    result = await BinaryReadGuardMiddleware().awrap_tool_call(request, handler)

    assert result == "ok"
    assert handler.await_args.args[0] is request
