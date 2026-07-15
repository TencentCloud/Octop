"""Benchmark: subagent scan/parse + deepagents graph compile on the real workspace."""

import statistics
import time
from pathlib import Path

WS = Path.home() / ".octop/agents/0E3ZZN"

from harness_agent.backends import resolve_backend
from harness_agent.backends.workspace import BackendWorkspace
from harness_agent.subagents.loader import (
    collect_agent_markdown_paths,
    load_subagents_from_workspace,
)

backend = resolve_backend(None, workspace_dir=WS)
ws = BackendWorkspace(backend, WS)


def timeit(fn, n=3):
    runs = []
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        runs.append(time.perf_counter() - t0)
    return out, statistics.median(runs)


# 1. scan (recursive list_dir)
paths, t_scan = timeit(lambda: collect_agent_markdown_paths(ws, "agents"))
print(f"[1] scan agents/**/*.md         : {t_scan*1000:8.1f} ms  ({len(paths)} files)")

# 2. scan + read + YAML parse (no tools resolution)
specs, t_parse = timeit(lambda: load_subagents_from_workspace(ws))
print(f"[2] scan+read+parse specs       : {t_parse*1000:8.1f} ms  ({len(specs)} specs)")

# size of context payload: task tool description lines + subagent bodies
desc_chars = sum(len(s["name"]) + len(s["description"]) + 4 for s in specs)
body_chars = sum(len(s.get("system_prompt", "")) for s in specs)
print(f"    task-tool description size : {desc_chars} chars (~{desc_chars//4} tokens) — sent EVERY parent turn")
print(f"    subagent bodies total      : {body_chars} chars (~{body_chars//4} tokens) — loaded only on task() call")

# 3. deepagents compile with fake model: with vs without subagents
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.tools import tool


@tool
def dummy_tool(x: str) -> str:
    """A dummy tool."""
    return x


def make_model():
    return GenericFakeChatModel(messages=iter([]))


import deepagents

for spec in specs:
    spec["model"] = make_model()
    spec["tools"] = [dummy_tool]

_, t_bare = timeit(
    lambda: deepagents.create_deep_agent(model=make_model(), tools=[dummy_tool], checkpointer=False), n=3
)
print(f"[3] create_deep_agent, 0 subagents : {t_bare*1000:8.1f} ms")

_, t_full = timeit(
    lambda: deepagents.create_deep_agent(
        model=make_model(), tools=[dummy_tool], subagents=specs, checkpointer=False
    ),
    n=3,
)
print(f"[4] create_deep_agent, {len(specs)} subagents: {t_full*1000:8.1f} ms")
print(f"    → per-subagent compile cost : {(t_full-t_bare)/max(len(specs),1)*1000:6.1f} ms")
print(f"    → one _init_graph ≈ scan({t_parse*1000:.0f}) + compile({t_full*1000:.0f}) ms; agent start does this ≥2×")
