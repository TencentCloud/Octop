"""Real graph/checkpoint/memory with a model that raises deterministic test faults."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.exceptions import ModelAuthenticationError
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from octop_harness.middleware.memory import MemoryMiddleware
from octop_harness.middleware.model_retry import ModelRetryMiddleware
from octop_harness.request import ChatRequest
from octop_memory import Memory, MemoryService


class FaultModel(FakeMessagesListChatModel):
    mode: str = "auth"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Any:
        if self.mode == "auth":
            raise ModelAuthenticationError("simulated provider authentication failure")
        if self.mode == "timeout":
            raise TimeoutError("simulated provider request timed out")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Any:
        return self._generate(messages, stop, run_manager, **kwargs)


class FaultGraph:
    """Attach to an existing host fake; no real provider or IM connection exists."""

    def __init__(self, agent: Any, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.memory = Memory(
            namespace="fault_verification",
            backend_config={"db_path": str(directory / "memory.sqlite")},
        )
        service = MemoryService(self.memory, config={"capture": {"min_message_chars": 0}})
        self.middleware = MemoryMiddleware(service=service, jsonl_enabled=False)
        self.model = FaultModel(responses=[AIMessage(content="模拟故障已解除，本轮回复成功。")])
        self.graph = create_deep_agent(
            model=self.model,
            middleware=[ModelRetryMiddleware(max_retries=0, on_failure="error"), self.middleware],
            backend=FilesystemBackend(root_dir=str(directory), virtual_mode=True),
            checkpointer=InMemorySaver(),
        )
        self.partial = False
        self.last_config: dict[str, Any] = {}
        agent.graph = self.graph
        agent.stream = self.stream
        agent.aget_history = self.history

    async def stream(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        prepared = ChatRequest.coerce(request)
        self.last_config = prepared.to_runnable_config()
        if self.partial:
            yield {"type": "token", "content": "模拟的部分输出，随后发生故障。"}
        result = await self.graph.ainvoke(
            {"messages": prepared.normalize_messages()}, self.last_config
        )
        yield {"type": "token", "content": str(result["messages"][-1].content)}
        yield {"type": "state_snapshot", "data": {"messages": result["messages"]}}

    async def history(
        self, thread_id: str, *, limit: int = 50, before: str | None = None
    ) -> list[Any]:
        state = await self.graph.aget_state({"configurable": {"thread_id": thread_id}})
        return list(state.values.get("messages", []))[-limit:]

    def close(self) -> None:
        self.middleware.shutdown()
        self.memory.backend.close()
