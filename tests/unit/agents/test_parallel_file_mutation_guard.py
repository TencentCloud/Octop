"""Regression test for same-file parallel edit protection (issue #1519).

deepagents >= 0.7.16 ships the upstream fix (langchain-ai/deepagents#6446):
later file mutations to the same path in one model response are rejected
with a ``ToolMessage(status="error")`` instead of silently overwriting the
earlier edit. Octop pins that floor in ``pyproject.toml``; this test fails
loudly if a future dependency change resolves below it.
"""

from __future__ import annotations

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage


def _request(tool_call: dict, messages: list) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call=tool_call,
        tool=None,
        state={"messages": messages},
        runtime=None,
    )


def _handler(seen: list[str]):
    async def handler(request: ToolCallRequest) -> ToolMessage:
        seen.append(request.tool_call["id"])
        return ToolMessage(content="ok", tool_call_id=request.tool_call["id"])

    return handler


async def test_second_same_path_edit_is_rejected(tmp_path) -> None:
    middleware = FilesystemMiddleware(backend=FilesystemBackend(root_dir=str(tmp_path)))
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-1",
                "name": "edit_file",
                "args": {
                    "file_path": "/report.md",
                    "old_string": "A",
                    "new_string": "A2",
                },
            },
            {
                "id": "call-2",
                "name": "edit_file",
                "args": {
                    "file_path": "/report.md",
                    "old_string": "B",
                    "new_string": "B2",
                },
            },
        ],
    )
    seen: list[str] = []

    first = await middleware.awrap_tool_call(
        _request(ai_message.tool_calls[0], [ai_message]), _handler(seen)
    )
    second = await middleware.awrap_tool_call(
        _request(ai_message.tool_calls[1], [ai_message]), _handler(seen)
    )

    assert first.status != "error"
    assert seen == ["call-1"]  # the second edit never reached the backend
    assert second.status == "error"
    assert "parallel file mutations" in second.content


async def test_different_paths_still_run_in_parallel(tmp_path) -> None:
    middleware = FilesystemMiddleware(backend=FilesystemBackend(root_dir=str(tmp_path)))
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-1",
                "name": "edit_file",
                "args": {
                    "file_path": "/a.md",
                    "old_string": "A",
                    "new_string": "A2",
                },
            },
            {
                "id": "call-2",
                "name": "edit_file",
                "args": {
                    "file_path": "/b.md",
                    "old_string": "B",
                    "new_string": "B2",
                },
            },
        ],
    )
    seen: list[str] = []

    for tool_call in ai_message.tool_calls:
        result = await middleware.awrap_tool_call(_request(tool_call, [ai_message]), _handler(seen))
        assert result.status != "error"

    assert seen == ["call-1", "call-2"]  # both edits run, no serialization
