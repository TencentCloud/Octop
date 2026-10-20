"""Tests for FilesystemGuard outside-root soft-fail."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage

from octop_harness.middleware.filesystem_guard import (
    FilesystemGuardMiddleware,
    is_path_outside_root_error,
    path_outside_root_tool_message,
    rewrite_legacy_windows_fs_path,
)


def test_is_path_outside_root_error_matches_deepagents_message() -> None:
    exc = ValueError(r"Path:D:\octop-data\data\x.md outside root directory: C:\Users\Administrator")
    assert is_path_outside_root_error(exc) is True


def test_is_path_outside_root_error_matches_traversal() -> None:
    assert is_path_outside_root_error(ValueError("Path traversal not allowed")) is True


def test_is_path_outside_root_error_ignores_other_value_errors() -> None:
    assert is_path_outside_root_error(ValueError("invalid offset")) is False
    assert is_path_outside_root_error(RuntimeError("outside root directory")) is False


def test_path_outside_root_tool_message_shape() -> None:
    msg = path_outside_root_tool_message(
        tool_name="read_file",
        tool_call_id="call_1",
        exc=ValueError("Path:/tmp/x outside root directory: /home"),
    )
    assert isinstance(msg, ToolMessage)
    assert msg.status == "error"
    assert msg.name == "read_file"
    assert msg.tool_call_id == "call_1"
    assert "outside root directory" in str(msg.content)
    assert "storage root" in str(msg.content).lower()


@pytest.mark.asyncio
async def test_middleware_softens_outside_root_value_error() -> None:
    mw = FilesystemGuardMiddleware()
    request = MagicMock()
    request.tool_call = {"name": "read_file", "id": "call_99", "args": {}}

    async def boom(_req: Any) -> ToolMessage:
        raise ValueError("Path:/D:/data/x.md outside root directory: C:/Users/me")

    out = await mw.awrap_tool_call(request, boom)
    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert out.tool_call_id == "call_99"
    assert "outside root directory" in str(out.content)


@pytest.mark.asyncio
async def test_middleware_reraises_unrelated_value_error() -> None:
    mw = FilesystemGuardMiddleware()
    request = MagicMock()
    request.tool_call = {"name": "read_file", "id": "call_1", "args": {}}

    async def boom(_req: Any) -> ToolMessage:
        raise ValueError("limit must be > 0")

    with pytest.raises(ValueError, match="limit must be > 0"):
        await mw.awrap_tool_call(request, boom)


@pytest.mark.asyncio
async def test_middleware_does_not_soften_non_fs_tool() -> None:
    """Outside-root text from a non-filesystem tool must still propagate."""
    mw = FilesystemGuardMiddleware()
    request = MagicMock()
    request.tool_call = {"name": "web_fetch", "id": "call_w", "args": {}}

    async def boom(_req: Any) -> ToolMessage:
        raise ValueError("Path:/tmp/x outside root directory: /home")

    with pytest.raises(ValueError, match="outside root directory"):
        await mw.awrap_tool_call(request, boom)


def test_sync_wrap_softens_outside_root() -> None:
    mw = FilesystemGuardMiddleware()
    request = MagicMock()
    request.tool_call = {"name": "write_file", "id": "call_w", "args": {}}

    def boom(_req: Any) -> ToolMessage:
        raise ValueError("Path:/etc/passwd outside root directory: /workspace")

    out = mw.wrap_tool_call(request, boom)
    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert out.name == "write_file"


def test_rewrite_legacy_windows_path_suffix_under_root(tmp_path) -> None:
    target = tmp_path / "data" / "文章存稿" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")
    leftover = r"D:\octop-data\data\文章存稿\x.md"
    assert rewrite_legacy_windows_fs_path(leftover, root_dir=tmp_path) == "/data/文章存稿/x.md"


def test_rewrite_legacy_windows_path_ignores_posix_and_relative() -> None:
    assert rewrite_legacy_windows_fs_path("/data/x.md", root_dir="/tmp") == "/data/x.md"
    assert rewrite_legacy_windows_fs_path("relative/x.md", root_dir="/tmp") == "relative/x.md"


@pytest.mark.asyncio
async def test_middleware_rewrites_leftover_windows_path_before_tool(tmp_path) -> None:
    target = tmp_path / "data" / "文章存稿" / "_核验与备选标题.md"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")
    mw = FilesystemGuardMiddleware(root_dir=tmp_path)
    request = MagicMock()
    request.tool_call = {
        "name": "read_file",
        "id": "call_1",
        "args": {"file_path": r"D:\octop-data\data\文章存稿\_核验与备选标题.md"},
    }
    request.override = None
    seen: dict[str, str] = {}

    async def handler(req: Any) -> ToolMessage:
        seen["path"] = req.tool_call["args"]["file_path"]
        return ToolMessage(content="ok", name="read_file", tool_call_id="call_1")

    out = await mw.awrap_tool_call(request, handler)
    assert isinstance(out, ToolMessage)
    assert seen["path"] == "/data/文章存稿/_核验与备选标题.md"


@pytest.mark.asyncio
async def test_windows_path_rewrite_logs_once_at_debug(tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    target = tmp_path / "data" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")
    mw = FilesystemGuardMiddleware(root_dir=tmp_path)
    path = r"D:\octop-data\data\x.md"

    def _request() -> MagicMock:
        request = MagicMock()
        request.tool_call = {"name": "read_file", "id": "call_1", "args": {"file_path": path}}
        request.override = None
        return request

    async def handler(req: Any) -> ToolMessage:
        return ToolMessage(content="ok", name="read_file", tool_call_id="call_1")

    with caplog.at_level(logging.DEBUG, logger="octop_harness.middleware.filesystem_guard"):
        await mw.awrap_tool_call(_request(), handler)
        await mw.awrap_tool_call(_request(), handler)
    logged = [rec for rec in caplog.records if "rewrote leftover Windows path" in rec.message]
    assert len(logged) == 1
    assert logged[0].levelno == logging.DEBUG
