"""Protocol dispatch tests for the Octop Agent MCP Gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.agent_mcp.protocol import handle_agent_mcp_request
from octop.infra.users.identity import User


@pytest.fixture
def user() -> User:
    return User(id=7, username="alice", role="user", display_name="Alice")


@pytest.mark.asyncio
async def test_resume_tool_dispatches_structured_decisions(user: User) -> None:
    service = MagicMock()
    service.resume_expert = AsyncMock(
        return_value={
            "status": "completed",
            "expert_id": "expert-1",
            "thread_id": "thr-1",
            "response": "done",
        }
    )
    response = await handle_agent_mcp_request(
        service=service,
        user=user,
        body={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "resume_octop_expert",
                "arguments": {
                    "expert_id": "expert-1",
                    "thread_id": "thr-1",
                    "decisions": [{"type": "approve"}],
                },
            },
        },
    )
    service.resume_expert.assert_awaited_once_with(
        user,
        expert_id="expert-1",
        thread_id="thr-1",
        decisions=[{"type": "approve"}],
    )
    assert response["result"]["structuredContent"]["response"] == "done"
    assert response["result"]["isError"] is False


@pytest.mark.asyncio
async def test_unknown_tool_is_a_tool_error(user: User) -> None:
    response = await handle_agent_mcp_request(
        service=MagicMock(),
        user=user,
        body={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "unknown", "arguments": {}},
        },
    )
    assert response["result"]["isError"] is True
    assert response["result"]["structuredContent"] == {"error": "unknown tool: unknown"}
