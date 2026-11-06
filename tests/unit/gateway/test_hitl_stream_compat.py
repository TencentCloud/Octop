"""LangGraph v2 interrupt projection for dashboard HITL."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.types import Interrupt
from octop_harness.protocols.langgraph import LangGraphProtocol

from octop.infra.gateway.hitl.stream_compat import (
    hitl_events_from_interrupts,
    install_harness_hitl_compat,
    merge_hitl_projection,
)


def test_hitl_events_from_interrupt_objects() -> None:
    class _Interrupt:
        def __init__(self, value: object) -> None:
            self.value = value

    events = hitl_events_from_interrupts(
        (
            _Interrupt(
                {
                    "action_requests": [
                        {
                            "name": "ask_user_question",
                            "args": {"questions": [{"question": "Go?"}]},
                        }
                    ]
                }
            ),
        )
    )
    assert len(events) == 1
    assert events[0]["type"] == "hitl_required"
    assert events[0]["request"]["action_requests"][0]["name"] == "ask_user_question"


def test_hitl_events_from_interrupt_dicts() -> None:
    events = hitl_events_from_interrupts(
        [
            {
                "id": "abc",
                "value": {
                    "action_requests": [{"name": "execute", "args": {"command": "ls"}}],
                },
            }
        ]
    )
    assert events[0]["request"]["action_requests"][0]["args"]["command"] == "ls"


def test_hitl_events_ignore_empty_envelopes() -> None:
    assert hitl_events_from_interrupts([{"id": "x", "value": {"raw": "nope"}}]) == []
    assert hitl_events_from_interrupts(None) == []


def test_merge_replaces_empty_hitl_required_from_interrupts() -> None:
    events = merge_hitl_projection(
        [{"type": "hitl_required", "request": {"id": "int-1", "value": {}}}],
        [
            {
                "id": "int-1",
                "value": {
                    "action_requests": [
                        {"name": "ask_user_question", "args": {"questions": [{"question": "Go?"}]}}
                    ]
                },
            }
        ],
    )
    assert len(events) == 1
    assert events[0]["request"]["action_requests"][0]["name"] == "ask_user_question"


def test_merge_keeps_actionable_hitl_required() -> None:
    existing = {
        "type": "hitl_required",
        "request": {"action_requests": [{"name": "execute", "args": {"command": "ls"}}]},
    }
    events = merge_hitl_projection(
        [existing],
        [{"value": {"action_requests": [{"name": "ask_user_question", "args": {}}]}}],
    )
    assert events == [existing]


class _ChunkGraph:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        assert kwargs["stream_mode"] == ["values", "updates", "messages", "custom"]
        assert kwargs["version"] == "v2"
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk


def _paired_chunks(interrupt: Any) -> list[dict[str, Any]]:
    return [
        {"type": "updates", "ns": (), "data": {"__interrupt__": (interrupt,)}},
        {"type": "values", "ns": (), "data": {"messages": []}, "interrupts": (interrupt,)},
    ]


def _request() -> dict[str, Any]:
    return {
        "action_requests": [{"name": "request_secret_file", "args": {"path": "hr.token"}}],
        "review_configs": [
            {"action_name": "request_secret_file", "allowed_decisions": ["respond"]}
        ],
    }


async def _collect_hitl(source: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event async for event in source if event["type"] == "hitl_required"]


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("as_dict", [False, True])
async def test_protocol_projects_each_interrupt_id_once_without_changing_chunks(
    resume: bool, as_dict: bool
) -> None:
    install_harness_hitl_compat()
    interrupts = [
        {"id": identity, "value": _request()}
        if as_dict
        else Interrupt(value=_request(), id=identity)
        for identity in ("pause-one", "pause-two")
    ]
    chunks = [chunk for item in interrupts for chunk in _paired_chunks(item)]
    original = deepcopy(chunks)
    protocol = LangGraphProtocol(graph=_ChunkGraph(chunks))
    config = {"configurable": {"thread_id": "thread-one"}}
    source = (
        protocol.resume_stream("thread-one", [{"type": "respond", "message": "filled"}], config)
        if resume
        else protocol.stream([], config)
    )
    events = await _collect_hitl(source)
    assert len(events) == 2
    assert [event["request"] for event in events] == [_request(), _request()]
    assert chunks == original


@pytest.mark.parametrize("resume", [False, True])
async def test_protocol_keeps_interrupts_without_an_identity(resume: bool) -> None:
    install_harness_hitl_compat()
    chunks = _paired_chunks(SimpleNamespace(value=_request()))
    original = deepcopy(chunks)
    protocol = LangGraphProtocol(graph=_ChunkGraph(chunks))
    source = (
        protocol.resume_stream("thread-one", [{"type": "respond", "message": "filled"}], {})
        if resume
        else protocol.stream([], {"configurable": {"thread_id": "thread-one"}})
    )
    assert len(await _collect_hitl(source)) == 2
    assert chunks == original


async def test_protocol_interrupt_ids_are_isolated_between_concurrent_streams_and_resume() -> None:
    install_harness_hitl_compat()
    protocol = LangGraphProtocol(
        graph=_ChunkGraph(_paired_chunks(Interrupt(value=_request(), id="same-identity")))
    )
    results = await asyncio.gather(
        _collect_hitl(protocol.stream([], {"configurable": {"thread_id": "thread-one"}})),
        _collect_hitl(protocol.stream([], {"configurable": {"thread_id": "thread-two"}})),
        _collect_hitl(
            protocol.resume_stream("thread-three", [{"type": "respond", "message": "filled"}], {})
        ),
    )
    assert [len(events) for events in results] == [1, 1, 1]
