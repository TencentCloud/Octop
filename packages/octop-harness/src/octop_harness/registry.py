"""In-memory agent registry: :class:`AgentEntry` + storage CRUD."""

from __future__ import annotations

import secrets
import string
from datetime import datetime
from typing import TYPE_CHECKING, Any

from octop_harness.config import HarnessAgentConfig

if TYPE_CHECKING:
    from octop_harness.agent import HarnessAgent

_AGENT_ID_ALPHABET = string.ascii_lowercase + string.digits
_AGENT_ID_LENGTH = 6
_AGENT_ID_MAX_ATTEMPTS = 100


def generate_agent_id(*, occupied: set[str]) -> str:
    """Return a short random ID not present in *occupied*."""
    for _ in range(_AGENT_ID_MAX_ATTEMPTS):
        aid = "".join(secrets.choice(_AGENT_ID_ALPHABET) for _ in range(_AGENT_ID_LENGTH))
        if aid not in occupied:
            return aid
    msg = f"Failed to generate a unique {_AGENT_ID_LENGTH}-character agent_id"
    raise RuntimeError(msg)


class AgentEntry:
    """Registry record for a managed agent."""

    def __init__(
        self,
        *,
        agent_id: str,
        agent: HarnessAgent,
        config: HarnessAgentConfig,
        metadata: dict[str, Any],
        tags: list[str],
        created_at: datetime,
    ) -> None:
        self.agent_id = agent_id
        self.agent = agent
        self.config = config
        self.metadata = metadata
        self.tags = tags
        self.created_at = created_at


class AgentRegistry:
    """``agent_id → AgentEntry`` map with add/get/remove/list."""

    def __init__(self) -> None:
        self._entries: dict[str, AgentEntry] = {}

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._entries

    def __getitem__(self, agent_id: str) -> AgentEntry:
        return self._entries[agent_id]

    def values(self) -> list[AgentEntry]:
        return list(self._entries.values())

    def agent_ids(self) -> list[str]:
        return list(self._entries.keys())

    def clear(self) -> None:
        self._entries.clear()

    def add(self, entry: AgentEntry) -> None:
        if entry.agent_id in self._entries:
            raise ValueError(f"Agent '{entry.agent_id}' already exists in the registry.")
        self._entries[entry.agent_id] = entry

    def get(self, agent_id: str) -> AgentEntry:
        return self._entries[agent_id]

    def remove(self, agent_id: str) -> AgentEntry:
        entry = self._entries.pop(agent_id, None)
        if entry is None:
            raise KeyError(agent_id)
        return entry

    def list(
        self,
        *,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> list[AgentEntry]:
        results: list[AgentEntry] = []
        for entry in self._entries.values():
            if agent_id is not None and entry.agent_id != agent_id:
                continue
            if metadata is not None and not all(entry.metadata.get(k) == v for k, v in metadata.items()):
                continue
            if tags is not None and not all(t in entry.tags for t in tags):
                continue
            results.append(entry)
        return results


__all__ = ["AgentEntry", "AgentRegistry", "generate_agent_id"]
