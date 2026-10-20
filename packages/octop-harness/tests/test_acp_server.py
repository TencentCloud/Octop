"""tests/test_acp_server.py — unit tests for ACP server helpers."""

from __future__ import annotations

from typing import Any, Protocol

import pytest
from acp import Agent
from acp.schema import InitializeResponse, NewSessionResponse

from octop_harness.acp.server import (
    ACP_AGENT_META_KEY,
    HarnessACPAgent,
    _acp_agent_cls,
    _chunk_to_updates,
    _extract_prompt_text,
    _StreamTracker,
    _tool_output_text,
    build_harness_acp_agent,
)


def test_extract_prompt_text_from_dict_blocks() -> None:
    assert _extract_prompt_text([{"type": "text", "text": "hello"}]) == "hello"
    assert _extract_prompt_text([{"text": "a"}, {"text": "b"}]) == "a\nb"


def test_stream_tracker_text_delta() -> None:
    tracker = _StreamTracker()
    assert tracker.delta_text("hello") == "hello"
    assert tracker.delta_text("hello world") == " world"


def test_chunk_to_updates_token() -> None:
    tracker = _StreamTracker()
    updates = _chunk_to_updates(
        {"type": "token", "content": "hi"},
        tracker,
        tool_name_buf={},
        tool_id_buf={},
    )
    assert len(updates) == 1


def test_tool_output_text_from_objects() -> None:
    class _Msg:
        content = "done"

    assert _tool_output_text([_Msg()]) == "done"


def test_acp_agent_mro_prefers_harness_implementation() -> None:
    """Protocol stubs must not shadow HarnessACPAgent (regression for null ACP replies)."""
    cls = _acp_agent_cls(object(), agent_id="agent-1")
    mro = cls.__mro__
    assert mro.index(HarnessACPAgent) < mro.index(Agent), (
        f"HarnessACPAgent must precede acp.Agent in MRO, got {[c.__name__ for c in mro]}"
    )


@pytest.mark.asyncio
async def test_protocol_before_impl_returns_none_documents_bug() -> None:
    """Pin why ``(Agent, HarnessACPAgent)`` is wrong: Protocol methods return None."""

    class _Iface(Protocol):
        async def initialize(self, protocol_version: int) -> object:
            """Protocol stub: the body is ``...``, so a protocol-first MRO returns None."""
            ...

    class _Impl:
        async def initialize(self, protocol_version: int) -> object:
            return {"protocolVersion": protocol_version}

    class _Broken(_Iface, _Impl):
        def __init__(self) -> None:
            _Impl.__init__(self)

    class _Fixed(_Impl, _Iface):
        def __init__(self) -> None:
            _Impl.__init__(self)

    assert await _Broken().initialize(1) is None
    assert await _Fixed().initialize(1) == {"protocolVersion": 1}


@pytest.mark.asyncio
async def test_build_harness_acp_agent_initialize_not_null() -> None:
    agent = build_harness_acp_agent(object(), agent_id="main")
    result = await agent.initialize(protocol_version=1)
    assert result is not None
    assert isinstance(result, InitializeResponse)
    assert result.protocol_version == 1
    assert result.agent_capabilities is not None
    assert result.agent_capabilities.load_session is True
    assert result.agent_info is not None
    assert result.agent_info.name == "octop"


@pytest.mark.asyncio
async def test_build_harness_acp_agent_new_session_returns_id() -> None:
    agent = build_harness_acp_agent(object(), agent_id="main")
    result = await agent.new_session(cwd="/tmp")
    assert result is not None
    assert isinstance(result, NewSessionResponse)
    assert isinstance(result.session_id, str) and result.session_id
    assert result.field_meta == {ACP_AGENT_META_KEY: "main"}


@pytest.mark.asyncio
async def test_build_harness_acp_agent_load_and_close_session() -> None:
    agent = build_harness_acp_agent(object(), agent_id="main")
    created = await agent.new_session(cwd="/work")
    loaded = await agent.load_session(cwd="/work", session_id=created.session_id)
    assert loaded is not None
    assert loaded.field_meta == {ACP_AGENT_META_KEY: "main"}
    closed = await agent.close_session(session_id=created.session_id)
    assert closed is not None


@pytest.mark.asyncio
async def test_wrong_mro_with_real_acp_agent_protocol_returns_null() -> None:
    """With the real ``acp.Agent`` Protocol, wrong base order yields null handshakes."""

    class _Broken(Agent, HarnessACPAgent):
        def __init__(self) -> None:
            HarnessACPAgent.__init__(self, object(), agent_id="x")

    broken = _Broken()
    assert await broken.initialize(protocol_version=1) is None
    assert await broken.new_session(cwd="/tmp") is None


def test_run_and_build_share_same_mro_factory() -> None:
    """Both public entry points must use the same implementation-first class factory."""
    build_cls = type(build_harness_acp_agent(object(), agent_id="a"))
    run_cls = _acp_agent_cls(object(), agent_id="a")
    assert build_cls.__mro__[1:] == run_cls.__mro__[1:]
    assert build_cls.__mro__.index(HarnessACPAgent) < build_cls.__mro__.index(Agent)


@pytest.mark.asyncio
async def test_prompt_empty_returns_end_turn_without_harness_stream() -> None:
    class _BoomHarness:
        def stream(self, *_a: Any, **_k: Any) -> Any:
            raise AssertionError("empty prompt must not call harness.stream")

    agent = build_harness_acp_agent(_BoomHarness(), agent_id="main")
    result = await agent.prompt(prompt=[], session_id="s1")
    assert result.stop_reason == "end_turn"
