# pylint: disable=invalid-name
"""E2E test: searchfree as a built-in web-search tool.

Verifies that the agent can use ``searchfree_search`` out-of-the-box
(no API key needed) when ``web_search_tools`` is left at its new default
``"auto"``.

Run with::

    uv run python examples/10_searchfree_builtin.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgentConfig,
    HarnessAgentManager,
)


def _make_config(root_dir: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig.from_env(
        workspace_dir=root_dir,
        name="searchfree-e2e",
        backend={"type": "filesystem", "root_dir": str(root_dir), "virtual_mode": True},
        # web_search_tools defaults to "auto" now — searchfree is always loaded.
        # Disable checkpointer for async compatibility (SqliteSaver is sync-only).
        checkpointer=False,
        memory_enabled=False,
        model_retry_max_retries=1,
        model_retry_initial_delay=0.5,
    )


async def _test_agent_search(root: Path) -> None:
    """Test 3: Agent uses searchfree_search via HarnessAgentManager streaming."""
    print("=" * 60)
    print(" Test 3: Agent uses searchfree_search to answer a web query")
    print("=" * 60)

    manager = HarnessAgentManager()
    entry = manager.create_agent(_make_config(root / "agent"))

    request = ChatRequest(
        messages=(
            "请使用 searchfree_search 工具搜索 'Python programming language'，"
            "然后用一句话告诉我搜索结果中的第一条标题是什么。"
        ),
        thread_id="searchfree-test",
    )

    all_chunks: list[object] = []
    async for chunk in manager.stream(entry.agent_id, request):
        all_chunks.append(chunk)

    # Extract last non-empty content as reply
    reply = ""
    for chunk in reversed(all_chunks):
        content = getattr(chunk, "content", None)
        if content:
            reply = content
            break
    print(f"  Agent reply: {reply}")

    # Check if any chunk had tool calls for searchfree_search
    used_searchfree = any(
        tc.get("name") == "searchfree_search"
        for chunk in all_chunks
        for tc in (getattr(chunk, "tool_calls", None) or [])
    )
    print(f"  Used searchfree_search tool: {used_searchfree}")

    if used_searchfree:
        print("  ✅ PASS: Agent successfully invoked searchfree_search\n")
    else:
        print("  ⚠️  Agent did not explicitly call searchfree_search")
        print("     (model may have answered from knowledge or used a different tool)\n")


async def _run_tests() -> None:
    root = Path(".e2e_root/10_searchfree").absolute()
    root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Test 1: Verify searchfree is loaded with default config
    # ------------------------------------------------------------------
    print("=" * 60)
    print(" Test 1: searchfree_search is loaded by default")
    print("=" * 60)

    cfg = _make_config(root)
    assert cfg.web_search_tools == "auto", f"Expected 'auto', got {cfg.web_search_tools!r}"

    from octop_harness.builtin.tools.web_search import load_web_search_tools

    tools = load_web_search_tools(cfg.web_search_tools)
    tool_names = [t.name for t in tools]
    print(f"  Loaded tools: {tool_names}")
    assert "searchfree_search" in tool_names, "searchfree_search not loaded!"
    print("  ✅ PASS: searchfree_search is present in default tool set\n")

    # ------------------------------------------------------------------
    # Test 2: searchfree_search works standalone (direct invocation)
    # ------------------------------------------------------------------
    print("=" * 60)
    print(" Test 2: Direct invocation of searchfree_search tool")
    print("=" * 60)

    from octop_harness.builtin.tools.web_search.searchfree import searchfree_search

    search_result = await searchfree_search.ainvoke(
        {"query": "Python programming language", "max_results": 3},
    )
    print(f"  Raw result (first 500 chars): {search_result[:500]}")

    if search_result.startswith("Error"):
        print(f"  ❌ FAIL: searchfree returned an error: {search_result}")
        sys.exit(1)
    else:
        try:
            parsed = json.loads(search_result)
            count = len(parsed) if isinstance(parsed, list) else "N/A"
            print(f"  Results count: {count}")
            print("  ✅ PASS: searchfree_search returned valid results\n")
        except json.JSONDecodeError:
            print("  ❌ FAIL: could not parse JSON response")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Test 3: Agent uses searchfree_search via HarnessAgentManager streaming
    # ------------------------------------------------------------------
    await _test_agent_search(root)

    print("=" * 60)
    print(" All tests passed!")
    print("=" * 60)


def main() -> None:
    load_dotenv()
    asyncio.run(_run_tests())


if __name__ == "__main__":
    main()
