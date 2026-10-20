# pylint: disable=invalid-name
"""Multi-agent orchestration: route requests across multiple specialised agents.

Demonstrates running several agents with different roles under one
``AgentManager``:

- ``AgentManager.create()``  — register agents with metadata and tags
- ``AgentManager.list()``    — filter by metadata / tags
- ``AgentManager.stream()``  — route a chat request to a specific agent by id
- ``AgentManager.cancel()``  — interrupt an in-flight stream
- ``AgentManager.remove()``  — deregister an agent

Provider config is read automatically from environment variables::

    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME
    HARNESS_PROVIDER_<NAME>_API_KEY / _BASE_URL
    DEEPSEEK_API_KEY  (or any other known provider key)

Run with::

    uv run python examples/11_multi_agent.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgentConfig,
    HarnessAgentManager,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(root: Path, role: str) -> HarnessAgentConfig:
    """One sandboxed config per agent role."""
    ws = root / role
    ws.mkdir(parents=True, exist_ok=True)
    return HarnessAgentConfig.from_env(
        workspace_dir=ws,
        name=role,
        backend={"type": "filesystem", "root_dir": str(ws), "virtual_mode": True},
    )


def _last_content(chunks: list[str]) -> str:
    return "".join(chunks).strip() or "(no output)"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


async def main() -> None:
    load_dotenv()

    root = Path("./multi_agent_demo").absolute()

    manager = HarnessAgentManager()

    # ------------------------------------------------------------------
    # 1. Register three agents with different roles
    # ------------------------------------------------------------------
    support = manager.create_agent(
        _config(root, "customer-support"),
        metadata={"role": "support", "env": "demo"},
        tags=["prod", "support"],
    )
    analyst = manager.create_agent(
        _config(root, "data-analyst"),
        metadata={"role": "analyst", "env": "demo"},
        tags=["prod", "analyst"],
    )
    dev = manager.create_agent(
        _config(root, "dev-assistant"),
        metadata={"role": "dev", "env": "staging"},
        tags=["staging", "dev"],
    )

    print("=== Registered agents ===")
    for e in manager.list_agents():
        print(f"  [{e.agent_id[:8]}]  name={e.config.name!r}  tags={e.tags}")

    # ------------------------------------------------------------------
    # 2. Filter agents by metadata / tags
    # ------------------------------------------------------------------
    prod_agents = manager.list_agents(metadata={"env": "demo"})
    print(f"\nAgents in 'demo' env ({len(prod_agents)}):", [e.config.name for e in prod_agents])

    support_agents = manager.list_agents(tags=["support"])
    print(f"Agents tagged 'support' ({len(support_agents)}):", [e.config.name for e in support_agents])

    # ------------------------------------------------------------------
    # 3. Route a request to the support agent and stream the reply
    # ------------------------------------------------------------------
    print(f"\n=== [{support.config.name}] What can you help me with? ===")
    req = ChatRequest(
        messages="Hello! What topics can you help me with?",
        thread_id="support-thread",
    )
    chunks: list[str] = []
    async for chunk in manager.stream(support.agent_id, req):
        c = getattr(chunk, "content", None) or str(chunk)
        chunks.append(c)
        print(c, end="", flush=True)
    print()

    # ------------------------------------------------------------------
    # 4. Follow-up on the same thread (conversation history preserved)
    # ------------------------------------------------------------------
    print(f"\n=== [{support.config.name}] Follow-up on same thread ===")
    followup = ChatRequest(
        messages="Can you give me a one-sentence summary of that?",
        thread_id="support-thread",  # same thread → context carries over
    )
    async for chunk in manager.stream(support.agent_id, followup):
        print(getattr(chunk, "content", None) or str(chunk), end="", flush=True)
    print()

    # ------------------------------------------------------------------
    # 5. Route a different question to the analyst agent
    # ------------------------------------------------------------------
    print(f"\n=== [{analyst.config.name}] A quick data question ===")
    data_req = ChatRequest(
        messages="In one sentence: what is the difference between mean and median?",
        thread_id="analyst-thread",
    )
    async for chunk in manager.stream(analyst.agent_id, data_req):
        print(getattr(chunk, "content", None) or str(chunk), end="", flush=True)
    print()

    # ------------------------------------------------------------------
    # 6. Cancel a stream mid-flight
    # ------------------------------------------------------------------
    print("\n=== Cancel demo: stop after first meaningful chunk ===")
    cancel_req = ChatRequest(
        messages="List the numbers 1 through 50, one per line.",
        thread_id="cancel-thread",
    )
    received: list[str] = []
    async for chunk in manager.stream(analyst.agent_id, cancel_req):
        c = getattr(chunk, "content", None) or str(chunk)
        received.append(c)
        print(c, end="", flush=True)
        if len(received) >= 3:
            manager.cancel(analyst.agent_id, "cancel-thread")
    print(f"\n(cancelled after {len(received)} chunks)")

    # ------------------------------------------------------------------
    # 7. Remove the staging agent
    # ------------------------------------------------------------------
    manager.remove_agent(dev.agent_id)
    remaining = manager.list_agents()
    print(f"\n=== After removing '{dev.config.name}': {len(remaining)} agents remain ===")
    for e in remaining:
        print(f"  {e.config.name}")


if __name__ == "__main__":
    asyncio.run(main())
