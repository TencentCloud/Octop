"""The loopback knowledge MCP speaks search_knowledge."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.knowledge.mcp_gateway import handle_knowledge_mcp


@pytest.mark.asyncio
async def test_lists_and_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_retrieve(*args: Any, **kwargs: Any) -> str:
        assert kwargs["knowledge_base_ids"] == ["kb1"]
        assert kwargs["query"] == "部署"
        return "passage"

    monkeypatch.setattr("octop.infra.knowledge.mcp_gateway.retrieve_context", fake_retrieve)
    listed = await handle_knowledge_mcp(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        user_id=1,
        is_admin=False,
        knowledge_base_ids=["kb1"],
        locale="zh",
        catalog=[{"id": "kb1", "name": "手册", "description": "安装"}],
        services=object(),
    )
    tool = listed["result"]["tools"][0]
    assert tool["name"] == "search_knowledge"
    assert "手册" in tool["description"]

    called = await handle_knowledge_mcp(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "search_knowledge", "arguments": {"query": "部署"}},
        },
        user_id=1,
        is_admin=False,
        knowledge_base_ids=["kb1"],
        locale="zh",
        catalog=[],
        services=object(),
    )
    assert called["result"]["content"][0]["text"] == "passage"
    assert called["result"]["isError"] is False
