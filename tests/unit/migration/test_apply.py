"""Applying a migration plan to Octop's stores and one expert workspace."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.migration.apply import MigrationReport, apply_plan
from octop.infra.migration.plan import (
    ChannelImport,
    FileImport,
    McpImport,
    MigrationPlan,
    ProviderImport,
    SkillImport,
)
from octop.infra.utils.paths import PathLayout

AGENT = "agent-1"


class FakeWorkspace:
    """The slice of BackendWorkspace the migration writes through."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(files or {})

    async def aexists(self, path: str) -> bool:
        return path in self.files

    async def awrite_text(self, path: str, content: str, *, force: bool = True) -> None:
        self.files[path] = content.encode("utf-8")

    async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
        self.files.update(pairs)

    async def adelete(self, path: str) -> None:
        for key in [k for k in self.files if k == path or k.startswith(f"{path}/")]:
            del self.files[key]


@pytest.fixture
def services(tmp_path: Path) -> Iterator[SharedServices]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    built = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    try:
        yield built
    finally:
        db.close()


@pytest.fixture
def user_id(services: SharedServices) -> int:
    uid = services.repos.user_repo.create(username="owner", password_hash="x", role="user")
    services.repos.agent_repo.create(agent_id=AGENT, user_id=uid, name="main")
    return int(uid)


def _plan(tmp_path: Path) -> MigrationPlan:
    source = tmp_path / "source"
    skill = source / "skills" / "weekly-report"
    (skill / "templates").mkdir(parents=True)
    # Bytes, not text: skills are copied verbatim and Windows text mode would write CRLF.
    (skill / "SKILL.md").write_bytes(b"---\nname: weekly-report\n---\n")
    (skill / "templates" / "report.md").write_bytes(b"# template")
    (skill / ".git").mkdir()
    (skill / ".git" / "config").write_text("ignored", encoding="utf-8")
    (source / "SOUL.md").write_text("migrated soul", encoding="utf-8")
    return MigrationPlan(
        source="openclaw",
        home=source,
        providers=[
            ProviderImport("proxy", "openai", "https://llm.example.com/v1", "sk-1", ("m1", "m2")),
            ProviderImport("keyless", "openai", "http://localhost:8080/v1", None, ()),
        ],
        default_model=("proxy", "m1"),
        files=[
            FileImport(dest="SOUL.md", source=source / "SOUL.md"),
            FileImport(dest="MEMORY.md", source=source / "missing.md", content="converted"),
        ],
        skills=[SkillImport("weekly-report", skill), SkillImport("../escape", skill)],
        mcp_servers=[
            McpImport("fetch", {"transport": "stdio", "command": "uvx"}),
            McpImport(
                "insecure", {"transport": "streamable_http", "url": "http://example.com/mcp"}
            ),
        ],
        channels=[ChannelImport("telegram", "telegram", {"bot_token": "tg"})],
    )


def _rows(report: MigrationReport) -> list[tuple[str, str, str, str]]:
    return [(i.section, i.name, i.status, i.reason) for i in report.items]


def _custom_servers(services: SharedServices, user_id: int) -> dict[str, Any]:
    return ConnectorService(
        repo=services.repos.connector_repo,
        secret_repo=services.secret_repo,
        settings_repo=services.settings_repo,
        config=services.config,
    ).get_custom_servers(user_id)


async def _apply(
    plan: MigrationPlan,
    services: SharedServices,
    workspace: FakeWorkspace,
    user_id: int,
    **options: Any,
) -> MigrationReport:
    return await apply_plan(
        plan, services=services, workspace=workspace, agent_id=AGENT, user_id=user_id, **options
    )


@pytest.mark.asyncio
async def test_applies_every_section(
    tmp_path: Path, services: SharedServices, user_id: int
) -> None:
    workspace = FakeWorkspace()
    report = await _apply(_plan(tmp_path), services, workspace, user_id)

    assert _rows(report) == [
        ("models", "proxy", "migrated", ""),
        ("models", "keyless", "migrated", "no_api_key"),
        ("models", "proxy/m1", "migrated", "default_model"),
        ("files", "SOUL.md", "migrated", ""),
        ("files", "MEMORY.md", "migrated", ""),
        ("skills", "weekly-report", "migrated", ""),
        ("skills", "../escape", "failed", "invalid_name"),
        ("mcp", "insecure", "failed", "invalid"),
        ("mcp", "fetch", "migrated", ""),
        ("channels", "telegram", "migrated", "channel_disabled"),
    ]

    proxy = services.provider_repo.get_by_name("proxy")
    assert proxy is not None
    assert (proxy.kind, proxy.base_url, proxy.api_key) == (
        "openai",
        "https://llm.example.com/v1",
        "sk-1",
    )
    assert [m["id"] for m in json.loads(proxy.models_json or "[]")] == ["m1", "m2"]
    assert services.settings_repo.get_active_model() == ("proxy", "m1")

    assert workspace.files == {
        "SOUL.md": b"migrated soul",
        "MEMORY.md": b"converted",
        "skills/weekly-report/SKILL.md": b"---\nname: weekly-report\n---\n",
        "skills/weekly-report/templates/report.md": b"# template",
    }
    assert set(_custom_servers(services, user_id)) == {"fetch"}

    [channel] = services.channel_repo.list_by_agent(AGENT)
    assert (channel.kind, channel.name, bool(channel.enabled)) == ("telegram", "telegram", False)
    assert json.loads(channel.config_json) == {"bot_token": "tg", "enabled": False}


