"""End-to-end protocol checks for the external Octop Agent MCP Gateway."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from octop.infra.gateway.threads import ThreadRegistry


def _rpc(
    method: str, *, request_id: int = 1, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


@pytest.mark.asyncio
async def test_agent_mcp_requires_authentication(
    env_with_agent: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, _server, _auth, _agent_id = env_with_agent
    response = await client.post("/api/mcp/agents", json=_rpc("tools/list"))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_mcp_initializes_and_lists_tools(
    env_with_agent: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, _server, auth, _agent_id = env_with_agent
    initialized = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "initialize",
            params={
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        ),
    )
    assert initialized.status_code == 200
    assert initialized.headers["mcp-session-id"]
    assert initialized.json()["result"]["protocolVersion"] == "2025-03-26"

    listed = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc("tools/list", request_id=2),
    )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names == {
        "list_octop_experts",
        "call_octop_expert",
        "resume_octop_expert",
    }


@pytest.mark.asyncio
async def test_agent_mcp_calls_expert_and_continues_only_its_own_thread(
    env_with_agent: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, server, auth, agent_id = env_with_agent
    runtime_agent = server.app_runtime.agent_registry.get_agent(agent_id)
    runtime_agent.chunks = [{"type": "token", "content": "first answer"}]

    listed = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            params={"name": "list_octop_experts", "arguments": {}},
        ),
    )
    experts = listed.json()["result"]["structuredContent"]["experts"]
    assert any(item["expert_id"] == agent_id for item in experts)

    called = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            request_id=2,
            params={
                "name": "call_octop_expert",
                "arguments": {"expert_id": agent_id, "message": "do the task"},
            },
        ),
    )
    first = called.json()["result"]["structuredContent"]
    assert first["status"] == "completed"
    assert first["response"] == "first answer"
    thread_id = first["thread_id"]
    thread = server.app_runtime.gateway.thread_registry.get_thread(thread_id)
    assert thread is not None
    assert thread.channel_type == ThreadRegistry.CHANNEL_MCP

    runtime_agent.chunks = [{"type": "token", "content": "second answer"}]
    continued = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            request_id=3,
            params={
                "name": "call_octop_expert",
                "arguments": {
                    "expert_id": agent_id,
                    "message": "continue",
                    "thread_id": thread_id,
                },
            },
        ),
    )
    second = continued.json()["result"]["structuredContent"]
    assert second["status"] == "completed"
    assert second["thread_id"] == thread_id
    assert second["response"] == "second answer"

    registry = server.app_runtime.gateway.thread_registry
    dashboard_key = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=thread.user_id)
    dashboard_thread = await registry.get_or_create_by_key(
        session_key=dashboard_key,
        agent_id=agent_id,
        user_id=thread.user_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
    )
    rejected = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            request_id=4,
            params={
                "name": "call_octop_expert",
                "arguments": {
                    "expert_id": agent_id,
                    "message": "take over the dashboard",
                    "thread_id": dashboard_thread,
                },
            },
        ),
    )
    result = rejected.json()["result"]
    assert result["isError"] is True
    assert "only MCP-created threads" in result["structuredContent"]["error"]


@pytest.mark.asyncio
async def test_agent_mcp_hitl_lifecycle_and_followup_approval(
    env_with_agent: tuple[httpx.AsyncClient, Any, dict[str, str], str],
) -> None:
    client, server, auth, agent_id = env_with_agent
    runtime_agent = server.app_runtime.agent_registry.get_agent(agent_id)
    runtime_agent.chunks = [
        {
            "type": "hitl_required",
            "request": {
                "action_requests": [
                    {"name": "execute", "args": {"command": "echo first"}},
                ],
                "review_configs": [
                    {
                        "action_name": "execute",
                        "allowed_decisions": ["approve", "reject"],
                    },
                ],
            },
        },
    ]
    called = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            params={
                "name": "call_octop_expert",
                "arguments": {"expert_id": agent_id, "message": "request approval"},
            },
        ),
    )
    first = called.json()["result"]["structuredContent"]
    assert first["status"] == "approval_required"
    assert first["approval"]["pending_id"]
    assert first["approval"]["request"]["pending_id"] == first["approval"]["pending_id"]
    thread_id = first["thread_id"]
    first_pending_id = first["approval"]["pending_id"]

    resume_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def _resume_with_followup(
        resumed_thread_id: str,
        decisions: list[dict[str, Any]],
    ) -> Any:
        resume_calls.append((resumed_thread_id, decisions))
        yield {"type": "token", "content": "first approved"}
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [
                    {
                        "name": "ask_user_question",
                        "args": {"questions": [{"question": "Which target?"}]},
                    },
                ],
                "review_configs": [
                    {
                        "action_name": "ask_user_question",
                        "allowed_decisions": ["respond"],
                    },
                ],
            },
        }

    runtime_agent.resume_hitl = _resume_with_followup
    rejected = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            request_id=2,
            params={
                "name": "resume_octop_expert",
                "arguments": {
                    "expert_id": agent_id,
                    "thread_id": thread_id,
                    "decisions": [
                        {"type": "edit", "edited_action": {"name": "execute"}},
                    ],
                },
            },
        ),
    )
    rejected_result = rejected.json()["result"]
    assert rejected_result["isError"] is True
    assert "is not allowed" in rejected_result["structuredContent"]["error"]
    assert resume_calls == []

    resumed = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            request_id=3,
            params={
                "name": "resume_octop_expert",
                "arguments": {
                    "expert_id": agent_id,
                    "thread_id": thread_id,
                    "decisions": [{"type": "approve"}],
                },
            },
        ),
    )
    followup = resumed.json()["result"]["structuredContent"]
    assert followup["status"] == "approval_required"
    assert followup["response"] == "first approved"
    second_pending_id = followup["approval"]["pending_id"]
    assert second_pending_id
    assert second_pending_id != first_pending_id
    assert resume_calls == [(thread_id, [{"type": "approve"}])]

    hitl_store = server.app_runtime.gateway.processor.hitl_coordinator.store
    assert hitl_store.get(first_pending_id).status == "approved"
    thread = server.app_runtime.gateway.thread_registry.get_thread(thread_id)
    assert thread is not None
    second_pending = hitl_store.resolve_pending_for_thread(
        thread_id,
        agent_id=agent_id,
        user_id=thread.user_id,
    )
    assert second_pending is not None
    assert second_pending.pending_id == second_pending_id

    async def _resume_with_answer(
        resumed_thread_id: str,
        decisions: list[dict[str, Any]],
    ) -> Any:
        resume_calls.append((resumed_thread_id, decisions))
        yield {"type": "token", "content": "finished"}

    runtime_agent.resume_hitl = _resume_with_answer
    answered = await client.post(
        "/api/mcp/agents",
        headers=auth,
        json=_rpc(
            "tools/call",
            request_id=4,
            params={
                "name": "resume_octop_expert",
                "arguments": {
                    "expert_id": agent_id,
                    "thread_id": thread_id,
                    "decisions": [{"type": "respond", "message": "staging"}],
                },
            },
        ),
    )
    final = answered.json()["result"]["structuredContent"]
    assert final["status"] == "completed"
    assert final["response"] == "finished"
    assert hitl_store.get(second_pending_id).status == "approved"
