"""Apply create-time prompt / skill patches onto a newly seeded workspace."""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.skill_packages import validate_skill_slug

logger = logging.getLogger(__name__)

_MAX_PATCH_FILES = 80
_MAX_FILE_BYTES = 1_000_000
_ROOT_MD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")
_NESTED_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ComposerHubSkillPick:
    skill_name: str
    display_name: str = ""
    icon_url: str = ""
    label: dict[str, str] = field(default_factory=dict)
    summary: dict[str, str] = field(default_factory=dict)


@dataclass
class ComposerApplyReport:
    hub_skill_errors: list[str] = field(default_factory=list)
    copy_skill_errors: list[str] = field(default_factory=list)

    def as_api_fields(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if self.hub_skill_errors:
            out["hub_skill_errors"] = list(self.hub_skill_errors)
        if self.copy_skill_errors:
            out["copy_skill_errors"] = list(self.copy_skill_errors)
        return out


@dataclass(frozen=True)
class ComposerSkillCopy:
    agent_id: str
    slug: str


@dataclass(frozen=True)
class ComposerWorkspacePatch:
    file_overrides: tuple[tuple[str, str], ...] = ()
    omit_files: tuple[str, ...] = ()
    hub_skills: tuple[ComposerHubSkillPick, ...] = ()

    def is_empty(self) -> bool:
        return not (self.file_overrides or self.omit_files or self.hub_skills)


def normalize_composer_relpath(name: str, *, allow_skill_dir: bool = False) -> str:
    """Normalize a composer-editable workspace path or raise ``SLASH_BAD_ARGS``."""
    rel = name.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/") or rel.startswith(".octop"):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}")
    parts = rel.split("/")
    if any(not part for part in parts):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}")
    if len(parts) == 1:
        if not _ROOT_MD.fullmatch(parts[0]):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}")
        return parts[0]
    if parts[0] == "skills" and len(parts) >= 2:
        try:
            slug = validate_skill_slug(parts[1])
        except Exception as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}") from exc
        if len(parts) == 2:
            if not allow_skill_dir:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}")
            return f"skills/{slug}"
        if any(not _NESTED_FILE.fullmatch(part) for part in parts[2:]):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}")
        return "/".join([parts[0], slug, *parts[2:]])
    if parts[0] == "agents" and len(parts) == 2 and parts[1].endswith(".md"):
        slug = parts[1][:-3]
        try:
            validate_skill_slug(slug)
        except Exception as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}") from exc
        return f"agents/{slug}.md"
    raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid file path {name!r}")


def composer_copies_from_payload(
    copy_skills: list[dict[str, Any]] | None,
) -> tuple[ComposerSkillCopy, ...]:
    picks: list[ComposerSkillCopy] = []
    for raw in copy_skills or []:
        agent_id = str(raw.get("agent_id") or "").strip()
        if not agent_id or "/" in agent_id or "\\" in agent_id or ".." in agent_id:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid copy source {agent_id!r}")
        try:
            slug = validate_skill_slug(str(raw.get("slug") or ""))
        except Exception as exc:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"invalid copy skill {raw.get('slug')!r}",
            ) from exc
        picks.append(ComposerSkillCopy(agent_id=agent_id, slug=slug))
    return tuple(picks)


def composer_patch_from_payload(
    *,
    file_overrides: list[dict[str, str]] | None,
    omit_files: list[str] | None,
    hub_skills: list[dict[str, Any]] | None,
) -> ComposerWorkspacePatch:
    overrides = tuple(
        (
            normalize_composer_relpath(str(item.get("name") or "")),
            str(item.get("content") or ""),
        )
        for item in (file_overrides or [])
    )
    omitted = tuple(
        normalize_composer_relpath(path, allow_skill_dir=True) for path in (omit_files or [])
    )
    picks: list[ComposerHubSkillPick] = []
    for raw in hub_skills or []:
        try:
            skill_name = validate_skill_slug(str(raw.get("skill_name") or ""))
        except Exception as exc:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                f"invalid hub skill {raw.get('skill_name')!r}",
            ) from exc
        label = {
            key: value.strip()
            for key, value in dict(raw.get("label") or {}).items()
            if isinstance(value, str) and value.strip()
        }
        summary = {
            key: value.strip()
            for key, value in dict(raw.get("summary") or {}).items()
            if isinstance(value, str) and value.strip()
        }
        picks.append(
            ComposerHubSkillPick(
                skill_name=skill_name,
                display_name=str(raw.get("display_name") or "").strip(),
                icon_url=str(raw.get("icon_url") or "").strip(),
                label=label,
                summary=summary,
            )
        )
    patch = ComposerWorkspacePatch(
        file_overrides=overrides,
        omit_files=omitted,
        hub_skills=tuple(picks),
    )
    if len(patch.file_overrides) + len(patch.omit_files) + len(patch.hub_skills) > _MAX_PATCH_FILES:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "too many composer file patches")
    for _name, content in patch.file_overrides:
        if len(content.encode("utf-8")) > _MAX_FILE_BYTES:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "composer file is too large")
    return patch


