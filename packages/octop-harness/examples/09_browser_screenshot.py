# pylint: disable=invalid-name
"""Demo: drive a real Chrome browser via the ``browser_use`` built-in tool.

Three run modes:

1. **Direct** (default) -- call :func:`octop_browser.browser_tool` end
   to end: open https://cloud.tencent.com, take a screenshot, save it
   under ``$TMPDIR/tencent_cloud.png``. No LLM keys needed, just Chrome.

2. **Wrapper** (``--wrapper``) -- same task via the octop-harness
   ``browser_use`` LLM-tool wrapper. Demonstrates per-profile
   ``action_history`` and the multimodal ``[image_block, text_block]``
   screenshot return value.

3. **Agent** (``--agent``) -- feed the same task to a HarnessAgent that
   has ``browser_use`` registered as a tool, so the model itself decides
   to call ``browser_use(action="navigate", ...)`` then
   ``browser_use(action="screenshot", ...)``. Reads model config from env
   (``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` / ``OPENAI_MODEL_NAME``).

This example DOES launch a real Chromium session, so:

    pip install octop-harness     # octop-browser ships by default
    sudo apt install chromium-browser     # or brew install chromium

Run::

    uv run python examples/09_browser_screenshot.py
    uv run python examples/09_browser_screenshot.py --wrapper
    OPENAI_API_KEY=... uv run python examples/09_browser_screenshot.py --agent
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgent,
    HarnessAgentConfig,
    HarnessAgentManager,
)
from octop_harness.builtin.tools import browser_use

TARGET_URL = "https://cloud.tencent.com"
SCREENSHOT_PATH = Path(tempfile.gettempdir()) / "tencent_cloud.png"
PROFILE = "demo-tencent-cloud"


async def run_direct() -> int:
    """Drive ``octop_browser.browser_tool`` directly — no LLM involved."""
    try:
        from octop_browser import browser_tool
    except ImportError:
        print(
            "ERROR: octop-browser is not installed. It ships as a "
            "default dependency of octop-harness — reinstall the "
            "package, or run `pip install octop-browser` directly.",
            file=sys.stderr,
        )
        return 1

    print(f"→ navigating to {TARGET_URL}")
    nav = await browser_tool(action="navigate", url=TARGET_URL, profile=PROFILE)
    if not nav.success:
        print(f"navigate failed: {nav.error}", file=sys.stderr)
        await browser_tool(action="close_session", profile=PROFILE)
        return 2

    print("→ capturing screenshot")
    shot = await browser_tool(
        action="screenshot",
        profile=PROFILE,
        full_page=True,
        path=str(SCREENSHOT_PATH),
    )
    await browser_tool(action="close_session", profile=PROFILE)

    if not shot.success:
        print(f"screenshot failed: {shot.error}", file=sys.stderr)
        return 3

    saved = shot.content if isinstance(shot.content, str) else SCREENSHOT_PATH
    size_kb = shot.metrics.screenshot_size_kb
    print(f"✅ saved {saved}  ({size_kb} KB)")
    if isinstance(shot.metadata, dict):
        for key in ("url", "title", "full_page"):
            if key in shot.metadata:
                print(f"   {key}: {shot.metadata[key]}")
    return 0


async def run_via_wrapper() -> int:
    """Exercise the octop-harness ``browser_use`` tool wrapper.

    Demonstrates the two ergonomic features layered on top of
    ``octop_browser.browser_tool``: per-profile ``action_history`` and
    multimodal screenshot blocks.
    """
    print(f"→ navigate to {TARGET_URL} (via browser_use wrapper)")
    nav_raw = await browser_use.ainvoke({"action": "navigate", "url": TARGET_URL, "profile": PROFILE})
    if not isinstance(nav_raw, str):
        print(f"unexpected navigate result: {nav_raw!r}", file=sys.stderr)
        return 2
    nav = json.loads(nav_raw)
    if not nav["success"]:
        print(f"navigate failed: {nav.get('error')}", file=sys.stderr)
        await browser_use.ainvoke({"action": "close_session", "profile": PROFILE})
        return 2
    print(f"   action_history: {nav['action_history']}")

    print("→ screenshot (multimodal blocks)")
    shot = await browser_use.ainvoke(
        {
            "action": "screenshot",
            "profile": PROFILE,
            "full_page": True,
            "path": str(SCREENSHOT_PATH),
        }
    )
    await browser_use.ainvoke({"action": "close_session", "profile": PROFILE})

    if not isinstance(shot, list):
        # Failure path: wrapper falls back to JSON envelope.
        print(f"screenshot failed: {shot}", file=sys.stderr)
        return 3

    image_block, text_block = shot
    print("✅ multimodal result:")
    print(f"   image: type={image_block['type']} url={image_block['source']['url']}")
    print("   summary:")
    for line in text_block["text"].splitlines():
        print(f"     {line}")
    return 0


async def run_with_agent() -> int:
    """Let the LLM choose to call ``browser_use`` for navigation + screenshot."""
    root = Path("./agent_root").absolute()
    config = HarnessAgentConfig.from_env(
        workspace_dir=root,
        name="browser-screenshot-agent",
        # Sandbox the filesystem to the demo dir so the agent's grep/ls tools
        # don't recurse into ``/`` on the default ``local_shell`` backend.
        backend={"type": "filesystem", "root_dir": str(root), "virtual_mode": True},
        # ``browser_use`` is async-only, so we drive the agent via streaming
        # below. The default sync ``SqliteSaver`` checkpointer can't be used
        # from an async runtime — disable it (``False``) and skip persistence
        # for this short demo.
        checkpointer=False,
        tools=[browser_use],
    )

    # Direct HarnessAgent access for workspace initialization (AgentManager doesn't expose these)
    agent = HarnessAgent(config)
    agent.init_workspace()

    prompt = (
        f"Use the browser_use tool to open {TARGET_URL} (profile='{PROFILE}'), "
        f"then take a full_page screenshot saved to '{SCREENSHOT_PATH}'. "
        "Finally call browser_use with action='close_session' on the same "
        "profile. Report the saved path and the screenshot size in KB."
    )
    req = ChatRequest(messages=prompt, thread_id="browser-screenshot-demo")

    manager = HarnessAgentManager()
    entry = manager.create_agent(config)

    all_chunks: list[object] = []
    async for chunk in manager.stream(entry.agent_id, req):
        all_chunks.append(chunk)

    print("\n--- Agent reply ---")
    last_content = ""
    for chunk in reversed(all_chunks):
        content = getattr(chunk, "content", None)
        if content:
            last_content = content
            break
    print(last_content)

    # Surface the tool calls so users can see what the agent actually did.
    print("\n--- Tool calls ---")
    for chunk in all_chunks:
        for call in getattr(chunk, "tool_calls", None) or []:
            args = json.dumps(call.get("args", {}), ensure_ascii=False)
            print(f"  {call.get('name')}({args})")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Run via HarnessAgent + LLM tool-calling (requires OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--wrapper",
        action="store_true",
        help="Exercise the browser_use tool wrapper directly (multimodal output, action_history).",
    )
    args = parser.parse_args()

    if args.agent:
        return asyncio.run(run_with_agent())
    if args.wrapper:
        return asyncio.run(run_via_wrapper())
    return asyncio.run(run_direct())


if __name__ == "__main__":
    sys.exit(main())
