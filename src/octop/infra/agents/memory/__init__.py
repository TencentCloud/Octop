"""Agent memory backend resolution and host-side slim control."""

from octop.infra.agents.memory.backend import (
    memory_backend_from_agent_config,
    open_memory_kwargs,
)
from octop.infra.agents.memory.slim import MemorySlimCoordinator
from octop.infra.agents.memory.slim_control import (
    MemorySlimControl,
    list_memory_slim_agents,
    request_memory_slim,
)

__all__ = [
    "MemorySlimControl",
    "MemorySlimCoordinator",
    "list_memory_slim_agents",
    "memory_backend_from_agent_config",
    "open_memory_kwargs",
    "request_memory_slim",
]