@pytest.mark.asyncio
async def test_dry_run_reports_the_same_and_writes_nothing(
    tmp_path: Path, services: SharedServices, user_id: int
) -> None:
    workspace = FakeWorkspace()
    plan = _plan(tmp_path)

    dry = await _apply(plan, services, workspace, user_id, dry_run=True)

    assert dry.dry_run is True
    assert workspace.files == {}
    assert services.provider_repo.list_all() == []
    assert services.settings_repo.get_active_model() == ("", "")
    assert _custom_servers(services, user_id) == {}
    assert services.channel_repo.list_by_agent(AGENT) == []

    real = await _apply(plan, services, workspace, user_id)
    assert _rows(dry) == _rows(real)


@pytest.mark.asyncio
async def test_second_run_skips_what_is_there(
    tmp_path: Path, services: SharedServices, user_id: int
) -> None:
    workspace = FakeWorkspace()
    plan = _plan(tmp_path)
    await _apply(plan, services, workspace, user_id)
    workspace.files["SOUL.md"] = b"edited in octop"

    again = await _apply(plan, services, workspace, user_id)

    assert [
        (i.name, i.status, i.reason, i.detail) for i in again.items if i.status == "skipped"
    ] == [
        ("proxy", "skipped", "exists", ""),
        ("keyless", "skipped", "exists", ""),
        ("proxy/m1", "skipped", "default_model_set", "proxy/m1"),
        ("SOUL.md", "skipped", "exists", ""),
        ("MEMORY.md", "skipped", "exists", ""),
        ("weekly-report", "skipped", "exists", ""),
        ("fetch", "skipped", "exists", ""),
        ("telegram", "skipped", "exists", ""),
    ]
    assert again.count("migrated") == 0
    assert workspace.files["SOUL.md"] == b"edited in octop"
    assert len(services.channel_repo.list_by_agent(AGENT)) == 1


@pytest.mark.asyncio
async def test_overwrite_replaces_files_skills_and_default_model(
    tmp_path: Path, services: SharedServices, user_id: int
) -> None:
    workspace = FakeWorkspace(
        {
            "SOUL.md": b"old soul",
            "skills/weekly-report/SKILL.md": b"old skill",
            "skills/weekly-report/stale.md": b"left over",
        }
    )
    services.settings_repo.set_active_model("other", "model")

    report = await _apply(_plan(tmp_path), services, workspace, user_id, overwrite=True)

    assert workspace.files["SOUL.md"] == b"migrated soul"
    assert "skills/weekly-report/stale.md" not in workspace.files
    assert workspace.files["skills/weekly-report/SKILL.md"].startswith(b"---")
    assert services.settings_repo.get_active_model() == ("proxy", "m1")
    assert report.count("skipped") == 0


@pytest.mark.asyncio
async def test_sections_can_be_left_out(
    tmp_path: Path, services: SharedServices, user_id: int
) -> None:
    workspace = FakeWorkspace()
    report = await _apply(
        _plan(tmp_path), services, workspace, user_id, sections=("files", "skills")
    )
    assert {item.section for item in report.items} == {"files", "skills"}
    assert services.provider_repo.list_all() == []
    assert services.channel_repo.list_by_agent(AGENT) == []


@pytest.mark.asyncio
async def test_default_model_needs_its_provider(
    tmp_path: Path, services: SharedServices, user_id: int
) -> None:
    plan = MigrationPlan(source="hermes", home=tmp_path, default_model=("absent", "m"))
    report = await _apply(plan, services, FakeWorkspace(), user_id)
    assert report.items == []
    assert services.settings_repo.get_active_model() == ("", "")


def test_report_serializes_for_json_output(tmp_path: Path) -> None:
    plan = MigrationPlan(source="hermes", home=tmp_path)
    plan.note("cron_not_migrated", count=2)
    report = MigrationReport(source="hermes", home=str(tmp_path), dry_run=True, notes=plan.notes)
    report.add("files", "SOUL.md", "skipped", "exists")
    assert json.loads(json.dumps(report.to_dict())) == {
        "source": "hermes",
        "home": str(tmp_path),
        "dry_run": True,
        "items": [
            {
                "section": "files",
                "name": "SOUL.md",
                "status": "skipped",
                "reason": "exists",
                "detail": "",
            }
        ],
        "notes": [{"code": "cron_not_migrated", "params": {"count": 2}}],
    }
