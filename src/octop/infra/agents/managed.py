"""Managed agents: an ACP runner addressed like any other expert."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).with_name("managed_seed")

MANAGED_KIND = "managed"

MANAGED_BACKEND: dict[str, Any] = {
    "type": "filesystem",
    "root_dir": "/",
    "virtual_mode": True,
}


def is_managed_agent(row: Any) -> bool:
    return getattr(row, "kind", None) == MANAGED_KIND


def read_managed_permission_mode(config: dict[str, Any] | None) -> str:
    """``yolo`` when this expert was created to skip approval. Otherwise ``ask``."""
    if isinstance(config, dict) and config.get("managed_permission_mode") == "yolo":
        return "yolo"
    return "ask"


def apply_managed_backend(config: dict[str, Any]) -> None:
    """Pin storage to the local filesystem root. The user picks the workspace."""
    config["backend"] = dict(MANAGED_BACKEND)


def pin_managed_runtime(config: dict[str, Any], *, previous: dict[str, Any] | None = None) -> None:
    """Drop expert-only runtime knobs. Memory stays off unless this expert enables it."""
    config.pop("conversation_mode", None)
    memory = config.get("memory")
    if isinstance(memory, dict):
        section = dict(memory)
    else:
        prior = (previous or {}).get("memory")
        section = dict(prior) if isinstance(prior, dict) else {}
    section.setdefault("memory_enabled", False)
    section.setdefault("memory_capture_enabled", False)
    section.setdefault("memory_recall_inject_enabled", False)
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


def _owned_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _known_skill_dirs(workspace: Path) -> list[Path]:
    roots = set(_RUNNER_PROJECT_ROOTS.values())
    roots.add(_DEFAULT_PROJECT_ROOT)
    return [workspace / f"{root}/skills" for root in sorted(roots)]


def _load_skill_manifest(path: Path) -> tuple[str, list[str]]:
    if not path.is_file():
        return "", []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", []
    if isinstance(raw, list):
        return "", [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, dict):
        runner = str(raw.get("runner") or "").strip()
        links = raw.get("links")
        if isinstance(links, list):
            return runner, [str(item) for item in links if str(item).strip()]
    return "", []


def _remove_owned_links(dest_root: Path, names: list[str]) -> None:
    for name in names:
        link = dest_root / name
        if _owned_link(link):
            link.unlink()


def _place_skill_link(target: Path, source: Path) -> None:
    resolved = source.resolve()
    try:
        target.symlink_to(resolved, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    import _winapi

    _winapi.CreateJunction(str(resolved), str(target))  # type: ignore[attr-defined]


def link_managed_skill_packages(
    workspace: Path,
    runner: str,
    package_dirs: list[Path],
) -> list[str]:
    """Expose selected skill packages inside the runner's own skills directory.

    Returns skill names that were skipped because another package, or a real
    directory, already owns that name. The first package wins. Links this
    function created earlier are removed, including after the runner changes.
    """
    root = runner.strip()
    if not root:
        return []
    dest_root = workspace / managed_skill_dir(root)
    dest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = workspace / ".octop" / "managed-skill-links.json"
    previous_runner, previous = _load_skill_manifest(manifest_path)
    if previous_runner:
        _remove_owned_links(workspace / managed_skill_dir(previous_runner), previous)
    else:
        for skill_dir in _known_skill_dirs(workspace):
            _remove_owned_links(skill_dir, previous)
    created: list[str] = []
    skipped: list[str] = []
    for package_dir in package_dirs:
        if not package_dir.is_dir():
            continue
        for child in sorted(package_dir.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").is_file():
                continue
            slug = child.name
            target = dest_root / slug
            if slug in created or target.exists() or _owned_link(target):
                if slug not in skipped:
                    skipped.append(slug)
                continue
            try:
                _place_skill_link(target, child)
            except OSError:
                logger.warning("managed skill link failed for %s", slug, exc_info=True)
                continue
            created.append(slug)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"runner": root, "links": created}),
        encoding="utf-8",
    )
    if skipped:
        logger.warning(
            "managed skill names already exist, kept the first: %s",
            ", ".join(skipped),
        )
    return skipped


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


def _keep_offered_session_mode(config: dict[str, Any]) -> None:
    """Drop a mode id this underlying agent does not publish."""
    from octop.infra.agents.acp.session_modes import session_modes

    mode = config.get("managed_session_mode")
    text = mode.strip() if isinstance(mode, str) else ""
    runner = config.get("managed_runner")
    runner_name = runner.strip() if isinstance(runner, str) else ""
    offered = {item.id for item in session_modes(runner_name)}
    if text and (not runner_name or not offered or text not in offered):
        config.pop("managed_session_mode", None)
        return
    if text:
        config["managed_session_mode"] = text
        return
    config.pop("managed_session_mode", None)


def preserve_managed_config(config: dict[str, Any], previous: dict[str, Any]) -> None:
    """Keep the ACP binding and filesystem root across later edits."""
    apply_managed_backend(config)
    pin_managed_runtime(config, previous=previous)
    runner = config.get("managed_runner")
    if not isinstance(runner, str) or not runner.strip():
        previous_runner = previous.get("managed_runner")
        if isinstance(previous_runner, str) and previous_runner.strip():
            config["managed_runner"] = previous_runner.strip()
    if config.get("managed_permission_mode") not in {"ask", "yolo"}:
        previous_mode = previous.get("managed_permission_mode")
        if previous_mode in {"ask", "yolo"}:
            config["managed_permission_mode"] = previous_mode
    if "managed_session_mode" not in config:
        previous_session = previous.get("managed_session_mode")
        if isinstance(previous_session, str) and previous_session.strip():
            config["managed_session_mode"] = previous_session.strip()
    _keep_offered_session_mode(config)
