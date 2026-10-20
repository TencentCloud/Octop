"""Workspace bootstrap helpers.

Two public entry points share the same machinery:

* :class:`HarnessAgent` exposes :meth:`HarnessAgent.init_workspace` for users
  who already have a configured agent. That path uses the agent's resolved
  backend, language, and workspace paths.
* :func:`init_workspace` (this module, top-level) is a *no-config*
  bootstrap. CLI tools call it before any provider is configured — i.e.
  before a ``HarnessAgent`` can even be constructed — so it can't depend
  on :class:`HarnessAgentConfig`. It builds a plain
  ``FilesystemBackend(root_dir, virtual_mode=True)`` and runs the same
  template + skill sync.

Both paths funnel into :func:`_seed_workspace`, so any change to the
copy-templates / sync-skills logic propagates automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import resources as _resources
from pathlib import Path as _Path
from typing import TYPE_CHECKING

from octop_harness.backends.workspace import DEFAULT_BUILTIN_SKILLS_DIR
from octop_harness.builtin._sync import VERSION_FILE
from octop_harness.builtin.templates import iter_md_template_files

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

_PROVIDERS_USER_DIR = _Path.home() / ".octop-harness"
_PROVIDERS_TEMPLATE_SRC = "octop_harness.providers"
_PROVIDERS_TEMPLATE_FILE = "provider_template.json"
_PROVIDERS_USER_FILE = "providers_template.json"


@dataclass
class InitResult:
    """Outcome of a workspace initialization.

    Attributes:
        workspace_path: Backend virtual path to the workspace.
        templates_created: Paths of newly written template files.
        templates_skipped: Paths that already existed and were left untouched.
        templates_overwritten: Paths that existed but were replaced (overwrite=True).
        skills_synced: True when built-in skills were (re)copied.
        skills_fallback: Workspace paths served from the ``"en"`` fallback
            because the requested language subdirectory was missing.
        agents_created: Absolute paths of agent markdown files seeded on this run.
        agents_skipped: Agent paths that already existed and were left untouched.
        agents_overwritten: Agent paths replaced when ``overwrite=True``.
        agents_fallback: Workspace paths served from the ``"en"`` fallback.
    """

    workspace_path: str
    templates_created: list[str] = field(default_factory=list)
    templates_skipped: list[str] = field(default_factory=list)
    templates_overwritten: list[str] = field(default_factory=list)
    skills_synced: bool = False
    skills_fallback: list[str] = field(default_factory=list)
    agents_created: list[str] = field(default_factory=list)
    agents_skipped: list[str] = field(default_factory=list)
    agents_overwritten: list[str] = field(default_factory=list)
    agents_fallback: list[str] = field(default_factory=list)


def _write_providers_template(
    user_dir: _Path,
    *,
    overwrite: bool = False,
) -> None:
    """Write built-in provider template to *user_dir*/providers_template.json."""
    dest = user_dir / _PROVIDERS_USER_FILE
    if dest.exists() and not overwrite:
        return
    user_dir.mkdir(parents=True, exist_ok=True)
    pkg = _resources.files(_PROVIDERS_TEMPLATE_SRC)
    raw = pkg.joinpath(_PROVIDERS_TEMPLATE_FILE).read_text(encoding="utf-8")
    dest.write_text(raw, encoding="utf-8")


def _seed_workspace(
    workspace: BackendWorkspace,
    *,
    language: str,
    include_md_files: bool,
    include_skills: bool,
    include_agents: bool,
    overwrite: bool,
) -> InitResult:
    """Run template + skill sync against an arbitrary backend.

    Shared between :meth:`HarnessAgent.init_workspace` and the top-level
    :func:`init_workspace`. Backend-agnostic — accepts anything
    that quacks like ``BackendProtocol``.
    """
    result = InitResult(workspace_path=str(workspace.workspace_dir))

    if include_md_files:
        templates = iter_md_template_files(language)
        for name, content_bytes in templates:
            exists = workspace.exists(name)
            if exists and not overwrite:
                result.templates_skipped.append(workspace.resolve_path(name))
                continue
            content_str = content_bytes.decode("utf-8").replace(
                "{{BOOTSTRAP_MARKER}}",
                workspace.system_rel(".bootstrapped"),
            )
            workspace.write_text(name, content_str, force=True)
            resolved = workspace.resolve_path(name)
            if exists:
                result.templates_overwritten.append(resolved)
            else:
                result.templates_created.append(resolved)

    if include_skills:
        from octop_harness._version import __version__ as version

        synced, fallback_paths = workspace.sync_builtin_skills(version, language=language)
        if synced is False and overwrite:
            workspace.write_text(f"{DEFAULT_BUILTIN_SKILLS_DIR}/{VERSION_FILE}", "", force=True)
            synced, fallback_paths = workspace.sync_builtin_skills(version, language=language)
        result.skills_synced = bool(synced)
        result.skills_fallback.extend(fallback_paths)

    if include_agents:
        seed_result = workspace.seed_builtin_agents(language=language, overwrite=overwrite)
        result.agents_created.extend(seed_result.created)
        result.agents_skipped.extend(seed_result.skipped)
        result.agents_overwritten.extend(seed_result.overwritten)
        result.agents_fallback.extend(seed_result.fallback)

    return result


def init_workspace(
    workspace_dir: str | _Path,
    *,
    language: str = "en",
    include_md_files: bool = True,
    include_skills: bool = True,
    include_agents: bool = True,
    overwrite: bool = False,
) -> InitResult:
    """Bootstrap a Harness workspace without constructing a full agent.

    Use this from CLI / scaffold tools that need to lay down the
    built-in skills + markdown templates *before* the user has
    configured a model provider (which a real ``HarnessAgent`` would
    require).

    Args:
        workspace_dir: Absolute local directory that will host the
            workspace. Templates and skills are written directly under
            this directory; the underlying ``FilesystemBackend`` is
            rooted here, exposing it as the virtual ``/``.
        language: Language code for markdown templates (``"en"`` /
            ``"zh"``).
        include_md_files: Copy packaged markdown templates
            (``AGENTS.md``, ``MEMORY.md``, …) into the workspace root.
        include_skills: Sync packaged ``builtin/skills/**`` into
            ``{workspace}/_builtin_skills/``.
        include_agents: Seed packaged ``builtin/agents/**`` into
            ``{workspace}/agents/``.
        overwrite: When True, replace user-edited files and force a
            skill resync.

    Returns:
        An :class:`InitResult` summarizing what was created, skipped,
        overwritten, and whether skills were synced.

    Raises:
        FileNotFoundError: If ``language`` doesn't exist under packaged
            ``builtin/md_files/``.
        ValueError: If ``workspace_dir`` is not an absolute path.
    """
    # Local import: ``deepagents.backends`` pulls in optional deps; defer
    # so ``import octop_harness.init`` stays cheap.
    from deepagents.backends import FilesystemBackend

    from octop_harness.backends.workspace import BackendWorkspace

    workspace = _Path(workspace_dir).expanduser()
    if not workspace.is_absolute():
        raise ValueError(f"workspace_dir must be an absolute path, got {workspace_dir!r}")
    workspace.mkdir(parents=True, exist_ok=True)

    # Backend rooted at the workspace itself: skills, templates and memory
    # md files all sit under ``workspace_dir``.
    backend = FilesystemBackend(root_dir=str(workspace), virtual_mode=False)
    ws = BackendWorkspace(backend, workspace)

    result = ws.init_workspace(
        language=language,
        include_md_files=include_md_files,
        include_skills=include_skills,
        include_agents=include_agents,
        overwrite=overwrite,
    )
    _write_providers_template(_PROVIDERS_USER_DIR, overwrite=overwrite)
    return result


__all__ = ["InitResult", "init_workspace"]
