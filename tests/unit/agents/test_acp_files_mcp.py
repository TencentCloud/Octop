"""Managed runners deliver files through the send_file_to_user loopback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.agents.acp.files_mcp import (
    file_scope,
    handle_files_mcp,
    retain_file_scope,
)


class _Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def materialize_local(self, path: str) -> Path:
        return self.root / path


def test_file_token_is_stable_per_expert() -> None:
    assert retain_file_scope("GWN") == retain_file_scope("GWN")
    assert file_scope(retain_file_scope("GWN")) is not None


@pytest.mark.asyncio
async def test_send_file_returns_the_native_media_block(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_text("hello", encoding="utf-8")
    listed = await handle_files_mcp(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, workspace=_Workspace(tmp_path)
    )
    tools = listed["result"]["tools"]
    assert [item["name"] for item in tools] == ["send_file_to_user"]

    result = await handle_files_mcp(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "send_file_to_user", "arguments": {"file_path": "report.txt"}},
        },
        workspace=_Workspace(tmp_path),
    )
    content = result["result"]["content"]
    assert result["result"]["isError"] is False
    block = json.loads(content[0]["text"])
    assert block["octop_delivery"] == "send_file_to_user"
    assert block["path"] == "report.txt"
    assert block["source"]["url"].startswith("file:")


@pytest.mark.asyncio
async def test_missing_file_is_an_error(tmp_path: Path) -> None:
    result = await handle_files_mcp(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "send_file_to_user", "arguments": {"file_path": "missing.txt"}},
        },
        workspace=_Workspace(tmp_path),
    )
    assert result["result"]["isError"] is True
    assert "missing.txt" in result["result"]["content"][0]["text"]
