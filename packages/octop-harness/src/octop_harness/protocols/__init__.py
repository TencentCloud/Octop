"""Protocol registry — discover and resolve chat protocol implementations."""

from __future__ import annotations

from typing import Any

from octop_harness.protocols.base import ChatProtocol

_PROTOCOL_REGISTRY: dict[str, type[ChatProtocol]] = {}


def register_protocol(name: str, cls: type[ChatProtocol]) -> None:
    """Register a protocol class under a given name.

    Args:
        name: Short identifier (e.g. ``"langgraph"``, ``"openai"``).
        cls: A concrete subclass of :class:`ChatProtocol`.
    """
    _PROTOCOL_REGISTRY[name] = cls


def resolve_protocol(name: str, graph: Any) -> ChatProtocol:
    """Instantiate a registered protocol by name.

    Args:
        name: The protocol identifier previously passed to :func:`register_protocol`.
        graph: The LangGraph graph (or compatible) object to inject.

    Returns:
        An instantiated :class:`ChatProtocol` subclass.

    Raises:
        ValueError: If *name* is not in the registry.
    """
    cls = _PROTOCOL_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(_PROTOCOL_REGISTRY.keys()))
        msg = f"Unknown protocol {name!r}. Available: {available}"
        raise ValueError(msg)
    return cls(graph=graph)


def _register_builtins() -> None:
    """Register the built-in protocol implementations."""
    from octop_harness.protocols.langgraph import LangGraphProtocol
    from octop_harness.protocols.mcp import MCPProtocol
    from octop_harness.protocols.openai import OpenAIProtocol

    register_protocol("langgraph", LangGraphProtocol)
    register_protocol("openai", OpenAIProtocol)
    register_protocol("mcp", MCPProtocol)


# Auto-register built-in protocols at module load time.
_register_builtins()

__all__ = ["ChatProtocol", "register_protocol", "resolve_protocol"]
