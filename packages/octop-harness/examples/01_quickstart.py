# pylint: disable=invalid-name
"""Quickstart: single agent via HarnessAgentManager.

Demonstrates the recommended entry point for octop-harness:

- Provider config auto-detected from environment variables (no code changes needed)
- ``AgentManager`` as the single coordination layer
- ``invoke()`` for one-shot calls
- ``stream()`` for streaming responses
- Follow-up on the same ``thread_id`` (conversation history preserved)

Supported environment variables::

    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME
    HARNESS_PROVIDER_<NAME>_API_KEY / _BASE_URL
    DEEPSEEK_API_KEY  (or any other known provider key)

Run with::

    uv run python examples/01_quickstart.py
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


async def main() -> None:
    load_dotenv()

    root = Path("./agent_root").absolute()
    root.mkdir(parents=True, exist_ok=True)

    # --- Build config from environment variables (zero explicit provider setup)
    config = HarnessAgentConfig.from_env(
        workspace_dir=root,
        name="quickstart-agent",
        backend={"type": "filesystem", "root_dir": str(root), "virtual_mode": True},
    )

    # --- Create the manager and register the agent
    manager = HarnessAgentManager()
    entry = manager.create_agent(
        config,
        metadata={"demo": "quickstart"},
        tags=["quickstart"],
    )
    print(f"Agent registered: {entry.agent_id[:8]}  name={entry.config.name!r}")

    # --- 1) One-shot streaming call
    print("\n--- What's the current time? ---")
    request = ChatRequest(
        messages="What's the current time?",
        thread_id="qs-thread",
    )
    async for chunk in manager.stream(entry.agent_id, request):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()

    # --- 2) Follow-up on the same thread (conversation history preserved)
    print("\n--- Follow-up: And in Tokyo? ---")
    followup = ChatRequest(
        messages="And what time is it in Tokyo right now?",
        thread_id="qs-thread",  # same thread_id → context carries over
        user="alice",
    )
    async for chunk in manager.stream(entry.agent_id, followup):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
