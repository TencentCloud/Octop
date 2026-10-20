# pylint: disable=invalid-name
"""Demo: built-in Skills (skill-creator / install-skill / …).

Walks through:

    1. ``HarnessAgent.init_workspace`` populates ``{workspace}/_builtin_skills/``
       with the bundled Skills.
    2. With an LLM configured, the agent loads Skills from the workspace.

Run with::

    uv run python examples/07_builtin_skills_tour.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgent,
    HarnessAgentConfig,
    HarnessAgentManager,
    ModelConfig,
    ProviderConfig,
)


def _heading(label: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n {label}\n{bar}")


def _build_offline_agent(root: Path) -> HarnessAgent:
    """Construct an agent whose only job is to bootstrap the workspace."""
    config = HarnessAgentConfig(
        workspace_dir=root,
        name="skills-tour-init",
        backend={
            "type": "filesystem",
            "root_dir": str(root),
            "virtual_mode": True,
        },
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://api.example.com/v1",
                api_key="sk-fake",
                models=[ModelConfig(id="placeholder", input=["text"])],
            ),
        ],
        default_model="p/placeholder",
        session_log_enabled=False,
    )
    return HarnessAgent(config)


def scenario_init_with_skills(root: Path) -> None:
    _heading("Scenario 1: built-in Skills sync into the workspace")
    agent = _build_offline_agent(root)
    agent.init_workspace()
    workspace = root / "workspace"
    builtin = workspace / "_builtin_skills"
    skills = sorted(p.name for p in builtin.iterdir() if p.is_dir())
    print("synced built-in skills:")
    for name in skills:
        print(f"  • {name}")
    assert {"skill-creator", "install-skill"}.issubset(set(skills))


async def scenario_agent_uses_skill(root: Path) -> None:
    _heading("Scenario 2: agent + LLM consumes the bundled Skills")
    if "OPENAI_API_KEY" not in os.environ:
        print("(skipped — OPENAI_API_KEY not set)")
        return

    config = HarnessAgentConfig.from_env(
        workspace_dir=root,
        name="skills-tour",
        backend={
            "type": "filesystem",
            "root_dir": str(root),
            "virtual_mode": True,
        },
        session_log_enabled=False,
    )
    manager = HarnessAgentManager()
    entry = manager.create_agent(config)

    prompt = (
        "The workspace includes built-in skills such as skill-creator and install-skill. "
        "In one sentence each, say what those two skills are for."
    )
    print("model reply: ", end="", flush=True)
    async for chunk in manager.stream(entry.agent_id, ChatRequest(messages=prompt, thread_id="skills-tour")):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


def main() -> None:
    load_dotenv()
    root = Path("./.skills_tour_root").absolute()
    root.mkdir(exist_ok=True)
    print(f"demo root: {root}")

    scenario_init_with_skills(root)
    asyncio.run(scenario_agent_uses_skill(root))


if __name__ == "__main__":
    main()
