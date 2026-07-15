"""Isolated simulation: real HarnessAgent (same workspace content + provider as agent 0E3ZZN)
delegates via task(subagent_type=academic-anthropologist), traced to local Langfuse.

Run:  .venv/bin/python sim_task_langfuse.py
"""

import asyncio
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

SCRATCH = Path(__file__).parent
SIM_WS = SCRATCH / "sim-workspace-0E3ZZN"
REAL_WS = Path.home() / ".octop/agents/0E3ZZN"

LANGFUSE_HOST = "http://localhost:3000"
LANGFUSE_PUBLIC = "pk-lf-octop-kr2-subagent"
LANGFUSE_SECRET = "sk-lf-octop-kr2-subagent"

os.environ["LANGFUSE_HOST"] = LANGFUSE_HOST
os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC
os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET


def prepare_workspace() -> None:
    if SIM_WS.exists():
        shutil.rmtree(SIM_WS)
    ignore = shutil.ignore_patterns(
        "memory.sqlite*", "checkpoints.sqlite*", "logs", "sessions", "*.log"
    )
    shutil.copytree(REAL_WS, SIM_WS, ignore=ignore)
    print(f"[ws] copied {REAL_WS} -> {SIM_WS}")


def load_provider():
    con = sqlite3.connect(f"file:{Path.home() / '.octop/octop.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM providers WHERE enabled=1").fetchone()
    models = json.loads(row["models_json"])
    return row, models


async def main() -> None:
    prepare_workspace()
    prow, models = load_provider()

    from harness_agent import HarnessAgent
    from harness_agent.config import HarnessAgentConfig, ModelConfig, ProviderConfig

    target_model = "glm-5.2"
    model_cfgs = [ModelConfig.from_dict(dict(m)) for m in models if m["id"] == target_model]
    provider = ProviderConfig(
        id=prow["name"],
        name=prow["name"],
        base_url=prow["base_url"],
        api_key=prow["api_key"],
        protocol="openai",
        models=model_cfgs,
    )

    cfg = HarnessAgentConfig(
        name="sim-0e3zzn",
        workspace_dir=SIM_WS,
        providers=[provider],
        default_model=f"{prow['name']}/{target_model}",
        system_prompt=None,  # matches DB row (empty) — parent prompt = base + memory files
        memory=None,  # default: scan workspace AGENTS.md / MEMORY.md etc., like the live agent
        checkpointer=False,
        bootstrap_enabled=True,  # .bootstrapped marker copied — bootstrap already done
        session_log_enabled=False,
    )
    agent = HarnessAgent(cfg)

    from langfuse import get_client
    from langfuse.langchain import CallbackHandler

    lf = get_client()
    print("[langfuse] auth ok:", lf.auth_check())
    agent.set_langfuse_callbacks([CallbackHandler(public_key=LANGFUSE_PUBLIC)])

    subs = agent.list_subagent_summaries()
    print("[subagents]", [s.get("name") for s in subs])

    prompt = (
        "请立即使用 task 工具，subagent_type 选 academic-anthropologist，"
        "任务：用不超过3句话解释什么是'文化相对主义'。"
        "拿到子智能体的回答后直接转发给我，不要自己另行作答。"
    )
    req = {
        "messages": [{"role": "user", "content": prompt}],
        "thread_id": "sim-kr2-trace-1",
        "metadata": {
            "langfuse_session_id": "sim-kr2-trace-1",
            "langfuse_user_id": "sim",
            "agent_id": "sim-0e3zzn",
        },
    }

    print("[stream] sending turn ...")
    n_chunks = 0
    async for chunk in agent.stream(req):
        n_chunks += 1
        if isinstance(chunk, dict) and chunk.get("type") == "token":
            sys.stdout.write(str(chunk.get("content") or ""))
            sys.stdout.flush()
    print(f"\n[stream] done, {n_chunks} chunks")

    lf.flush()
    await asyncio.sleep(3)
    print("[langfuse] flushed")


if __name__ == "__main__":
    asyncio.run(main())
