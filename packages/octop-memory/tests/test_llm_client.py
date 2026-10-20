"""Tests for ``LLMClient`` Protocol + ``MockLLMClient`` + ``NoopLLMClient``."""

from __future__ import annotations

import pytest

from octop_memory.ports.llm import (
    LLMClient,
    MockLLMClient,
    NoopLLMClient,
)
from octop_memory.ports.llm._protocol import LLMClientError

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_mock_satisfies_protocol(self) -> None:
        assert isinstance(MockLLMClient(default_response="x"), LLMClient)

    def test_noop_satisfies_protocol(self) -> None:
        assert isinstance(NoopLLMClient(), LLMClient)


# ---------------------------------------------------------------------------
# MockLLMClient
# ---------------------------------------------------------------------------


class TestMockLLMClient:
    def test_returns_default_response(self) -> None:
        mock = MockLLMClient(default_response="hello")
        assert mock.call_llm("anything") == "hello"

    def test_keyed_response_overrides_default(self) -> None:
        mock = MockLLMClient(
            responses={"first 80 chars match"[:80]: "specific"},
            default_response="default",
        )
        assert mock.call_llm("first 80 chars match") == "specific"
        assert mock.call_llm("something else") == "default"

    def test_no_response_no_default_raises(self) -> None:
        mock = MockLLMClient()
        with pytest.raises(LLMClientError):
            mock.call_llm("x")

    def test_raise_on_call_flag(self) -> None:
        mock = MockLLMClient(raise_on_call=True, default_response="ignored")
        with pytest.raises(LLMClientError):
            mock.call_llm("x")

    def test_call_recording(self) -> None:
        mock = MockLLMClient(default_response="ok")
        mock.call_llm("p1", tier="light", system="sys", response_format="json")
        mock.call_llm("p2", tier="heavy")

        assert len(mock.calls) == 2
        assert mock.calls[0].prompt == "p1"
        assert mock.calls[0].tier == "light"
        assert mock.calls[0].system == "sys"
        assert mock.calls[0].response_format == "json"
        assert mock.calls[1].tier == "heavy"
        assert mock.calls[1].system is None

    def test_queue_method_adds_response_after_construction(self) -> None:
        mock = MockLLMClient()
        mock.queue("hello"[:80], "world")
        assert mock.call_llm("hello") == "world"

    def test_reset_clears_calls(self) -> None:
        mock = MockLLMClient(default_response="x")
        mock.call_llm("a")
        mock.call_llm("b")
        mock.reset()
        assert mock.calls == []


# ---------------------------------------------------------------------------
# NoopLLMClient
# ---------------------------------------------------------------------------


class TestNoopLLMClient:
    def test_always_raises(self) -> None:
        client = NoopLLMClient()
        with pytest.raises(LLMClientError) as exc_info:
            client.call_llm("anything")
        assert "no LLM backend configured" in str(exc_info.value)
