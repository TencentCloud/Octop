"""Exercise the installed filesystem mutation guard through the real harness graph."""

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from octop_harness import HarnessAgent, HarnessAgentConfig, ModelConfig, ProviderConfig


class ToolCallingModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "ToolCallingModel":
        return self


def edit_call(call_id: str, path: str, old: str, new: str) -> dict[str, Any]:
    return {
        "name": "edit_file",
        "id": call_id,
        "type": "tool_call",
        "args": {"file_path": path, "old_string": old, "new_string": new},
    }


def make_agent(
    workspace: Path, replies: list[AIMessage], monkeypatch: pytest.MonkeyPatch, backend_kind: str
) -> HarnessAgent:
    model = ToolCallingModel(messages=iter(replies))
    monkeypatch.setattr(
        "octop_harness.llm.factory.ChatModelFactory.get_chat_model", lambda *args, **kwargs: model
    )
    monkeypatch.setenv("OCTOP_HOME", str(workspace.parent / "home"))
    return HarnessAgent(
        HarnessAgentConfig(
            workspace_dir=workspace,
            log_dir=workspace.parent / "logs",
            backend={"type": backend_kind, "root_dir": str(workspace), "virtual_mode": True},
            providers=[
                ProviderConfig(
                    id="test",
                    base_url="https://example.invalid/v1",
                    api_key="test-key",
                    models=[ModelConfig(id="fake")],
                )
            ],
            default_model="test/fake",
            memory_enabled=False,
            checkpointer=False,
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_kind", ["filesystem", "local_shell"])
async def test_same_path_mutation_is_rejected_then_can_retry_next_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend_kind: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report = workspace / "report.md"
    report.write_text("A=旧\nB=旧\n", encoding="utf-8")
    agent = make_agent(
        workspace,
        [
            AIMessage(
                content="",
                tool_calls=[
                    edit_call("first", "/report.md", "A=旧", "A=新"),
                    edit_call("parallel", "/./report.md", "B=旧", "B=新"),
                ],
            ),
            AIMessage(content="", tool_calls=[edit_call("retry", "/report.md", "B=旧", "B=新")]),
            AIMessage(content="完成"),
        ],
        monkeypatch,
        backend_kind,
    )
    try:
        payload = {"messages": [HumanMessage(content="修改两个段落")]}
        result = await agent.graph.ainvoke(payload)
        edits = [
            m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "edit_file"
        ]
        assert [m.status for m in edits] == ["success", "error", "success"]
        assert "parallel" in str(edits[1].content).lower()
        assert report.read_text(encoding="utf-8") == "A=新\nB=新\n"
    finally:
        await agent.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_kind", ["filesystem", "local_shell"])
async def test_different_file_mutations_remain_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend_kind: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("left.md", "right.md"):
        (workspace / name).write_text("旧内容", encoding="utf-8")
    agent = make_agent(
        workspace,
        [
            AIMessage(
                content="",
                tool_calls=[
                    edit_call("left", "/left.md", "旧内容", "左侧新内容"),
                    edit_call("right", "/right.md", "旧内容", "右侧新内容"),
                ],
            ),
            AIMessage(content="完成"),
        ],
        monkeypatch,
        backend_kind,
    )
    try:
        payload = {"messages": [HumanMessage(content="修改两个文件")]}
        result = await agent.graph.ainvoke(payload)
        edits = [
            m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "edit_file"
        ]
        assert [m.status for m in edits] == ["success", "success"]
        assert (workspace / "left.md").read_text(encoding="utf-8") == "左侧新内容"
        assert (workspace / "right.md").read_text(encoding="utf-8") == "右侧新内容"
    finally:
        await agent.aclose()
