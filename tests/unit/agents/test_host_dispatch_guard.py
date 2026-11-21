"""Team hosts keep only dispatch tools, even when the prompt mentions files."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import SystemMessage

from octop.infra.agents.middleware.host_dispatch_guard import HostDispatchGuardMiddleware


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Request:
    def __init__(self) -> None:
        self.tools: list[Any] = [
            _Tool("write_file"),
            _Tool("write_todos"),
            _Tool("execute"),
            _Tool("ask_agent"),
            _Tool("send_file_to_user"),
        ]
        self.system_message = SystemMessage(content="use write_file")

    def override(self, *, tools: list[Any], system_message: SystemMessage) -> _Request:
        nxt = _Request()
        nxt.tools = tools
        nxt.system_message = system_message
        return nxt


def test_model_request_drops_file_tools_and_states_the_boundary() -> None:
    mw = HostDispatchGuardMiddleware(locale="zh")
    updated = mw._apply(_Request())
    assert [tool.name for tool in updated.tools] == ["ask_agent", "send_file_to_user"]
    text = str(updated.system_message.content)
    assert "主持人工具边界" in text
    assert "write_file" in text


@pytest.mark.asyncio
async def test_disallowed_tool_call_is_rejected() -> None:
    mw = HostDispatchGuardMiddleware(locale="en")

    async def handler(_request: Any) -> str:
        raise AssertionError("write_file must not run")

    request = type(
        "Call",
        (),
        {"tool_call": {"name": "write_file", "id": "c1", "args": {}}},
    )()
    message = await mw.awrap_tool_call(request, handler)
    assert message.status == "error"
    assert "ask a member" in message.content


@pytest.mark.asyncio
async def test_send_file_still_runs() -> None:
    mw = HostDispatchGuardMiddleware(locale="en")
    seen: list[str] = []

    async def handler(request: Any) -> str:
        seen.append(request.tool_call["name"])
        return "sent"

    request = type(
        "Call",
        (),
        {"tool_call": {"name": "send_file_to_user", "id": "c2", "args": {}}},
    )()
    assert await mw.awrap_tool_call(request, handler) == "sent"
    assert seen == ["send_file_to_user"]
