"""Strong memory is snapshotted per session and cannot be edited by file tools."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.memory import MemoryMiddleware
from langchain.agents.middleware import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from octop_memory import Memory, MemoryService

from octop_harness.backends.workspace import DEFAULT_MEMORY_FILES, BackendWorkspace
from octop_harness.builtin.templates import iter_md_template_files
from octop_harness.builtin.tools.memory_tools import build_memory_tools
from octop_harness.middleware.filesystem_guard import FilesystemGuardMiddleware
from octop_harness.middleware.memory import MemoryMiddleware as CaptureMemoryMiddleware


class RecordingModel(FakeMessagesListChatModel):
    requests: list[Any] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
        self.requests.append(deepcopy(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _workspace(tmp_path: Path, prefix: str = "") -> BackendWorkspace:
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    return BackendWorkspace(backend, tmp_path, system_files_path=prefix)


def _loader(ws: BackendWorkspace, memory_files: Sequence[str] = DEFAULT_MEMORY_FILES) -> MemoryMiddleware[Any, Any]:
    return MemoryMiddleware(
        backend=ws.backend,
        sources=ws.memory_paths(memory_files, include_missing=True),
        system_prompt="<agent_memory>\n{agent_memory}\n</agent_memory>",
        add_cache_control=True,
    )


@pytest.mark.parametrize("prefix", ["", ".octop"])
def test_session_keeps_snapshot_after_edits_and_deletion(tmp_path: Path, prefix: str) -> None:
    ws = _workspace(tmp_path, prefix)
    ws.write_text("MEMORY.md", "original strong memory", force=True)
    mw = _loader(ws)
    first = mw.before_agent({}, MagicMock(), {})
    assert first is not None
    ws.write_text("MEMORY.md", "updated strong memory", force=True)
    with patch.object(ws.backend, "download_files", side_effect=AssertionError("session must reuse its snapshot")):
        assert mw.before_agent(first, MagicMock(), {}) is None
    assert list(first["memory_contents"].values()) == ["original strong memory"]
    new_session = mw.before_agent({}, MagicMock(), {})
    assert new_session is not None
    assert list(new_session["memory_contents"].values()) == ["updated strong memory"]
    ws.delete("MEMORY.md")
    with patch.object(ws.backend, "download_files", side_effect=AssertionError("session must reuse its snapshot")):
        assert mw.before_agent(first, MagicMock(), {}) is None
    assert mw.before_agent({}, MagicMock(), {}) == {"memory_contents": {}}


@pytest.mark.asyncio
async def test_empty_session_snapshot_stays_empty_until_a_new_session(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    mw = _loader(ws, memory_files=("MEMORY.md",))
    first = await mw.abefore_agent({}, MagicMock(), {})
    assert first == {"memory_contents": {}}
    content = "用户手动维护的强记忆\n" * 1000
    ws.write_text("MEMORY.md", content, force=True)
    ws.write_text("AGENTS.md", "bootstrap instructions", force=True)
    with patch.object(ws.backend, "adownload_files", side_effect=AssertionError("empty snapshot is still initialized")):
        assert await mw.abefore_agent(first, MagicMock(), {}) is None
    loaded = await mw.abefore_agent({}, MagicMock(), {})
    assert loaded is not None
    assert list(loaded["memory_contents"].values()) == [content]
    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="hi")],
        state=loaded,
        runtime=MagicMock(),
    )
    system = mw.modify_request(request).system_message
    assert system is not None
    text = "\n".join(str(block.get("text", "")) for block in system.content_blocks if isinstance(block, dict))
    assert content.rstrip() in text
    assert "<memory_guidelines>" not in str(system.content)
    assert "As you learn from your interactions" not in str(system.content)


@pytest.mark.parametrize("tool_name", ["write_file", "edit_file", "append_file", "delete"])
@pytest.mark.parametrize("path", ["MEMORY.md", "/MEMORY.md", "native"])
@pytest.mark.parametrize("filename", ["MEMORY.md", "USER.md"])
def test_file_tools_cannot_change_strong_memory(tmp_path: Path, tool_name: str, path: str, filename: str) -> None:
    ws = _workspace(tmp_path, ".octop")
    mw = FilesystemGuardMiddleware(workspace=ws)
    path = ws.resolve_path(filename) if path == "native" else path.replace("MEMORY.md", filename)
    request = MagicMock(tool_call={"name": tool_name, "args": {"file_path": path}, "id": "call-1"})
    handler = MagicMock()
    result = mw.wrap_tool_call(request, handler)
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "memory_save" in str(result.content)
    assert filename in str(result.content)
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_async_guard_allows_normal_workspace_edits(tmp_path: Path) -> None:
    mw = FilesystemGuardMiddleware(workspace=_workspace(tmp_path))
    request = MagicMock(tool_call={"name": "edit_file", "args": {"file_path": "notes.md"}, "id": "call-1"})
    calls: list[Any] = []

    async def handler(value: Any) -> ToolMessage:
        calls.append(value)
        return ToolMessage(content="edited", tool_call_id="call-1")

    assert (await mw.awrap_tool_call(request, handler)).content == "edited"
    assert calls == [request]


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["MEMORY.md", "USER.md"])
async def test_graph_blocks_manual_document_edits_and_allows_normal_files(tmp_path: Path, filename: str) -> None:
    ws = _workspace(tmp_path, ".octop")
    ws.write_text(filename, "manual agreement", force=True)
    ws.write_text("notes.md", "old note", force=True)
    model = RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "edit_file",
                        "args": {"file_path": f"/{filename}", "old_string": "manual", "new_string": "agent"},
                        "id": "protected-edit",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "edit_file",
                        "args": {"file_path": "/notes.md", "old_string": "old", "new_string": "new"},
                        "id": "normal-edit",
                    }
                ],
            ),
            AIMessage(content="Done"),
        ]
    )
    loader = _loader(ws)
    graph = create_deep_agent(
        model=model,
        backend=ws.backend,
        memory=loader.sources,
        middleware=[loader, FilesystemGuardMiddleware(workspace=ws)],
    )
    result = await graph.ainvoke({"messages": [HumanMessage(content="Edit both files")]})
    tools = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
    assert [(msg.tool_call_id, msg.status) for msg in tools] == [
        ("protected-edit", "error"),
        ("normal-edit", "success"),
    ]
    assert "user-maintained memory" in str(tools[0].content)
    assert ws.read_text(filename) == "manual agreement"
    assert ws.read_text("notes.md") == "new note"


@pytest.mark.asyncio
@pytest.mark.parametrize("async_mode", [False, True])
async def test_graph_preserves_session_snapshot_across_turns_and_graph_recreation(
    tmp_path: Path, async_mode: bool
) -> None:
    ws = _workspace(tmp_path)
    agents = dict(iter_md_template_files("en"))["AGENTS.md"].decode("utf-8")
    ws.write_text("AGENTS.md", agents, force=True)
    ws.write_text("MEMORY.md", "first manual agreement", force=True)
    memory = Memory(namespace="strong_test", backend_config={"db_path": str(tmp_path / "memory.sqlite")})
    service = MemoryService(memory)
    model = RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "memory_save",
                        "args": {"content": "Aurora uses PostgreSQL"},
                        "id": "save-1",
                    }
                ],
            ),
            AIMessage(content="Saved"),
            AIMessage(content="Continued the same session"),
            AIMessage(content="Restored the same session"),
            AIMessage(content="Started a new session"),
            AIMessage(content="Started a session after deletion"),
            AIMessage(content="Continued the original session after deletion"),
        ]
    )
    checkpointer = InMemorySaver()

    def make_graph() -> Any:
        loader = _loader(ws)
        return create_deep_agent(
            model=model,
            backend=ws.backend,
            tools=build_memory_tools(service),
            memory=loader.sources,
            middleware=[loader, FilesystemGuardMiddleware(workspace=ws)],
            checkpointer=checkpointer,
        )

    async def invoke(graph: Any, text: str, config: Any) -> Any:
        data = {"messages": [HumanMessage(content=text)]}
        return await graph.ainvoke(data, config=config) if async_mode else graph.invoke(data, config=config)

    download = "adownload_files" if async_mode else "download_files"
    graph = make_graph()
    config = {"configurable": {"thread_id": "strong-memory-test"}}
    await invoke(graph, "Remember Aurora uses PostgreSQL", config)
    assert memory.search_atoms("PostgreSQL")
    assert ws.read_text("MEMORY.md") == "first manual agreement"
    first_system = model.requests[-1][0].content
    assert str(first_system).count("<agent_memory>") == 1
    first_text = "\n".join(
        str(block.get("text", "")) for block in model.requests[-1][0].content_blocks if isinstance(block, dict)
    )
    assert agents.rstrip() in first_text
    ws.write_text("MEMORY.md", "second manual agreement", force=True)
    with patch.object(ws.backend, download, side_effect=AssertionError("no per-turn file read")):
        await invoke(graph, "Continue", config)
    assert model.requests[-1][0].content == first_system

    restored = make_graph()
    with patch.object(ws.backend, download, side_effect=AssertionError("restore uses checkpoint")):
        await invoke(restored, "Continue after restart", config)
    assert model.requests[-1][0].content == first_system

    await invoke(
        restored,
        "New session",
        {"configurable": {"thread_id": "new-strong-memory-session"}},
    )
    new_system = model.requests[-1][0].content
    assert "second manual agreement" in str(new_system)
    assert "first manual agreement" not in str(new_system)
    assert "Use `memory_save` for remember requests" in str(new_system)
    assert "As you learn from your interactions" not in str(new_system)

    ws.delete("MEMORY.md")
    restored = make_graph()
    await invoke(
        restored,
        "Another new session",
        {"configurable": {"thread_id": "empty-strong-memory-session"}},
    )
    assert "second manual agreement" not in str(model.requests[-1][0].content)
    with patch.object(ws.backend, download, side_effect=AssertionError("other sessions do not change snapshots")):
        await invoke(restored, "Return to the original session", config)
    assert model.requests[-1][0].content == first_system


@pytest.mark.asyncio
async def test_profile_snapshot_deduplicates_recall_without_reloading_files(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    fact = "Aurora uses PostgreSQL."
    ws.write_text("USER.md", fact, force=True)
    memory = Memory(namespace="profile_snapshot", backend_config={"db_path": str(tmp_path / "memory.sqlite")})
    memory.store(fact)
    capture = CaptureMemoryMiddleware(service=MemoryService(memory), jsonl_enabled=False, capture_enabled=False)
    model = RecordingModel(responses=[AIMessage(content="one"), AIMessage(content="two"), AIMessage(content="new")])
    loader = _loader(ws)
    graph = create_deep_agent(
        model=model,
        backend=ws.backend,
        memory=loader.sources,
        middleware=[loader, capture, FilesystemGuardMiddleware(workspace=ws)],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "profile-session"}}
    await graph.ainvoke({"messages": [HumanMessage(content="PostgreSQL")]}, config=config)
    assert "<memory-context>" not in str(model.requests[-1][-1].content)
    ws.write_text("USER.md", "A different profile", force=True)
    with patch.object(ws.backend, "adownload_files", side_effect=AssertionError("session snapshot must not reload")):
        await graph.ainvoke({"messages": [HumanMessage(content="PostgreSQL")]}, config=config)
    assert "<memory-context>" not in str(model.requests[-1][-1].content)
    await graph.ainvoke(
        {"messages": [HumanMessage(content="PostgreSQL")]},
        config={"configurable": {"thread_id": "new-profile-session"}},
    )
    assert fact in str(model.requests[-1][-1].content)
    assert "<memory-context>" in str(model.requests[-1][-1].content)
    capture.shutdown()