def composer_plan_from_payload(
    *,
    file_overrides: list[dict[str, str]] | None,
    omit_files: list[str] | None,
    hub_skills: list[dict[str, Any]] | None,
    copy_skills: list[dict[str, Any]] | None = None,
) -> tuple[ComposerWorkspacePatch, tuple[ComposerSkillCopy, ...]]:
    patch = composer_patch_from_payload(
        file_overrides=file_overrides,
        omit_files=omit_files,
        hub_skills=hub_skills,
    )
    copies = composer_copies_from_payload(copy_skills)
    if (
        len(patch.file_overrides) + len(patch.omit_files) + len(patch.hub_skills) + len(copies)
        > _MAX_PATCH_FILES
    ):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "too many composer file patches")
    return patch, copies


class _WorkspaceSkillInstallTarget:
    def __init__(self, workspace: Any) -> None:
        self._workspace = workspace

    async def skill_exists(self, slug: str) -> bool:
        text = await self._workspace.aread_text(f"skills/{slug}/SKILL.md")
        return text is not None

    async def write_files(self, slug: str, files: list[tuple[str, bytes]]) -> None:
        skill_root = f"skills/{slug}"
        with contextlib.suppress(Exception):
            await self._workspace.adelete(skill_root)
        dirs = [path for path, _content in files if path.endswith("/")]
        payload = [(path, content) for path, content in files if not path.endswith("/")]
        for path in dirs:
            await self._workspace.amkdir(f"{skill_root}/{path}".rstrip("/"))
        if payload:
            await self._workspace.aupload_many(
                [(f"{skill_root}/{path}", content) for path, content in payload]
            )

    async def after_install(self, slug: str, *, enable: bool | None = None) -> None:
        return None


async def apply_composer_workspace_patch(
    workspace: Any,
    patch: ComposerWorkspacePatch,
    *,
    copies: Sequence[tuple[str, Any]] = (),
    report: ComposerApplyReport | None = None,
) -> ComposerApplyReport:
    """Apply omit → copy → override → hub. Hub/copy failures are reported, not raised."""
    report = report or ComposerApplyReport()
    if patch.is_empty() and not copies:
        return report

    for rel in patch.omit_files:
        with contextlib.suppress(Exception):
            await workspace.adelete(rel)

    if copies:
        from octop.infra.skills.skill_transfer import (  # noqa: PLC0415
            copy_workspace_skill_to_workspace,
        )

        for slug, source in copies:
            try:
                await copy_workspace_skill_to_workspace(
                    source=source,
                    destination=workspace,
                    slug=slug,
                    overwrite=True,
                )
            except Exception:
                logger.warning("composer copy skill %s failed", slug, exc_info=True)
                report.copy_skill_errors.append(slug)

    uploads = [
        (rel, content.encode("utf-8"))
        for rel, content in patch.file_overrides
        if not rel.endswith("/")
    ]
    if uploads:
        await workspace.aupload_many(uploads)
    if not patch.hub_skills:
        return report

    from octop.infra.skills.install import install_skill_from_skillhub  # noqa: PLC0415
    from octop.infra.skills.skillhub_market import download_skillhub_package  # noqa: PLC0415

    target = _WorkspaceSkillInstallTarget(workspace)
    for pick in patch.hub_skills:
        try:
            files = await download_skillhub_package(pick.skill_name)
            await install_skill_from_skillhub(
                target,
                skill_name=pick.skill_name,
                files=files,
                display_name=pick.display_name,
                icon_url=pick.icon_url,
                label=pick.label or None,
                summary=pick.summary or None,
                overwrite=True,
                enable=True,
            )
        except Exception:
            logger.warning(
                "composer hub skill %s failed",
                pick.skill_name,
                exc_info=True,
            )
            report.hub_skill_errors.append(pick.skill_name)
    return report
