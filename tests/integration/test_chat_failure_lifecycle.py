"""Raised model failures survive UI reload without becoming checkpoint replies or memory."""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from tests.support.app import octop_client
from tests.support.auth import auth_header, bootstrap_admin, create_agent, seed_openai_provider
from tests.support.fault_graph import FaultGraph
from tests.support.http import chat_ws_path, ws_connect


@pytest.mark.parametrize("mode", ["auth", "timeout"])
@pytest.mark.parametrize("partial", [False, True])
async def test_failed_turn_survives_reload_releases_running_state_and_has_no_error_memory(
    tmp_octop_home: Any, mode: str, partial: bool
) -> None:
    async with octop_client(tmp_octop_home) as (client, server):
        await bootstrap_admin(client, tmp_octop_home)
        auth = await auth_header(client)
        await seed_openai_provider(client, auth)
        agent_id = await create_agent(client, auth)
        agent = server.app_runtime.agent_registry.get_agent(agent_id)
        fault = FaultGraph(agent, tmp_octop_home / "fault-memory")
        fault.model.mode, fault.partial = mode, partial
        try:
            created = await client.post(f"/api/agents/{agent_id}/threads", headers=auth)
            thread_id = created.json()["thread_id"]
            async with ws_connect(client._octop_app, chat_ws_path(agent_id, auth)) as ws:
                await ws.send_json(
                    {"type": "user_turn", "text": "这是隔离的模拟故障测试", "thread_id": thread_id}
                )
                frames = await ws.drain_turn()
                frames.append(await ws.receive_json())
            assert any(frame.get("type") == "error" for frame in frames)
            error = next(frame["message"] for frame in frames if frame.get("type") == "error")
            assert frames[-1]["type"] == "done"
            state = await fault.graph.aget_state({"configurable": {"thread_id": thread_id}})
            assert any(task.error for task in state.tasks)
            assert not any(isinstance(message, AIMessage) for message in state.values["messages"])
            assert fault.memory.list_raw() == []
            assert fault.memory.list_atoms() == []
            assert fault.memory.list_candidates() == []
            for _ in range(2):  # Repeated history reads model browser refresh/reconnect.
                response = await client.get(
                    f"/api/agents/{agent_id}/threads/{thread_id}/history", headers=auth
                )
                response.raise_for_status()
                body = response.json()
                errors = [
                    message for message in body["messages"] if message.get("status") == "error"
                ]
                assert len(errors) == 1
                assert error in json.dumps(errors[0], ensure_ascii=False)
            async with ws_connect(client._octop_app, chat_ws_path(agent_id, auth)) as ws:
                await ws.send_json({"type": "subscribe", "thread_id": thread_id})
                status = await ws.receive_json()
                assert status == {"type": "turn_status", "thread_id": thread_id, "active": False}
            fault.model.mode, fault.partial = "ok", False
            async with ws_connect(client._octop_app, chat_ws_path(agent_id, auth)) as ws:
                await ws.send_json(
                    {"type": "user_turn", "text": "模拟修复后再次请求", "thread_id": thread_id}
                )
                recovered = await ws.drain_turn()
            assert not any(frame.get("type") == "error" for frame in recovered)
            assert any("本轮回复成功" in frame.get("content", "") for frame in recovered)
        finally:
            fault.close()
