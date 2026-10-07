"""Octop-owned built-in Skills seeded into every agent workspace."""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

OCTOP_BUILTIN_SKILLS_ROOT = "_builtin_skills"
RETIRED_BUILTIN_SKILLS = ("install-skill",)
_WORKSPACE_TOKEN = b"{{OCTOP_WORKSPACE}}"
_SKILLS_TOKEN = b"{{OCTOP_SKILLS}}"
_BUILTIN_TOKEN = b"{{OCTOP_BUILTIN_SKILLS}}"
_PACKAGE = "octop.infra.agents.builtin_skills"


def normalize_workspace_rel(rel: str) -> str:
    """Collapse ``.`` and ``x/../`` spellings of a workspace-relative path.

    ``..`` is clamped at the workspace root: an escaping fragment is the backend's
    problem to reject, and collapsing it here would let an escape attempt read as an
    unrelated in-workspace path.
    """
    parts: list[str] = []
    for part in str(rel).replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def is_octop_builtin_skills_path(rel: str) -> bool:
    """True for workspace-relative paths inside the Octop-owned built-in Skills root.

    Compares the normalized path, so ``./_builtin_skills/x`` and
    ``docs/../_builtin_skills/x`` are recognized like ``_builtin_skills/x``: the
    backend resolves those fragments before writing, and this predicate is what
    tells Octop-owned files apart from user files in the workspace API and in
    backup import. Two roots are checked: the API name, and the ``.octop/``
    prefixed system location newer agents keep it in.
    """
    posix = normalize_workspace_rel(rel)
    for prefix in (OCTOP_BUILTIN_SKILLS_ROOT, f".octop/{OCTOP_BUILTIN_SKILLS_ROOT}"):
        if posix == prefix or posix.startswith(f"{prefix}/"):
            return True
    return False


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

    # Render the agent-facing workspace path into the instructions (not the
    # host ``root_dir`` join that ``resolve_path`` returns for I/O).
    from octop.infra.gateway.media.inbound_store import (  # noqa: PLC0415
        agent_facing_workspace_path,
    )

    workspace_path = agent_facing_workspace_path(workspace, ".").encode("utf-8")
    skills_rel = workspace.system_rel("skills")
    builtin_rel = workspace.system_rel(OCTOP_BUILTIN_SKILLS_ROOT)
    skills_path = agent_facing_workspace_path(workspace, skills_rel).encode("utf-8")
    builtin_path = agent_facing_workspace_path(workspace, builtin_rel).encode("utf-8")
    uploads = [
        (
            path,
            data.replace(_WORKSPACE_TOKEN, workspace_path)
            .replace(_SKILLS_TOKEN, skills_path)
            .replace(_BUILTIN_TOKEN, builtin_path),
        )
        for path, data in uploads
    ]

    if uploads:
        await workspace.aupload_many(uploads)

    for name in RETIRED_BUILTIN_SKILLS:
        path = f"{OCTOP_BUILTIN_SKILLS_ROOT}/{name}"
        if await workspace.aexists(path):
            await workspace.adelete(path)
    return sorted(skill_names)


__all__ = [
    "OCTOP_BUILTIN_SKILLS_ROOT",
    "is_octop_builtin_skills_path",
    "normalize_workspace_rel",
    "sync_octop_builtin_skills",
]
