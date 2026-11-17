"""Managed agents: an ACP runner addressed like any other expert."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop.infra.errors import ErrorCode, OctopError

_SEED_DIR = Path(__file__).with_name("managed_seed")

MANAGED_KIND = "managed"

MANAGED_BACKEND: dict[str, Any] = {
    "type": "filesystem",
    "root_dir": "/",
    "virtual_mode": True,
}


def is_managed_agent(row: Any) -> bool:
    return getattr(row, "kind", None) == MANAGED_KIND


def apply_managed_backend(config: dict[str, Any]) -> None:
    """Pin storage to the local filesystem root. The user picks the workspace."""
    config["backend"] = dict(MANAGED_BACKEND)


def pin_managed_runtime(config: dict[str, Any]) -> None:
    """Drop expert-only runtime knobs. The ACP runner owns the turn."""
    config.pop("conversation_mode", None)
    memory = config.get("memory")
    section = dict(memory) if isinstance(memory, dict) else {}
    section["memory_enabled"] = False
    section["memory_capture_enabled"] = False
    section["memory_recall_inject_enabled"] = False
    config["memory"] = section


def require_managed_fields(config: dict[str, Any]) -> None:
    runner = config.get("managed_runner")
    if not isinstance(runner, str) or not runner.strip():
        raise OctopError(ErrorCode.NOT_FOUND, "managed agent requires an ACP runner", status=400)
    workspace = config.get("workspace_dir")
    if not isinstance(workspace, str) or not workspace.strip():
        raise OctopError(
            ErrorCode.WORKSPACE_OP_UNSUPPORTED,
            "managed agent requires a working directory",
        )


def managed_default_workspace(agent_id: str) -> str:
    """``{home}/{agent_id}`` on the machine that runs Octop."""
    return str(Path.home() / agent_id.strip())


# Project directory each ACP agent already uses. Skills are ``{root}/skills``,
# subagents are ``{root}/agents`` — the same layout Octop uses under ``.octop``.
_RUNNER_PROJECT_ROOTS: dict[str, str] = {
    "codebuddy": ".codebuddy",
    "claude_code": ".claude",
    "opencode": ".opencode",
    "codex": ".codex",
    "cursor_cli": ".cursor",
    "kimi_code": ".kimi",
    "pi": ".pi",
}
_DEFAULT_PROJECT_ROOT = ".octop"


def managed_project_root(runner: str) -> str:
    """Workspace-relative directory that runner keeps its own project files in."""
    return _RUNNER_PROJECT_ROOTS.get(runner.strip(), _DEFAULT_PROJECT_ROOT)


def managed_skill_dir(runner: str) -> str:
    return f"{managed_project_root(runner)}/skills"


def managed_subagent_dir(runner: str) -> str:
    return f"{managed_project_root(runner)}/agents"


def managed_template_payload() -> dict[str, Any]:
    """Welcome cards and prompt files copied into a new managed workspace."""
    manifest = json.loads((_SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    prompts = manifest.get("quick_prompts")
    files = [
        {"name": "AGENTS.md", "content": (_SEED_DIR / "AGENTS.md").read_text(encoding="utf-8")}
    ]
    return {
        "files": files,
        "quick_prompts": prompts if isinstance(prompts, list) else [],
        "home": str(Path.home()),
    }


async def seed_managed_workspace(
    workspace: Any,
    *,
    agents_md: str | None = None,
    quick_prompts: list[dict[str, Any]] | None = None,
) -> None:
    """Copy ``AGENTS.md`` when the project does not already have one.

    An existing file is left in place unless the form sent a replacement.
    Welcome cards merge into ``{system dir}/manifest.json``. Skills and subagents
    stay in the ACP agent's own project directory and are not seeded here.
    """
    from octop.infra.agents.experts.catalog import (  # noqa: PLC0415
        apply_workspace_quick_prompts,
        workspace_manifest_rel,
    )

    if agents_md is not None:
        await workspace.aupload_many([("AGENTS.md", agents_md.encode("utf-8"))])
    elif await workspace.aread_text("AGENTS.md") is None:
        content = (_SEED_DIR / "AGENTS.md").read_bytes()
        await workspace.aupload_many([("AGENTS.md", content)])

    manifest_path = workspace_manifest_rel(workspace)
    if await workspace.aread_text(manifest_path) is None:
        raw = (_SEED_DIR / "manifest.json").read_bytes()
        await workspace.aupload_many([(manifest_path, raw)])
    if quick_prompts is not None:
        await apply_workspace_quick_prompts(workspace, quick_prompts)


def preserve_managed_config(config: dict[str, Any], previous: dict[str, Any]) -> None:
    """Keep the ACP binding and filesystem root across later edits."""
    apply_managed_backend(config)
    pin_managed_runtime(config)
    runner = config.get("managed_runner")
    if not isinstance(runner, str) or not runner.strip():
        previous_runner = previous.get("managed_runner")
        if isinstance(previous_runner, str) and previous_runner.strip():
            config["managed_runner"] = previous_runner.strip()
