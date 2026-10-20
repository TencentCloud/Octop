# pylint: disable=invalid-name
"""Skills + custom tools example.

Demonstrates:
  - Adding a custom tool via ``HarnessAgentConfig.tools``.
  - Dropping user skills into ``workspace/skills/<skill-name>/SKILL.md``.
  - Memory files (AGENTS.md / USER.md) influencing the agent.

Reads model config from environment variables (or ``.env``) via
``HarnessAgentConfig.from_env()``. Supports:

    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME
    HARNESS_PROVIDER_<NAME>_API_KEY / _BASE_URL
    Any known provider key (e.g. DEEPSEEK_API_KEY)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool

from octop_harness import (
    ChatRequest,
    HarnessAgentConfig,
    HarnessAgentManager,
)


@tool
def reverse_string(text: str) -> str:
    """Return the input string reversed."""
    return text[::-1]


async def main() -> None:
    load_dotenv()

    root = Path("./agent_root").absolute()
    root.mkdir(exist_ok=True)

    # Seed a memory file that the agent will read on every turn.
    (root / "AGENTS.md").write_text(
        "# Project conventions\n\n- Always reply in lowercase.\n",
        encoding="utf-8",
    )

    # Seed a user-provided skill under workspace/skills/.
    skills_dir = root / "workspace" / "skills" / "joke-mode"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: joke-mode\ndescription: Respond with a one-line dad joke.\n---\n\n"
        "# Joke mode\n\nWhen the user invokes joke mode, reply with a single dad joke.\n",
        encoding="utf-8",
    )

    config = HarnessAgentConfig.from_env(
        workspace_dir=root,
        name="skills-demo",
        # Sandbox the filesystem to the demo dir so the agent's grep/ls tools
        # don't recurse into ``/`` on the default ``local_shell`` backend.
        backend={"type": "filesystem", "root_dir": str(root), "virtual_mode": True},
        tools=[reverse_string],
        # AGENTS.md drives deepagents' built-in MemoryMiddleware. We
        # disable octop-harness's session logger / Memory store so the
        # two don't collide on duplicate middleware names. (See the
        # upstream `Please remove duplicate middleware instances.`
        # assertion.)
        memory_enabled=False,
        session_log_enabled=False,
    )

    manager = HarnessAgentManager()
    entry = manager.create_agent(config)

    request = ChatRequest(
        messages="Reverse the word 'harness' for me, and then say hi.",
        thread_id="skills-demo",
    )
    async for chunk in manager.stream(entry.agent_id, request):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
