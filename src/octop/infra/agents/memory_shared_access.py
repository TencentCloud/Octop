"""Per-expert data credentials for standalone Memory MCP access."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Any

from cryptography.fernet import InvalidToken
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from octop_harness.mcp import load_mcp_tools

from octop.infra.agents.memory_sharing import service_url
from octop.infra.crypto.fernet import decrypt_json, encrypt_json
from octop.infra.users.access import agent_is_shared

if TYPE_CHECKING:
    from octop.infra.db.repos.agents import AgentRow
    from octop.infra.db.repos.secrets import SecretRepo

_SECRET_PURPOSE = "memory_shared_expert_fernet"
_SECRET_KEY = "memory_sharing.expert.{agent_id}"
_SERVER_NAME = "octop_shared"
_TOOLS = ("memory_search", "memory_get", "memory_save", "memory_capture")


@dataclass(frozen=True)
class ExpertBinding:
    space_id: str | None = None
    owner_id: int | None = None
    base_url: str | None = None
    token_id: str | None = None
    token: str | None = field(default=None, repr=False)

    def active_for(self, row: AgentRow) -> bool:
        return bool(
            supports_sharing(row)
            and self.owner_id == row.user_id
            and self.base_url == service_url()
            and self.space_id
            and self.token_id
            and self.token
        )


def supports_sharing(row: AgentRow) -> bool:
    """Only local, owned expert runtimes can use their own private token."""
    return row.kind == "expert" and row.user_id is not None and not agent_is_shared(row)


def get_expert_binding(repo: SecretRepo, agent_id: str) -> ExpertBinding | None:
    stored = repo.get(_SECRET_KEY.format(agent_id=agent_id))
    if stored is None:
        return None
    try:
        return ExpertBinding(**decrypt_json(repo, _SECRET_PURPOSE, stored))
    except (InvalidToken, TypeError, ValueError):
        return ExpertBinding()


def save_expert_binding(repo: SecretRepo, agent_id: str, binding: ExpertBinding) -> None:
    repo.put(
        _SECRET_KEY.format(agent_id=agent_id), encrypt_json(repo, _SECRET_PURPOSE, asdict(binding))
    )


def _guard_tool(tool: StructuredTool, allowed: Callable[[], bool]) -> StructuredTool:
    original = tool.coroutine
    assert original is not None

    @wraps(original)
    async def invoke(*args: Any, **arguments: Any) -> Any:
        if not await asyncio.to_thread(allowed):
            raise ToolException(
                "Shared memory access changed. Reopen the expert to use its current space."
            )
        return await original(*args, **arguments)

    return tool.model_copy(update={"coroutine": invoke, "func": None, "handle_tool_error": True})


def shared_memory_tools(
    row: AgentRow,
    repo: SecretRepo,
    get_agent: Callable[[str], AgentRow | None],
) -> list[BaseTool]:
    if not supports_sharing(row):
        return []
    binding = get_expert_binding(repo, row.agent_id)
    if binding is None or not binding.active_for(row):
        return []

    def allowed() -> bool:
        # An in-flight turn may still hold tools from before a reload, unbind,
        # or a change in expert ownership/visibility.
        latest = get_agent(row.agent_id)
        return (
            latest is not None
            and binding.active_for(latest)
            and get_expert_binding(repo, row.agent_id) == binding
        )

    tools = load_mcp_tools(
        {
            _SERVER_NAME: {
                "transport": "http",
                "url": f"{binding.base_url}/mcp/",
                "headers": {
                    "Authorization": f"Bearer {binding.token}",
                    "X-Octop-Space": binding.space_id,
                },
                "allowed_tools": _TOOLS,
                "timeout": 5.0,
                "sse_read_timeout": 15.0,
            }
        }
    )
    return [
        _guard_tool(tool, allowed)
        for tool in tools
        if isinstance(tool, StructuredTool) and tool.coroutine is not None
    ]
