"""Recall must preserve model-visible prefixes across tools, checkpoints and turns."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware.types import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    message_to_dict,
    messages_from_dict,
)
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import StructuredTool
from langchain_openai.chat_models.base import _convert_message_to_dict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from octop_memory import Memory, MemoryService

from octop_harness.middleware.memory import MemoryMiddleware
from octop_harness.middleware.memory_recall import RECALL_SNAPSHOT_KEY, count_tokens_with_recall


class RecallService:
    def __init__(self, rendered: str = "deadline: Friday", *, fail: bool = False) -> None:
        self.rendered = rendered
        self.fail = fail
        self.queries: list[str] = []

    def recall(self, query: str, **kwargs: Any) -> Any:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("offline")
        return SimpleNamespace(rendered=self.rendered)


def middleware(service: Any, **kwargs: Any) -> MemoryMiddleware:
    return MemoryMiddleware(service=service, capture_enabled=False, jsonl_enabled=False, **kwargs)


def prepare(mw: MemoryMiddleware, messages: list[Any]) -> list[Any]:
    update = mw.before_model({"messages": messages}, None)
    return add_messages(messages, update["messages"]) if update else messages


def send(mw: MemoryMiddleware, messages: list[Any], system: SystemMessage | None = None) -> ModelRequest:
    request = ModelRequest(model=MagicMock(), messages=messages, system_message=system)
    return mw.wrap_model_call(request, lambda req: req)  # type: ignore[arg-type, return-value]


class RecordingModel(FakeMessagesListChatModel):
    wire_requests: list[list[dict[str, Any]]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> RecordingModel:
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any) -> Any:
        self.wire_requests.append(deepcopy([_convert_message_to_dict(m) for m in messages]))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_recall_changes_only_current_user_preserving_system_blocks() -> None:
    service = RecallService()
    mw = middleware(service)
    system = SystemMessage(content=[{"type": "text", "text": "Fixed", "cache_control": {"type": "ephemeral"}}])
    history = prepare(mw, [HumanMessage("deadline?", id="u1", additional_kwargs={"checkpoint_ts": 123})])
    first = send(mw, history, system)
    assert first.system_message == system
    assert history[0].content == "deadline?"
    assert first.messages[0].additional_kwargs == {"checkpoint_ts": 123}
    assert "deadline: Friday" in first.messages[0].content
    service.rendered = "deadline: Monday"
    second_history = prepare(mw, [*history, AIMessage("Friday", id="a1"), HumanMessage("deadline?", id="u2")])
    second = send(mw, second_history, system)
    assert second.system_message == first.system_message
    assert second.messages[0] == first.messages[0]
    assert "deadline: Monday" in second.messages[-1].content
    assert service.queries == ["deadline?", "deadline?"]


@pytest.mark.parametrize("mode", ["empty", "failure", "maintenance"])
def test_no_new_recall_during_retry_or_tool_continuation(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    service = RecallService("", fail=mode == "failure")
    mw = middleware(service)
    if mode == "maintenance":
        monkeypatch.setattr(mw, "_maintenance_blocks_io", lambda: True)
    history = prepare(mw, [HumanMessage("deadline?", id="u1")])
    first = send(mw, history)
    service.rendered, service.fail = "newly available memory", False
    monkeypatch.setattr(mw, "_maintenance_blocks_io", lambda: False)
    # Retry before an assistant response, then continue after tools.
    history = prepare(mw, history)
    assert send(mw, history).messages == first.messages
    history += [
        AIMessage("", tool_calls=[{"id": "t", "name": "lookup", "args": {}}]),
        ToolMessage("done", tool_call_id="t"),
    ]
    continued = send(mw, prepare(mw, history))
    assert continued.messages[0] == first.messages[0]
    assert service.queries == ([] if mode == "maintenance" else ["deadline?"])


def test_multimodal_replay_and_message_rewrite_do_not_restore_removed_content() -> None:
    service = RecallService()
    mw = middleware(service)
    blocks = [
        {"type": "text", "text": "deadline?"},
        {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
    ]
    history = prepare(mw, [HumanMessage(content=deepcopy(blocks), id="u1")])
    # Same message_to_dict / messages_from_dict path used by Octop archive/fork.
    restored = messages_from_dict([message_to_dict(m) for m in history])
    sent = send(mw, restored).messages[0]
    assert sent.content[:2] == blocks
    assert len(sent.content) == 3
    assert restored[0].content == blocks
    assert "image_url" not in restored[0].additional_kwargs[RECALL_SNAPSHOT_KEY]["suffix"]
    # A provider adapter mutating a nested block must not alter persisted input
    # or invalidate the original-content fingerprint on the next tool step.
    sent.content[1]["image_url"]["url"] = "https://example.com/normalized.png"
    assert restored[0].content == blocks
    assert send(mw, restored).messages[0].content[:2] == blocks
    rewritten = restored[0].model_copy(update={"content": "attachment removed"})
    assert send(mw, [rewritten]).messages[0].content == "attachment removed"
    assert RECALL_SNAPSHOT_KEY not in send(mw, [rewritten]).messages[0].additional_kwargs


def test_legacy_history_is_not_backfilled_and_disabling_recall_replays_old_snapshot() -> None:
    service = RecallService()
    mw = middleware(service)
    old = [HumanMessage("old", id="legacy"), AIMessage("answer")]
    history = prepare(mw, [*old, HumanMessage("new", id="new")])
    assert history[0] == old[0]
    sent = send(mw, history)
    disabled = middleware(None, recall_inject_enabled=False)
    assert send(disabled, prepare(disabled, history)).messages == sent.messages
    legacy_continuation = [*old, ToolMessage("done", tool_call_id="t")]
    assert prepare(mw, legacy_continuation) == legacy_continuation
    assert service.queries == ["new"]


def test_capture_and_jsonl_use_clean_content(tmp_path: Path) -> None:
    class CaptureService(RecallService):
        captured: list[dict[str, Any]] = []
        captured_event = threading.Event()

        def capture_turn(self, **kwargs: Any) -> dict[str, Any]:
            self.captured.append(kwargs)
            self.captured_event.set()
            return {}

    service = CaptureService()
    mw = MemoryMiddleware(service=service, jsonl_enabled=True, jsonl_dir=tmp_path)  # type: ignore[arg-type]
    model = RecordingModel(responses=[AIMessage("done")])
    graph = create_agent(model, middleware=[mw], checkpointer=InMemorySaver())
    graph.invoke({"messages": [HumanMessage("deadline?")]}, config={"configurable": {"thread_id": "capture"}})
    assert service.captured_event.wait(2)
    assert service.captured[0]["user"] == "deadline?"
    assert service.captured[0]["assistant"] == "done"
    rows = [json.loads(line) for path in tmp_path.glob("*.jsonl") for line in path.read_text().splitlines()]
    assert [row["content"] for row in rows] == ["deadline?", "done"]
    assert "deadline: Friday" in model.wire_requests[0][0]["content"]
    assert "deadline: Friday" not in str(rows)
    assert RECALL_SNAPSHOT_KEY not in str(rows)


def test_compaction_counts_recall_and_preserves_only_surviving_snapshots() -> None:
    from deepagents.middleware.summarization import SummarizationMiddleware

    service = RecallService("large memory " * 1000)
    mw = middleware(service)
    history = prepare(mw, [HumanMessage("first", id="u1")])
    history = prepare(mw, [*history, AIMessage("answer", id="a1"), HumanMessage("second", id="u2")])
    summarizer = SummarizationMiddleware(
        model=RecordingModel(responses=[AIMessage("summary")]),
        backend=MagicMock(),
        trigger=("tokens", 1000),
        keep=("messages", 1),
        token_counter=count_tokens_with_recall,
    )
    actual_count = summarizer._count_tokens(history, None, None)
    assert count_tokens_approximately(history) < 1000 < actual_count
    assert actual_count == count_tokens_approximately(send(mw, history).messages)
    assert summarizer._should_summarize(history, actual_count)
    # Real DeepAgents compaction event projection; trimmed memories cannot reappear.
    event = {
        "cutoff_index": 2,
        "summary_message": HumanMessage("summary", additional_kwargs={"lc_source": "summarization"}),
        "file_path": None,
    }
    projected = summarizer._apply_event_to_messages(history, event)
    sent = send(mw, projected).messages
    assert sent[0].content == "summary"
    assert sent[-1] == send(mw, history).messages[-1]
    assert len(sent) == 2
    assert service.queries == ["first", "second"]


def test_harness_wires_recall_budget_into_auto_and_manual_compaction(tmp_path: Path) -> None:
    from octop_harness.agent import HarnessAgent
    from octop_harness.compaction import _build_force_summarization_middleware
    from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig

    model = RecordingModel(responses=[AIMessage("done")], profile={"max_input_tokens": 100_000})
    factory = MagicMock()
    factory.get_chat_model.return_value = model
    cfg = HarnessAgentConfig(
        name="recall-budget",
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
        providers=[
            ProviderConfig(
                id="test", base_url="https://example.com/v1", api_key="test", models=[ModelConfig(id="model")]
            )
        ],
        default_model="test/model",
        memory_enabled=False,
        session_log_enabled=False,
        checkpointer=False,
    )
    with HarnessAgent(cfg, model_factory=factory) as agent:
        history = prepare(middleware(RecallService("long recall " * 1000)), [HumanMessage("question", id="u")])
        expected = count_tokens_with_recall(history)
        assert agent._summarization_mw.token_counter(history) == expected
        manual = _build_force_summarization_middleware(model, agent.backend)
        assert manual.token_counter(history) == expected
        assert expected > count_tokens_approximately(history)


def _close_memory(memory: Memory) -> None:
    pool = getattr(memory, "_checkpointer_pool", None)
    if pool is not None:
        pool.close()
    elif memory._checkpointer is not None:
        memory._checkpointer.conn.close()
    memory.backend.close()


def _open_memory(tmp_path: Path, backend: str, namespace: str) -> Memory:
    if backend == "postgres":
        dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("set TEST_POSTGRES_DSN to an isolated PostgreSQL test database")
        pytest.importorskip("psycopg")
        pytest.importorskip("langgraph.checkpoint.postgres")
        return Memory(namespace=namespace, backend="postgres", backend_config={"dsn": dsn})
    return Memory(namespace=namespace, backend_config={"db_path": str(tmp_path / "memory.sqlite")})


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
@pytest.mark.parametrize("interrupt_tools", [False, True])
def test_real_graph_reopens_database_and_preserves_wire_prefix(
    tmp_path: Path, interrupt_tools: bool, backend: str
) -> None:
    service = RecallService()

    def lookup() -> str:
        """Look up project details."""
        service.rendered = "changed while tool was running"
        return "lookup-result"

    tool = StructuredTool.from_function(lookup)
    model = RecordingModel(
        responses=[
            AIMessage("", tool_calls=[{"id": "t1", "name": "lookup", "args": {}}]),
            AIMessage("done"),
        ]
    )
    namespace = "replay_" + uuid.uuid4().hex[:12]
    config = {"configurable": {"thread_id": namespace, "session_id": namespace}}
    memory = _open_memory(tmp_path, backend, namespace)
    try:
        graph = create_agent(
            model,
            tools=[tool],
            system_prompt="Fixed system",
            middleware=[middleware(service)],
            checkpointer=memory,
            interrupt_before=["tools"] if interrupt_tools else None,
        )
        graph.invoke({"messages": [HumanMessage("deadline?")]}, config=config)
        state = graph.get_state(config).values
        assert state["messages"][0].content == "deadline?"
        assert RECALL_SNAPSHOT_KEY in state["messages"][0].additional_kwargs
    finally:
        _close_memory(memory)

    # Reopen both saver and middleware, including interrupted tool execution.
    reopened = _open_memory(tmp_path, backend, namespace)
    try:
        model2 = RecordingModel(responses=[AIMessage("done")])
        graph2 = create_agent(
            model2,
            tools=[tool],
            system_prompt="Fixed system",
            middleware=[middleware(service)],
            checkpointer=reopened,
            interrupt_before=["tools"] if interrupt_tools else None,
        )
        if interrupt_tools:
            graph2.invoke(None, config=config)
            last_wire = model2.wire_requests[-1]
            assert last_wire[: len(model.wire_requests[0])] == model.wire_requests[0]
        else:
            last_wire = model.wire_requests[-1]
            assert last_wire[: len(model.wire_requests[0])] == model.wire_requests[0]
        assert service.queries == ["deadline?"]
        service.rendered = "fresh next-turn memory"
        graph2.invoke({"messages": [HumanMessage("what next?")]}, config=config)
        next_wire = model2.wire_requests[-1]
        assert next_wire[: len(last_wire)] == last_wire
        assert "fresh next-turn memory" in next_wire[-1]["content"]
        assert service.queries == ["deadline?", "what next?"]
        assert RECALL_SNAPSHOT_KEY not in str(next_wire)
        assert graph2.get_state(config).values["messages"][0].content == "deadline?"
    finally:
        reopened.delete_thread(namespace)
        if backend == "postgres":
            reopened.backend.purge_namespace()
        _close_memory(reopened)


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_real_recall_survives_database_reopen_without_polluting_raw(tmp_path: Path, backend: str) -> None:
    namespace = "recall_" + uuid.uuid4().hex[:12]
    memory = _open_memory(tmp_path, backend, namespace)
    config = {"configurable": {"thread_id": namespace}}
    try:
        memory.store("ALPHA deadline is Friday", topic="ALPHA deadline")
        service = MemoryService(memory, host="recall-live-validation")
        result = service.recall("ALPHA deadline", thread_id=namespace)
        assert result.snippets and "Friday" in result.rendered
        model = RecordingModel(responses=[AIMessage("acknowledged")])
        graph = create_agent(model, middleware=[middleware(service)], checkpointer=memory)
        graph.invoke({"messages": [HumanMessage("ALPHA deadline")]}, config=config)
        first_wire = model.wire_requests[-1]
        assert "Friday" in first_wire[0]["content"]
    finally:
        _close_memory(memory)
    reopened = _open_memory(tmp_path, backend, namespace)
    try:
        # A different new question selects new data; the old turn keeps Friday.
        reopened.store("BETA deadline is Monday", topic="BETA deadline")
        service2 = MemoryService(reopened, host="recall-live-validation")
        assert service2.recall("BETA deadline", thread_id=namespace).snippets
        model2 = RecordingModel(responses=[AIMessage("acknowledged")])
        graph2 = create_agent(model2, middleware=[middleware(service2)], checkpointer=reopened)
        graph2.invoke({"messages": [HumanMessage("BETA deadline")]}, config=config)
        wire = model2.wire_requests[-1]
        assert wire[: len(first_wire)] == first_wire
        assert "Monday" in wire[-1]["content"]
        history = graph2.get_state(config).values["messages"]
        assert [m.content for m in history if isinstance(m, HumanMessage)] == ["ALPHA deadline", "BETA deadline"]
        service2.capture_turn(
            user=history[0].content, assistant="acknowledged", thread_id=namespace, session_id=namespace
        )
        # Capture is the real MemoryService write path, not a spy.
        rows = reopened.search_raw("ALPHA", limit=20)
        assert any(row.content == "ALPHA deadline" for row in rows)
        assert all("<memory-context>" not in row.content for row in rows)
    finally:
        reopened.delete_thread(namespace)
        if backend == "postgres":
            reopened.backend.purge_namespace()
        _close_memory(reopened)


@pytest.mark.asyncio
async def test_async_graph_keeps_sessions_isolated_and_replays_old_turns() -> None:
    class QueryService(RecallService):
        def recall(self, query: str, **kwargs: Any) -> Any:
            self.queries.append(query)
            return SimpleNamespace(rendered="memory for " + query)

    service = QueryService()
    model = RecordingModel(responses=[AIMessage("done")])
    graph = create_agent(model, middleware=[middleware(service)], checkpointer=InMemorySaver())
    configs = [{"configurable": {"thread_id": name}} for name in ("alice", "bob")]
    await asyncio.gather(
        *[
            graph.ainvoke({"messages": [HumanMessage(name)]}, config=config)
            for name, config in zip(("alice", "bob"), configs, strict=True)
        ]
    )
    for name, config in zip(("alice", "bob"), configs, strict=True):
        await graph.ainvoke({"messages": [HumanMessage("next " + name)]}, config=config)
        wire = model.wire_requests[-1]
        assert "memory for " + name in wire[0]["content"]
        assert "memory for next " + name in wire[-1]["content"]
        other = "bob" if name == "alice" else "alice"
        assert other not in str(wire)
    assert sorted(service.queries) == ["alice", "bob", "next alice", "next bob"]
