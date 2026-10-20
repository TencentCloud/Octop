"""Tests for the protocol registry."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import BaseMessage

from octop_harness.protocols import (
    _PROTOCOL_REGISTRY,
    register_protocol,
    resolve_protocol,
)
from octop_harness.protocols.base import ChatProtocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CustomProtocol(ChatProtocol):
    """Minimal concrete protocol for testing registration."""

    @property
    def name(self) -> str:
        return "custom"

    async def call(self, messages: list[BaseMessage], config: dict[str, Any]) -> dict[str, Any]:
        return {"messages": messages}

    async def stream(
        self, messages: list[BaseMessage], config: dict[str, Any], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        yield {"event": "done"}

    async def stream_events(self, messages: list[BaseMessage], config: dict[str, Any], **kwargs: Any) -> Any:
        return MagicMock(name="fake-stream")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegisterAndResolve:
    """Test registering a custom protocol and resolving it."""

    def test_register_custom_and_resolve(self) -> None:
        """A custom protocol can be registered and resolved."""
        register_protocol("custom", _CustomProtocol)
        try:
            graph = MagicMock(name="fake-graph")
            protocol = resolve_protocol("custom", graph)
            assert isinstance(protocol, _CustomProtocol)
            assert protocol.name == "custom"
            assert protocol._graph is graph
        finally:
            # Clean up to avoid polluting other tests
            _PROTOCOL_REGISTRY.pop("custom", None)


class TestResolveUnknown:
    """Test that resolving an unknown protocol raises ValueError."""

    def test_unknown_name_raises_value_error(self) -> None:
        """resolve_protocol raises ValueError for unregistered names."""
        with pytest.raises(ValueError, match="Unknown protocol 'nonexistent'") as exc_info:
            resolve_protocol("nonexistent", MagicMock())

        # The error message lists available names
        error_msg = str(exc_info.value)
        assert "Available:" in error_msg
        assert "langgraph" in error_msg


class TestBuiltinsRegistered:
    """Test that all builtin protocols are registered at module load."""

    @pytest.mark.parametrize("protocol_name", ["langgraph", "openai", "mcp"])
    def test_builtin_registered(self, protocol_name: str) -> None:
        """Built-in protocol is registered and resolvable."""
        assert protocol_name in _PROTOCOL_REGISTRY

        graph = MagicMock(name="fake-graph")
        protocol = resolve_protocol(protocol_name, graph)
        assert isinstance(protocol, ChatProtocol)
        assert protocol.name == protocol_name
