# pylint: disable=invalid-name
"""Tencent Cloud COS backend end-to-end test.

Exercises five scenarios:

    1. Direct COS backend ops (write / read / edit / ls)
    2. Pure-COS HarnessAgent construction (no LLM call)
    3. CompositeBackend: ``/cos/`` → COS, default → ``local_shell`` (virtual)
    4. Full agent-with-LLM round trip using the composite backend
    5. Real filesystem mount: default → ``local_shell`` (non-virtual, real disk),
       ``/cos/`` → COS — verifies that local writes land on disk AND COS
       writes land in the bucket, both readable via the same composite handle.

Credentials are read from environment variables (``.env`` is loaded
automatically). Required:

    COS_BUCKET, COS_REGION, COS_SECRET_ID, COS_SECRET_KEY

Optional:

    COS_TOKEN                  — STS temporary token, if applicable.
    OPENAI_API_KEY             — enables scenario 4 (LLM round trip).
    OPENAI_BASE_URL            — custom OpenAI-compatible endpoint.
    OPENAI_MODEL_NAME          — model name for the custom endpoint.

Run with::

    uv run python examples/05_cos_backend.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

from octop_harness import (
    ChatRequest,
    HarnessAgent,
    HarnessAgentConfig,
    HarnessAgentManager,
)
from octop_harness.backends import resolve_backend
from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

# ---------------------------------------------------------------------------
# Credentials — read strictly from the environment (``.env`` is auto-loaded
# by ``load_dotenv()`` in ``main()``). Hard-coding credentials in source is
# a security anti-pattern, so we fail loudly instead.
# ---------------------------------------------------------------------------

_REQUIRED_ENV: tuple[str, ...] = (
    "COS_BUCKET",
    "COS_REGION",
    "COS_SECRET_ID",
    "COS_SECRET_KEY",
)

# Per-run prefix root, so repeated executions don't collide on the
# write-once semantics enforced by the backend (write of an existing path
# is rejected on purpose). Override with ``COS_RUN_ID`` to pin a value.
_RUN_ID = os.environ.get("COS_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")


def _require_cos_env() -> dict[str, str]:
    missing = [name for name in _REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            "Missing required COS environment variables: "
            f"{joined}.\n"
            "Set them in your shell or in a .env file at the project root. "
            "See .env.example for a template.",
        )
    return {name: os.environ[name] for name in _REQUIRED_ENV}


def _cos_spec(prefix: str) -> dict[str, object]:
    env = _require_cos_env()
    spec: dict[str, object] = {
        "type": "cos",
        "bucket": env["COS_BUCKET"],
        "region": env["COS_REGION"],
        "secret_id": env["COS_SECRET_ID"],
        "secret_key": env["COS_SECRET_KEY"],
        "prefix": f"smoke/{_RUN_ID}/{prefix}",
    }
    token = os.environ.get("COS_TOKEN")
    if token:
        spec["token"] = token
    return spec


def _heading(label: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}\n {label}\n{bar}")


# ---------------------------------------------------------------------------
# Scenario 1 — direct backend operations
# ---------------------------------------------------------------------------


def scenario_direct_backend() -> None:
    _heading("Scenario 1: COS backend direct write/read/ls/edit")
    backend = resolve_backend(_cos_spec("smoke/direct/"))
    print("backend type:", type(backend).__name__)

    write_result = backend.write("/hello.txt", "Hello from CosBackend — 你好！")
    if getattr(write_result, "error", None):
        raise RuntimeError(f"write failed: {write_result.error}")
    print("write OK:", getattr(write_result, "path", "<unknown>"))

    read_result = backend.read("/hello.txt")
    if getattr(read_result, "error", None):
        raise RuntimeError(f"read failed: {read_result.error}")
    file_data = read_result.file_data or {}
    print("read OK; content:", repr(file_data.get("content")))

    ls_result = backend.ls("/")
    if getattr(ls_result, "error", None):
        raise RuntimeError(f"ls failed: {ls_result.error}")
    entries = ls_result.entries or []
    print("ls OK; entries:")
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", "?")
        is_dir = entry.get("is_dir") if isinstance(entry, dict) else getattr(entry, "is_dir", False)
        size = entry.get("size") if isinstance(entry, dict) else getattr(entry, "size", "")
        print(f" - {path}  is_dir={is_dir}  size={size}")

    edit_result = backend.edit("/hello.txt", "Hello", "Hi")
    if getattr(edit_result, "error", None):
        raise RuntimeError(f"edit failed: {edit_result.error}")
    print(f"edit OK; occurrences={edit_result.occurrences}")
    verified = backend.read("/hello.txt").file_data or {}
    print("post-edit content:", repr(verified.get("content")))


# ---------------------------------------------------------------------------
# Scenario 2 — agent uses COS as its sole backend (no LLM call)
# ---------------------------------------------------------------------------


def scenario_agent_pure_cos(local_root: Path) -> None:
    _heading("Scenario 2: HarnessAgent backed entirely by COS")
    # Use HarnessAgentConfig.from_env() so provider/model are read from
    # OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME (same as other scenarios).
    config = HarnessAgentConfig.from_env(
        workspace_dir=local_root,
        name="cos-only",
        # ``workspace_dir`` controls the *local* path used for log files,
        # the SqliteSaver checkpoint, and built-in skills sync. The actual
        # file ops the agent performs go through ``backend``.
        backend=_cos_spec("smoke/agent/"),
        session_log_enabled=False,
    )
    # Direct HarnessAgent access for workspace/backend operations (AgentManager doesn't expose these)
    agent = HarnessAgent(config)
    print("backend type:", type(agent.backend).__name__)
    agent.init_workspace()

    from octop_harness.backends.utils import backend_write_force

    backend_write_force(agent.backend, "/from-agent.md", "# Greetings from octop-harness")
    print("agent.backend.ls('/'):")
    ls_result = agent.backend.ls("/")
    for f in getattr(ls_result, "entries", None) or []:
        print(f"  {f}")
    read_result = agent.backend.read("/from-agent.md")
    file_data = getattr(read_result, "file_data", {}) or {}
    content = file_data.get("content", "") if isinstance(file_data, dict) else ""
    print("read back:", content[:60], "...")


# ---------------------------------------------------------------------------
# Scenario 3 — Composite: /cos/ → COS, everything else → local_shell
# ---------------------------------------------------------------------------


def scenario_composite(local_root: Path) -> None:
    _heading("Scenario 3: composite backend (/cos/ → COS, rest → local_shell)")
    composite_spec: dict[str, object] = {
        "type": "composite",
        "default": {
            "type": "local_shell",
            "root_dir": str(local_root),
            "virtual_mode": True,
        },
        "routes": {
            "/cos/": _cos_spec("smoke/composite/"),
        },
    }
    backend = resolve_backend(composite_spec, workspace_dir=local_root)
    print("backend type:", type(backend).__name__)

    # Write to a path under /cos/ — should land in COS.
    cos_target = "/cos/note-from-composite.md"
    r1 = backend.write(cos_target, "# I live in COS\n\nRouted via CompositeBackend.")
    if getattr(r1, "error", None):
        raise RuntimeError(f"COS write failed: {r1.error}")
    print(f"wrote {cos_target} (→ COS)")

    # Write to a path *not* under /cos/ — should land on local disk.
    local_target = "/local-note.md"
    r2 = backend.write(local_target, "I live locally")
    if getattr(r2, "error", None):
        raise RuntimeError(f"local write failed: {r2.error}")
    print(f"wrote {local_target} (→ local_shell)")

    local_path = local_root / "local-note.md"
    print(f"local file exists at {local_path}? {local_path.is_file()}")
    if local_path.is_file():
        print(f"  contents: {local_path.read_text(encoding='utf-8')!r}")

    # Reading back from COS via composite.
    cos_read = backend.read(cos_target).file_data or {}
    print(f"read back from {cos_target}: {cos_read.get('content')!r}")

    # ls /cos/ should show only the COS-routed file.
    ls_cos = backend.ls("/cos/")
    print("ls /cos/:")
    for entry in ls_cos.entries or []:
        path = entry.get("path") if isinstance(entry, dict) else getattr(entry, "path", "?")
        print(" -", path)


# ---------------------------------------------------------------------------
# Scenario 4 — full end-to-end with real LLM and composite backend
# ---------------------------------------------------------------------------


async def scenario_agent_composite_with_llm(local_root: Path) -> None:
    _heading("Scenario 4: HarnessAgent + composite backend + real LLM")
    if "OPENAI_API_KEY" not in os.environ:
        print("(skipping — OPENAI_API_KEY not set)")
        return

    config = HarnessAgentConfig.from_env(
        workspace_dir=local_root,
        name="composite-agent",
        backend={
            "type": "composite",
            "default": {
                "type": "local_shell",
                "root_dir": str(local_root),
                "virtual_mode": True,
            },
            "routes": {
                "/cos/": _cos_spec("smoke/agent-composite/"),
            },
        },
        model_retry_max_retries=1,
        session_log_enabled=False,
    )

    # Direct HarnessAgent access for backend seeding (AgentManager doesn't expose these)
    agent = HarnessAgent(config)

    # Pre-seed a file in COS via the underlying backend (bypasses Workspace's
    # workspace-rooted boundary check, which is intentional — Workspace is
    # for files *inside* the workspace_dir).
    seed = agent.backend.write(
        "/cos/secret-note.md",
        "The orca says: hello from Tencent COS!",
    )
    if getattr(seed, "error", None):
        raise RuntimeError(f"could not seed COS: {seed.error}")
    print("seeded /cos/secret-note.md in COS")

    # For streaming, use HarnessAgentManager with the same config.
    manager = HarnessAgentManager()
    entry = manager.create_agent(config)
    async for chunk in manager.stream(
        entry.agent_id,
        ChatRequest(messages="请使用 read_file 工具读取 /cos/secret-note.md ，然后用一句话告诉我 orca 说了什么。"),
    ):
        content = getattr(chunk, "content", None) or str(chunk)
        print(content, end="", flush=True)
    print()


# ---------------------------------------------------------------------------
# Scenario 5 — real filesystem mount + /cos/ overlay
# ---------------------------------------------------------------------------


def scenario_real_fs_mount(local_root: Path) -> None:
    _heading("Scenario 5: real filesystem mount + /cos/ overlay")
    local_root.mkdir(parents=True, exist_ok=True)

    # default → local_shell with virtual_mode=True (maps /path → {local_root}/path)
    # /cos/  → COS backend
    composite_spec: dict[str, object] = {
        "type": "composite",
        "default": {
            "type": "local_shell",
            "root_dir": str(local_root),
            "virtual_mode": True,
        },
        "routes": {
            "/cos/": _cos_spec("smoke/real-fs/"),
        },
    }
    backend = resolve_backend(composite_spec, workspace_dir=local_root)
    print("backend type:", type(backend).__name__)

    # Write a file to the real local filesystem (path NOT under /cos/).
    local_target = "/disk-note.txt"
    r_local = backend.write(local_target, "I live on the real disk.")
    if getattr(r_local, "error", None):
        raise RuntimeError(f"local write failed: {r_local.error}")
    disk_path = local_root / "disk-note.txt"
    assert disk_path.is_file(), f"Expected real file at {disk_path}"
    print(f"local write OK — real file confirmed at {disk_path}")
    print(f"  content on disk: {disk_path.read_text(encoding='utf-8')!r}")

    # Write a file under /cos/ — should land in COS, NOT on disk.
    cos_target = "/cos/cloud-note.txt"
    r_cos = backend.write(cos_target, "I live in COS.")
    if getattr(r_cos, "error", None):
        raise RuntimeError(f"COS write failed: {r_cos.error}")
    # Confirm it's NOT on disk.
    would_be_path = local_root / "cos" / "cloud-note.txt"
    assert not would_be_path.exists(), f"COS file leaked to disk at {would_be_path}"
    print("COS write OK — file not present on local disk \u2713")

    # Read back from COS via the composite handle.
    r_read = backend.read(cos_target)
    if getattr(r_read, "error", None):
        raise RuntimeError(f"COS read back failed: {r_read.error}")
    cos_content = (r_read.file_data or {}).get("content", "")
    assert cos_content == "I live in COS.", f"Unexpected content: {cos_content!r}"
    print(f"COS read-back OK: {cos_content!r}")

    # ls /cos/ — should list the COS object.
    ls_cos = backend.ls("/cos/")
    cos_paths = [(e.get("path") if isinstance(e, dict) else getattr(e, "path", "?")) for e in (ls_cos.entries or [])]
    assert any("/cos/cloud-note.txt" in p for p in cos_paths), (
        f"/cos/cloud-note.txt not found in ls result: {cos_paths}"
    )
    print("ls /cos/ OK:", cos_paths)

    # ls / (root) — should list the local file.
    ls_root = backend.ls("/")
    root_paths = [(e.get("path") if isinstance(e, dict) else getattr(e, "path", "?")) for e in (ls_root.entries or [])]
    assert any("disk-note.txt" in p for p in root_paths), f"disk-note.txt not found in root ls: {root_paths}"
    print("ls / OK:", root_paths)


async def main() -> None:
    load_dotenv()
    # Per-run local workspace, mirroring ``_RUN_ID`` so repeat executions
    # don't collide on the local_shell backend's write-once semantics.
    local_root = (Path(".cos_e2e_root") / _RUN_ID).absolute()
    local_root.mkdir(parents=True, exist_ok=True)
    print(f"COS run-id: smoke/{_RUN_ID}/  (override with COS_RUN_ID)")
    print(f"local root: {local_root}")

    sync_scenarios: list[tuple[str, Callable[[], None]]] = [
        ("01_direct", scenario_direct_backend),
        (
            "02_pure_cos",
            lambda: scenario_agent_pure_cos(local_root / "02_pure_cos"),
        ),
        (
            "03_composite",
            lambda: scenario_composite(local_root / "03_composite"),
        ),
        (
            "05_real_fs_mount",
            lambda: scenario_real_fs_mount(local_root / "05_real_fs"),
        ),
    ]
    failures = 0
    for name, fn in sync_scenarios:
        try:
            fn()
        except DEFENSIVE_OP_ERRORS as exc:
            failures += 1
            print(f"[!] scenario {name} raised: {type(exc).__name__}: {exc}")

    try:
        await scenario_agent_composite_with_llm(local_root / "04_composite_llm")
    except DEFENSIVE_OP_ERRORS as exc:
        failures += 1
        print(f"[!] scenario 04_composite_llm raised: {type(exc).__name__}: {exc}")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
