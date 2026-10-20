# pylint: disable=invalid-name
"""Demo: optional web-search built-in tools.

Walks through the four configuration policies for
``HarnessAgentConfig.web_search_tools`` and shows what each one yields.

    1. ``False`` (default) — no web-search tool exposed to the model.
    2. ``"auto"`` — every provider whose env vars are set is auto-loaded.
    3. ``["tavily", "kimi"]`` — explicit allow-list, with strict env-var
       validation at construction time.
    4. ``"all"`` — debugging mode; every provider is registered, the
       ones missing env vars return a plain-text error on invocation.

We do NOT make real Tavily / Brave / Google / Kimi network calls in
this demo: each script run prints whether the tool would be available
given the current shell environment, plus a short demonstration of the
error-handling path.

Run with::

    uv run python examples/08_web_search_tools.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from octop_harness import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.builtin.tools.web_search import load_web_search_tools
from octop_harness.builtin.tools.web_search._registry import WEB_SEARCH_PROVIDERS

_ENV_LABELS = {
    "tavily": ("TAVILY_API_KEY",),
    "brave": ("BRAVE_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GOOGLE_CSE_ID"),
    "kimi": ("MOONSHOT_API_KEY",),
    "searchfree": (),  # zero-config public fallback
}


def _heading(label: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n {label}\n{bar}")


def _names(tools: list[Any]) -> list[str]:
    return [t.name for t in tools]


def _print_env_state() -> None:
    print("environment status (which providers are configured?):")
    for name, env_vars in _ENV_LABELS.items():
        if not env_vars:
            status = "✅ ready (zero-config)"
        else:
            missing = [v for v in env_vars if not os.environ.get(v)]
            status = "✅ ready" if not missing else f"❌ missing {', '.join(missing)}"
        print(f"  {name:11s} {status}")


def scenario_off() -> None:
    _heading("Scenario 1: web_search_tools=False (default)")
    root = Path("./web_search_demo").absolute()
    cfg = HarnessAgentConfig(
        workspace_dir=root,
        providers=[
            ProviderConfig(
                id="p",
                base_url="http://x",
                api_key="x",
                models=[ModelConfig(id="m", input=["text"])],
            ),
        ],
    )
    print(f"config.web_search_tools = {cfg.web_search_tools!r}")
    print(f"loader output           = {_names(load_web_search_tools(cfg.web_search_tools))}")


def scenario_auto() -> None:
    _heading("Scenario 2: web_search_tools='auto' (env-driven)")
    _print_env_state()
    tools = load_web_search_tools("auto")
    print(f"\nloaded tools: {_names(tools) or '(none — set at least one API key in .env)'}")


def scenario_explicit_list() -> None:
    _heading("Scenario 3: web_search_tools=['tavily', 'kimi'] (strict)")
    try:
        tools = load_web_search_tools(["tavily", "kimi"])
        print(f"loaded: {_names(tools)}")
    except RuntimeError as exc:
        print("RuntimeError raised at construction time (expected when keys are missing):")
        print(f"  {exc}")


def scenario_all_with_runtime_error() -> None:
    _heading("Scenario 4: web_search_tools='all' (lenient)")
    tools = load_web_search_tools("all")
    print(f"every provider registered: {_names(tools)}")
    print("\nrunning each tool — providers without env vars return an Error:")
    for tool in tools:
        try:
            result = asyncio.run(tool.ainvoke({"query": "hello"}))
        except DEFENSIVE_OP_ERRORS as exc:  # pragma: no cover - defensive demo
            result = f"(exception) {type(exc).__name__}: {exc}"
        snippet = result.splitlines()[0] if isinstance(result, str) else str(result)
        if len(snippet) > 100:
            snippet = snippet[:97] + "…"
        print(f"  {tool.name:16s} → {snippet}")


def main() -> None:
    load_dotenv()
    print(f"providers known to the registry: {sorted(WEB_SEARCH_PROVIDERS)}\n")
    scenarios = [
        ("01_off", scenario_off),
        ("02_auto", scenario_auto),
        ("03_explicit", scenario_explicit_list),
        ("04_all", scenario_all_with_runtime_error),
    ]
    failures = 0
    for name, fn in scenarios:
        try:
            fn()
        except DEFENSIVE_OP_ERRORS as exc:
            failures += 1
            print(f"[!] scenario {name} raised: {type(exc).__name__}: {exc}")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
