"""Write a :class:`MigrationPlan` into Octop: providers, one expert's workspace
files and skills, the owner's custom MCP servers, and the expert's channels.

Nothing that already exists is replaced unless ``overwrite`` is set, and
``dry_run`` reports the same outcomes without writing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from octop.infra.connectors.custom_mcp import normalize_server_spec
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.services import SharedServices
from octop.infra.errors import OctopError
from octop.infra.migration.plan import MigrationPlan, Note, SkillImport
from octop.infra.skills.skill_packages import SkillPackageError, validate_skill_slug
from octop.infra.utils.ulid import new_ulid

SECTIONS = ("models", "files", "skills", "mcp", "channels")

_MAX_SKILL_BYTES = 20 * 1024 * 1024
_SKIPPED_DIRS = frozenset({"node_modules", "__pycache__"})


@dataclass(frozen=True)
class ItemResult:
    section: str
    name: str
    status: str  # "migrated" | "skipped" | "failed"
    reason: str = ""  # code for the CLI to word, e.g. "exists"
    detail: str = ""  # raw error text, when there is one


@dataclass
class MigrationReport:
    source: str
    home: str
    dry_run: bool
    items: list[ItemResult] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)

    def add(self, section: str, name: str, status: str, reason: str = "", detail: str = "") -> None:
        self.items.append(ItemResult(section, name, status, reason, detail))

    def count(self, status: str) -> int:
        return sum(1 for item in self.items if item.status == status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "home": self.home,
            "dry_run": self.dry_run,
            "items": [asdict(item) for item in self.items],
            "notes": [asdict(note) for note in self.notes],
        }


async def apply_plan(
    plan: MigrationPlan,
    *,
    services: SharedServices,
    workspace: Any,
    agent_id: str,
    user_id: int,
    sections: tuple[str, ...] = SECTIONS,
    overwrite: bool = False,
    dry_run: bool = False,
) -> MigrationReport:
    """Apply ``plan`` to the expert ``agent_id`` (``workspace`` is its BackendWorkspace)."""
    report = MigrationReport(
        source=plan.source, home=str(plan.home), dry_run=dry_run, notes=list(plan.notes)
    )
    if "models" in sections:
        _apply_models(plan, report, services, overwrite=overwrite, dry_run=dry_run)
    if "files" in sections:
        await _apply_files(plan, report, workspace, overwrite=overwrite, dry_run=dry_run)
    if "skills" in sections:
        for skill in plan.skills:
            await _apply_skill(skill, report, workspace, overwrite=overwrite, dry_run=dry_run)
    if "mcp" in sections:
        _apply_mcp(plan, report, services, user_id, dry_run=dry_run)
    if "channels" in sections:
        _apply_channels(plan, report, services, agent_id, user_id, dry_run=dry_run)
    return report


def _apply_models(
    plan: MigrationPlan,
    report: MigrationReport,
    services: SharedServices,
    *,
    overwrite: bool,
    dry_run: bool,
) -> None:
    repo = services.provider_repo
    available = {row.name for row in repo.list_all()}
    for provider in plan.providers:
        if provider.name in available:
            report.add("models", provider.name, "skipped", "exists")
            continue
        if not dry_run:
            models = [{"id": m, "name": m, "enabled": True} for m in provider.models]
            repo.create(
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                api_key=provider.api_key,
                models_json=json.dumps(models),
            )
        available.add(provider.name)
        report.add("models", provider.name, "migrated", "" if provider.api_key else "no_api_key")

    if plan.default_model is None or plan.default_model[0] not in available:
        return
    label = "/".join(plan.default_model)
    current = services.settings_repo.get_active_model()
    if any(current) and not overwrite:
        report.add("models", label, "skipped", "default_model_set", "/".join(current))
        return
    if not dry_run:
        services.settings_repo.set_active_model(*plan.default_model)
    report.add("models", label, "migrated", "default_model")


async def _apply_files(
    plan: MigrationPlan,
    report: MigrationReport,
    workspace: Any,
    *,
    overwrite: bool,
    dry_run: bool,
) -> None:
    for item in plan.files:
        if await workspace.aexists(item.dest) and not overwrite:
            report.add("files", item.dest, "skipped", "exists")
            continue
        if not dry_run:
            content = item.content
            if content is None:
                content = await asyncio.to_thread(
                    item.source.read_text, encoding="utf-8-sig", errors="replace"
                )
            await workspace.awrite_text(item.dest, content, force=True)
        report.add("files", item.dest, "migrated")


def _read_skill_files(root: Path) -> list[tuple[str, bytes]] | None:
    """Files of one skill directory, or None when it is too large to copy."""
    pairs: list[tuple[str, bytes]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part.startswith(".") or part in _SKIPPED_DIRS for part in rel.parts):
            continue
        if not path.is_file():
            continue
        total += path.stat().st_size
        if total > _MAX_SKILL_BYTES:
            return None
        pairs.append((rel.as_posix(), path.read_bytes()))
    return pairs


async def _apply_skill(
    skill: SkillImport,
    report: MigrationReport,
    workspace: Any,
    *,
    overwrite: bool,
    dry_run: bool,
) -> None:
    try:
        slug = validate_skill_slug(skill.slug)
    except SkillPackageError:
        report.add("skills", skill.slug, "failed", "invalid_name")
        return
    root = f"skills/{slug}"
    exists = await workspace.aexists(f"{root}/SKILL.md")
    if exists and not overwrite:
        report.add("skills", slug, "skipped", "exists")
        return
    files = await asyncio.to_thread(_read_skill_files, skill.source)
    if files is None:
        report.add("skills", slug, "failed", "too_large")
        return
    if not dry_run:
        if exists:
            with contextlib.suppress(Exception):
                await workspace.adelete(root)
        await workspace.aupload_many([(f"{root}/{rel}", data) for rel, data in files])
    report.add("skills", slug, "migrated")


def _apply_mcp(
    plan: MigrationPlan,
    report: MigrationReport,
    services: SharedServices,
    user_id: int,
    *,
    dry_run: bool,
) -> None:
    if not plan.mcp_servers:
        return
    service = ConnectorService(
        repo=services.repos.connector_repo,
        secret_repo=services.secret_repo,
        settings_repo=services.settings_repo,
        config=services.config,
    )
    existing = service.get_custom_servers(user_id)
    reserved = service.reserved_builtin_mcp_names(user_id)
    added: dict[str, Any] = {}
    for server in plan.mcp_servers:
        if server.name in existing or server.name in added:
            report.add("mcp", server.name, "skipped", "exists")
            continue
        if server.name in reserved:
            report.add("mcp", server.name, "failed", "name_reserved")
            continue
        try:
            normalize_server_spec(server.name, server.spec)
        except OctopError as exc:
            report.add("mcp", server.name, "failed", "invalid", exc.message)
            continue
        except ValueError as exc:
            report.add("mcp", server.name, "failed", "invalid", str(exc))
            continue
        added[server.name] = server.spec
    if added and not dry_run:
        try:
            service.put_custom_servers(user_id, {**existing, **added})
        except ValueError as exc:
            for name in added:
                report.add("mcp", name, "failed", "invalid", str(exc))
            return
    for name in added:
        report.add("mcp", name, "migrated")


def _apply_channels(
    plan: MigrationPlan,
    report: MigrationReport,
    services: SharedServices,
    agent_id: str,
    user_id: int,
    *,
    dry_run: bool,
) -> None:
    repo = services.channel_repo
    taken = {(row.kind, row.name) for row in repo.list_by_agent(agent_id)}
    for channel in plan.channels:
        if (channel.kind, channel.name) in taken:
            report.add("channels", channel.name, "skipped", "exists")
            continue
        if not dry_run:
            # Disabled on arrival: the old assistant may still be answering on
            # the same bot, and two listeners would both reply.
            channel_id = repo.create(
                channel_id=new_ulid(),
                agent_id=agent_id,
                user_id=user_id,
                kind=channel.kind,
                name=channel.name,
                config_json=json.dumps({**channel.config, "enabled": False}),
            )
            repo.update(channel_id, enabled=False)
        report.add("channels", channel.name, "migrated", "channel_disabled")
