"""Memory adapter helpers for octop-harness.

The public surface of this subpackage is :class:`MemoryRuntime`, which wires
:class:`octop_memory.Memory` / :class:`octop_memory.MemoryService` into the
agent.

:class:`octop_harness.memory.llm_client.HarnessAgentLLMClient` is an internal
adapter used by :class:`MemoryRuntime` to expose the agent's
:class:`~octop_harness.llm.factory.ChatModelFactory` to octop-memory's
extractor / promotion / page-regeneration paths via the
:class:`octop_memory.ports.llm.LLMClient` protocol. It is intentionally not
re-exported here: callers who need a custom LLM client should implement the
``LLMClient`` protocol directly rather than subclassing or constructing this
adapter themselves.
"""

from __future__ import annotations

from octop_harness.memory.runtime import MemoryRuntime

__all__ = ["MemoryRuntime"]
