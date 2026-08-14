"""Octop-owned built-in Skills seeded into every agent workspace."""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

OCTOP_BUILTIN_SKILLS_ROOT = "_builtin_skills"
RETIRED_BUILTIN_SKILLS = ("install-skill",)
_WORKSPACE_TOKEN = b"{{OCTOP_WORKSPACE}}"
_PACKAGE = "octop.infra.agents.builtin_skills"


def _collect_files(source: Traversable, prefix: str, out: list[tuple[str, bytes]]) -> None:
    for entry in source.iterdir():
        if entry.name.startswith((".", "__")):
            continue
        path = f"{prefix}/{entry.name}"
        if entry.is_dir():
            _collect_files(entry, path, out)
        else:
            out.append((path, entry.read_bytes()))


async def sync_octop_builtin_skills(workspace: Any) -> list[str]:
    """Overwrite Octop-owned built-ins and remove superseded runtime copies."""
    # DeepAgents scans both roots on the first turn. Keep the writable root
    # present even before the user installs their first Skill so that scan is
    # clean on fresh expert instances.
    await workspace.amkdir("skills")

    package_root = resources.files(_PACKAGE)
    uploads: list[tuple[str, bytes]] = []
    skill_names: list[str] = []
    for entry in package_root.iterdir():
        if entry.name.startswith((".", "__")) or not entry.is_dir():
            continue
        if not entry.joinpath("SKILL.md").is_file():
            continue
        skill_names.append(entry.name)
        _collect_files(entry, f"{OCTOP_BUILTIN_SKILLS_ROOT}/{entry.name}", uploads)

    # Render the exact backend-visible workspace path into the instructions.
    # This prevents an agent from confusing Octop's per-expert workspace with
    # a legacy ~/.harness-agent/workspace directory discovered through HOME.
    workspace_path = workspace.resolve_path(".").encode("utf-8")
    uploads = [(path, data.replace(_WORKSPACE_TOKEN, workspace_path)) for path, data in uploads]

    if uploads:
        await workspace.aupload_many(uploads)

    for name in RETIRED_BUILTIN_SKILLS:
        path = f"{OCTOP_BUILTIN_SKILLS_ROOT}/{name}"
        if await workspace.aexists(path):
            await workspace.adelete(path)
    return sorted(skill_names)


__all__ = ["OCTOP_BUILTIN_SKILLS_ROOT", "sync_octop_builtin_skills"]
