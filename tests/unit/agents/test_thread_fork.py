"""Tests for conversation fork-from-user-message."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop.infra.agents.thread_fork import (
    _fork_title,
    find_user_fork_index,
    fork_dashboard_thread,
    write_checkpoint_messages,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry


def test_fork_title_suffix() -> None:
    assert _fork_title("My chat", "en") == "My chat (fork)"
    assert _fork_title("My chat", "zh") == "My chat（分叉）"
    assert _fork_title(None, "en") == "Forked chat"
    assert _fork_title("", "zh") == "分叉对话"


def test_find_user_fork_index_by_suffix_count() -> None:
    messages = [
        HumanMessage(content="one", id="h1"),
        AIMessage(content="a1", id="a1"),
        HumanMessage(content="two", id="h2"),
        AIMessage(content="a2", id="a2"),
        HumanMessage(content="three", id="h3"),
    ]
    assert find_user_fork_index(messages, message_id="x", user_turns_from_end=2) == 2
    assert find_user_fork_index(messages, message_id="x", user_turns_from_end=1) == 4
    assert find_user_fork_index(messages, message_id="x", user_turns_from_end=3) == 0


def test_find_user_fork_index_by_id_when_suffix_mismatches_content() -> None:
    messages = [
        HumanMessage(content="keep", id="h1"),
        AIMessage(content="a1", id="a1"),
        HumanMessage(content="fork-me", id="h2"),
    ]
    idx = find_user_fork_index(
        messages,
        message_id="h2",
        content="other text",
        user_turns_from_end=1,
    )
    assert idx == 2


def test_find_user_fork_index_by_content_fallback() -> None:
    messages = [
        HumanMessage(content="alpha", id="h1"),
        AIMessage(content="a1", id="a1"),
        HumanMessage(content="beta", id="h2"),
    ]
    assert find_user_fork_index(messages, message_id="missing", content="beta") == 2


def test_find_user_fork_index_missing_raises() -> None:
    messages = [AIMessage(content="only assistant", id="a1")]
    with pytest.raises(OctopError) as exc:
        find_user_fork_index(messages, message_id="h1")
    assert exc.value.code is ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_write_checkpoint_messages_skips_empty() -> None:
    graph = SimpleNamespace(aupdate_state=AsyncMock())
    harness = SimpleNamespace(graph=graph)
    await write_checkpoint_messages(harness, thread_id="thr_new", messages=[])
    graph.aupdate_state.assert_not_called()


@pytest.mark.asyncio
async def test_fork_dashboard_thread_copies_prefix_and_rebinds() -> None:
    source_id = "thr_src"
    messages = [
        HumanMessage(content="first", id="h1"),
        AIMessage(content="ok", id="a1"),
        ToolMessage(content="tool", id="t1", tool_call_id="c1"),
        HumanMessage(content="second", id="h2"),
        AIMessage(content="later", id="a2"),
    ]
    store: dict[str, list[Any]] = {source_id: list(messages)}
    graph = SimpleNamespace()

    async def aget_state(config: dict[str, Any]) -> SimpleNamespace:
        tid = config["configurable"]["thread_id"]
        return SimpleNamespace(values={"messages": list(store.get(tid, []))})

    async def aupdate_state(config: dict[str, Any], values: dict[str, Any], **_k: Any) -> None:
        tid = config["configurable"]["thread_id"]
        store.setdefault(tid, []).extend(list(values.get("messages") or []))

    graph.aget_state = aget_state
    graph.aupdate_state = aupdate_state
    harness = SimpleNamespace(graph=graph)

    source = MagicMock(
        thread_id=source_id,
        agent_id="agt_1",
        title="Original title",
        model_ref="openai/gpt-4o",
        reasoning_mode="auto",
        reasoning_effort=None,
    )
    created: dict[str, Any] = {}

    async def rebind(**kwargs: Any) -> None:
        created["rebind"] = kwargs

    registry = MagicMock()
    registry.create_thread.return_value = "thr_fork"
    registry.get_thread.return_value = MagicMock(
        title="Original title",
        last_active=9,
        created_at=8,
    )
    registry.rebind = rebind

    out = await fork_dashboard_thread(
        thread_registry=registry,
        harness=harness,
        source=source,
        user_id=7,
        message_id="h2",
        content="second",
        user_turns_from_end=1,
    )

    assert out["thread_id"] == "thr_fork"
    assert out["source_thread_id"] == source_id
    assert out["copied_messages"] == 3
    assert [m.id for m in store["thr_fork"]] == ["h1", "a1", "t1"]
    registry.update_title.assert_called_once_with("thr_fork", "Original title (fork)")
    registry.touch_last_active.assert_not_called()
    registry.update_composer.assert_called_once()
    assert created["rebind"]["thread_id"] == "thr_fork"
    assert created["rebind"]["session_key"] == ThreadRegistry.dashboard_key(
        agent_id="agt_1", user_id=7
    )


@pytest.mark.asyncio
async def test_fork_dashboard_thread_from_first_question_is_empty() -> None:
    source_id = "thr_src"
    messages = [HumanMessage(content="only", id="h1"), AIMessage(content="a", id="a1")]
    store: dict[str, list[Any]] = {source_id: list(messages)}
    graph = SimpleNamespace()

    async def aget_state(config: dict[str, Any]) -> SimpleNamespace:
        tid = config["configurable"]["thread_id"]
        return SimpleNamespace(values={"messages": list(store.get(tid, []))})

    graph.aget_state = aget_state
    graph.aupdate_state = AsyncMock()
    harness = SimpleNamespace(graph=graph)

    registry = MagicMock()
    registry.create_thread.return_value = "thr_fork"
    registry.get_thread.return_value = MagicMock(title=None, last_active=0, created_at=1)
    registry.rebind = AsyncMock()

    out = await fork_dashboard_thread(
        thread_registry=registry,
        harness=harness,
        source=MagicMock(
            thread_id=source_id,
            agent_id="agt_1",
            title="only",
            model_ref=None,
            reasoning_mode=None,
            reasoning_effort=None,
        ),
        user_id=1,
        message_id="h1",
        user_turns_from_end=1,
    )

    assert out["copied_messages"] == 0
    graph.aupdate_state.assert_not_called()
    registry.update_title.assert_not_called()
    registry.touch_last_active.assert_not_called()


@pytest.mark.asyncio
async def test_fork_dashboard_thread_deletes_row_when_write_fails() -> None:
    source_id = "thr_src"
    messages = [
        HumanMessage(content="first", id="h1"),
        AIMessage(content="ok", id="a1"),
        HumanMessage(content="second", id="h2"),
    ]
    graph = SimpleNamespace()

    async def aget_state(_config: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(values={"messages": list(messages)})

    graph.aget_state = aget_state
    graph.aupdate_state = AsyncMock(side_effect=RuntimeError("checkpoint write failed"))
    harness = SimpleNamespace(graph=graph)
    registry = MagicMock()
    registry.create_thread.return_value = "thr_fork"
    registry.rebind = AsyncMock()

    with pytest.raises(RuntimeError, match="checkpoint write failed"):
        await fork_dashboard_thread(
            thread_registry=registry,
            harness=harness,
            source=MagicMock(
                thread_id=source_id,
                agent_id="agt_1",
                title="t",
                model_ref=None,
                reasoning_mode=None,
                reasoning_effort=None,
            ),
            user_id=1,
            message_id="h2",
            user_turns_from_end=1,
        )

    registry.delete_thread.assert_called_once_with("thr_fork")
    registry.rebind.assert_not_called()
