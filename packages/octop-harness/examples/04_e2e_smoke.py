# pylint: disable=invalid-name
"""End-to-end smoke tests against a real LLM provider.

Reads ``OPENAI_*`` from ``.env`` and exercises six scenarios:

    1. Plain chat                — verifies the agent talks to the model at all.
    2. Builtin tool (current_time) — verifies tool invocation works.
    3. Builtin tool (web_fetch)   — verifies network tool works.
    4. Workspace round-trip      — direct backend ops + agent reading file.
    5. Backend string config     — uses ``backend="local_shell"``.
    6. API-key redaction         — verifies a leaked key gets masked before
                                    reaching the model.

Run with::

    uv run python examples/04_e2e_smoke.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgentConfig,
    HarnessAgentManager,
)
from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS


def _make_config(
    *,
    root_dir: Path,
    backend: Any = None,
) -> HarnessAgentConfig:
    if backend is None:
        backend = {
            "type": "filesystem",
            "root_dir": str(root_dir),
            "virtual_mode": True,
        }

    return HarnessAgentConfig.from_env(
        workspace_dir=root_dir,
        name="e2e",
        backend=backend,
        # Keep retries snappy for a smoke test.
        model_retry_max_retries=1,
        model_retry_initial_delay=0.5,
    )


def _heading(label: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n {label}\n{bar}")


async def scenario_1_plain_chat(root_dir: Path) -> None:
    _heading("Scenario 1: plain chat")
    manager = HarnessAgentManager()
    entry = manager.create_agent(_make_config(root_dir=root_dir))
    async for chunk in manager.stream(entry.agent_id, ChatRequest(messages="用一句话介绍你自己。")):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


async def scenario_2_current_time(root_dir: Path) -> None:
    _heading("Scenario 2: builtin tool current_time")
    manager = HarnessAgentManager()
    entry = manager.create_agent(_make_config(root_dir=root_dir))
    async for chunk in manager.stream(
        entry.agent_id,
        ChatRequest(messages="现在的时间是什么？请用 current_time 工具回答。"),
    ):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


async def scenario_3_web_fetch(root_dir: Path) -> None:
    _heading("Scenario 3: builtin tool web_fetch")
    manager = HarnessAgentManager()
    entry = manager.create_agent(_make_config(root_dir=root_dir))
    async for chunk in manager.stream(
        entry.agent_id,
        ChatRequest(
            messages="请使用 web_fetch 工具抓取 https://example.com 的首页，然后用一句话告诉我页面的主标题是什么。",
        ),
    ):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


async def scenario_4_workspace_roundtrip(root_dir: Path) -> None:
    _heading("Scenario 4: workspace direct ops + agent read")

    # create() builds the agent and initialises the workspace in one step.
    manager = HarnessAgentManager()
    entry = manager.create_agent(_make_config(root_dir=root_dir))

    from octop_harness.backends.utils import backend_write_force

    # Access the cached agent's backend directly via entry.agent.
    backend_write_force(entry.agent.backend, "/hello.md", "# Hello\n\nThe magic word is Octop.")
    ls_result = entry.agent.backend.ls("/")
    entries_ls = getattr(ls_result, "entries", None) or []
    files = [e.get("path", "") if isinstance(e, dict) else getattr(e, "path", "") for e in entries_ls]
    print("workspace files:", files)

    async for chunk in manager.stream(
        entry.agent_id,
        ChatRequest(
            messages="我刚刚在 workspace 根目录下放了 hello.md。请用 read_file 读取它，然后告诉我 magic word 是什么。",
        ),
    ):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


async def scenario_5_backend_string_config(root_dir: Path) -> None:
    _heading("Scenario 5: backend='local_shell' (constructor only — no shell command)")
    # We pin root_dir to ``root_dir`` so we don't expose ``/`` here.
    cfg = _make_config(
        root_dir=root_dir,
        backend={"type": "local_shell", "root_dir": str(root_dir), "virtual_mode": True},
    )
    manager = HarnessAgentManager()
    entry = manager.create_agent(cfg)
    # Access backend type via the cached agent on entry.
    print("backend type:", type(entry.agent.backend).__name__)
    async for chunk in manager.stream(entry.agent_id, ChatRequest(messages="用一句话告诉我你能做什么。")):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


async def scenario_6_pii_redaction(root_dir: Path) -> None:
    _heading("Scenario 6: api key redaction")

    # Inspect what reaches the model after PIIMiddleware processes the input.
    fake_key = "sk-4b829b7b-b0aa-4064-8d53-FAKEFAKEFAKEFAKE"
    user_text = f"我的 API key 是 {fake_key}，请直接复述一遍。"

    manager = HarnessAgentManager()
    entry = manager.create_agent(_make_config(root_dir=root_dir))

    # Run as a streaming call so we see the full pipeline including session logger.
    reply_chunks: list[str] = []
    async for chunk in manager.stream(
        entry.agent_id,
        ChatRequest(messages=user_text, thread_id="redact-demo"),
    ):
        content = getattr(chunk, "content", None) or str(chunk)
        if content:
            reply_chunks.append(content)
            print(content, end="", flush=True)
    print()
    reply = "".join(reply_chunks)
    print("model reply:", reply)
    leaked = fake_key in reply
    print(f"key leaked into model reply? {leaked}")

    # And confirm the session log scrubbed it too.
    sessions = list((root_dir / "workspace" / "sessions").glob("*.jsonl"))
    if sessions:
        log_text = sessions[0].read_text()
        print(f"key leaked into session log? {fake_key in log_text}")
    else:
        print("(no session log produced)")


async def main() -> None:
    load_dotenv()

    base = Path(".e2e_root").absolute()
    base.mkdir(exist_ok=True)

    # Each scenario gets its own subdirectory so SqliteSaver / sessions don't collide.
    scenarios = [
        ("01_plain", scenario_1_plain_chat),
        ("02_time", scenario_2_current_time),
        ("03_web_fetch", scenario_3_web_fetch),
        ("04_workspace", scenario_4_workspace_roundtrip),
        ("05_backend_string", scenario_5_backend_string_config),
        ("06_redaction", scenario_6_pii_redaction),
    ]
    for sub, fn in scenarios:
        root = base / sub
        root.mkdir(exist_ok=True)
        try:
            await fn(root)
        except DEFENSIVE_OP_ERRORS as exc:
            print(f"[!] scenario {sub} raised: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
