"""Tests for Langfuse tracing in octop-harness."""

from __future__ import annotations

from unittest import mock

from octop_harness.observability.langfuse import LangfuseConfig, LangfuseTracer
from octop_harness.request import ChatRequest


def test_enrich_request_disabled_returns_unchanged() -> None:
    tracer = LangfuseTracer(None)
    req = ChatRequest(messages="hi", thread_id="t1")
    assert tracer.enrich_request(req) is req


def test_enrich_request_adds_metadata_only() -> None:
    cfg = LangfuseConfig(
        enabled=True,
        public_key="pk-test",
        host="http://langfuse.example",
        secret_key="k",
    )
    tracer = LangfuseTracer(cfg)
    req = ChatRequest(
        messages="hi",
        thread_id="thread-1",
        user="7",
        agent_id="agent-1",
        source="dashboard",
        metadata={"foo": "bar"},
    )

    out = tracer.enrich_request(req)

    assert out is not req
    assert out.callbacks is None
    assert out.metadata is not None
    assert out.metadata["langfuse_user_id"] == "7"
    assert out.metadata["langfuse_session_id"] == "thread-1"
    assert out.metadata["agent_id"] == "agent-1"
    assert out.metadata["foo"] == "bar"


def test_callbacks_for_graph_with_config() -> None:
    cfg = LangfuseConfig(
        enabled=True,
        public_key="pk-test",
        host="http://langfuse.example",
        secret_key="k",
    )
    tracer = LangfuseTracer(cfg)
    handler = object()

    with (
        mock.patch("langfuse.Langfuse"),
        mock.patch("langfuse.langchain.CallbackHandler", return_value=handler),
    ):
        cbs = tracer.callbacks

    assert cbs == [handler]


def test_set_langfuse_callbacks_wraps_graph() -> None:
    from octop_harness.agent import HarnessAgent

    base = mock.MagicMock(name="base_graph")
    wrapped = mock.MagicMock(name="wrapped_graph")
    base.with_config.return_value = wrapped

    agent = object.__new__(HarnessAgent)
    agent._langfuse_callbacks = None
    agent._base_graph = base
    agent._graph = base
    agent._protocols = {}

    handler = object()
    agent.set_langfuse_callbacks([handler])

    base.with_config.assert_called_once_with({"callbacks": [handler]})
    assert agent._graph is wrapped

    agent.set_langfuse_callbacks(None)
    assert agent._graph is base
