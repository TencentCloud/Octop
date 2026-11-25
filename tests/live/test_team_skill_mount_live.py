"""A dispatched member can read a skill file that lives on its own workspace.

Requires ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, and ``OPENAI_MODEL_NAME``.
The agents are created in the temporary live home, not the operator's
``~/.octop``.
"""

from __future__ import annotations

from typing import Any

import pytest
from octop_harness.request import ChatRequest

from octop.infra.agents.manager import AgentCreateSpec
from octop.infra.agents.teams.file_target import (
    DIR_KEY,
    HOST_KEY,
    MOUNTS_KEY,
    deepagents_directories,
    workspace_directory,
)

pytestmark = pytest.mark.live


def _text(result: dict[str, Any]) -> str:
    messages = result.get("messages")
    if not isinstance(messages, list):
        return str(result)
    parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(str(block.get("text") or block.get("content") or ""))
        else:
            parts.append(str(message))
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_member_reads_its_skill_file_while_the_root_is_the_host(
    live_agent_manager,
    live_openai_config,
) -> None:
    host = await live_agent_manager.create(
        AgentCreateSpec(
            name="mount-host",
            default_model=live_openai_config.default_model,
            system_prompt="You are a team host.",
        ),
    )
    member = await live_agent_manager.create(
        AgentCreateSpec(
            name="mount-member",
            default_model=live_openai_config.default_model,
            system_prompt="You follow file paths exactly.",
        ),
    )
    member_agent = live_agent_manager.get_agent(member.agent_id)
    host_agent = live_agent_manager.get_agent(host.agent_id)
    mounts = deepagents_directories(member_agent)
    builtin = next(
        (path for path in mounts if path.rstrip("/").endswith("_builtin_skills")),
        "",
    )
    assert builtin
    skill_path = f"{builtin}/team-mount-probe/SKILL.md"
    await member_agent.workspace.awrite_text(
        skill_path,
        "name: team-mount-probe\nprobe-marker-4c91e2\n",
        force=True,
    )

    chunks: list[Any] = []
    async for chunk in member_agent.stream(
        ChatRequest(
            messages=(
                "Call read_file exactly once on this path, then stop. "
                "Reply with the phrase skill-mount-ok and the marker line from the file. "
                f"Path: {skill_path}"
            ),
            model=live_openai_config.default_model,
            configurable={
                HOST_KEY: host.agent_id,
                DIR_KEY: workspace_directory(host_agent),
                MOUNTS_KEY: mounts,
            },
            recursion_limit=40,
        )
    ):
        chunks.append(chunk)
    parts: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        data = chunk.get("data")
        messages = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(messages, list):
            continue
        for message in messages:
            content = getattr(message, "content", "")
            parts.append(f"{type(message).__name__}: {content}")
    text = "\n".join(parts)
    assert "probe-marker-4c91e2" in text, text[-5000:]
