"""Tests for exported published-expert snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.builtin_skills import OCTOP_BUILTIN_SKILLS_ROOT
from octop.infra.agents.experts.catalog import MANIFEST_FILENAME, seed_expert_directory
from octop.infra.agents.experts.publish import (
    PublishedExpertSnapshotMeta,
    assert_can_mutate_published,
    export_agent_workspace_to_dir,
    resolve_published_expert_slug,
)
from octop.infra.db.repos.published_experts import PublishedExpertRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User
from octop.infra.utils.paths import PathLayout


def _workspace(root: Path) -> BackendWorkspace:
    return BackendWorkspace(LocalShellBackend(root_dir=str(root), virtual_mode=False), root)


def test_published_experts_dir_is_under_instance_root(tmp_path: Path) -> None:
    assert PathLayout(tmp_path).published_experts_dir == tmp_path / "published_experts"


def test_only_creator_or_admin_can_mutate_published_expert() -> None:
    row = PublishedExpertRow(
        id="01",
        slug="researcher",
        name="Researcher",
        description="",
        created_by="7",
        source_agent_id=None,
        icon_name="",
        color="",
        created_at=0,
        updated_at=0,
    )
    owner = User(id=7, username="owner", role=Role.USER, display_name=None)
    admin = User(id=8, username="admin", role=Role.ADMIN, display_name=None)
    other = User(id=9, username="other", role=Role.USER, display_name=None)

    assert_can_mutate_published(row, owner)
    assert_can_mutate_published(row, admin)
    with pytest.raises(OctopError) as exc:
        assert_can_mutate_published(row, other)
    assert exc.value.code is ErrorCode.FORBIDDEN


def test_resolve_published_expert_slug_retries_derived_name_and_rejects_taken_explicit_slug() -> (
    None
):
    class Repo:
        def __init__(self) -> None:
            self.slugs = {"source-expert", "chosen-slug"}

        def get_by_slug(self, slug: str) -> object | None:
            return object() if slug in self.slugs else None

    repo = Repo()

    assert resolve_published_expert_slug(repo=repo, name="Source Expert") == "source-expert-2"
    with pytest.raises(OctopError) as exc:
        resolve_published_expert_slug(repo=repo, name="Other", slug="chosen-slug")
    assert exc.value.code is ErrorCode.PUBLISHED_EXPERT_SLUG_TAKEN


@pytest.mark.asyncio
async def test_export_snapshot_writes_manifest_and_seed_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    manifest = {
        "id": "source-agent",
        "label": {"zh": "来源专家", "en": "Source expert"},
        "description": {"zh": "说明", "en": "Description"},
        "quick_prompts": [{"title": {"zh": "开始", "en": "Start"}}],
    }
    await source.aupload_many(
        [
            (MANIFEST_FILENAME, json.dumps(manifest, ensure_ascii=False).encode()),
            ("SOUL.md", b"# Source soul"),
            ("MEMORY.md", b"# Shared memory"),
            ("skills/research/SKILL.md", b"# Research"),
            (".env", b"API_KEY=secret"),
            ("inbound/note.txt", b"user upload"),
            ("daily/2026-01-01.md", b"journal"),
            ("uploads/tmp.bin", b"binary"),
        ]
    )

    destination = tmp_path / "published"
    exported = await export_agent_workspace_to_dir(workspace=source, dest=destination)

    assert set(exported) == {
        MANIFEST_FILENAME,
        "SOUL.md",
        "skills/research/SKILL.md",
    }
    assert json.loads((destination / MANIFEST_FILENAME).read_text(encoding="utf-8")) == manifest
    assert (destination / "SOUL.md").read_text(encoding="utf-8") == "# Source soul"
    assert not (destination / "MEMORY.md").exists()
    assert (destination / "skills" / "research" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "# Research"
    assert not (destination / ".env").exists()
    assert not (destination / "inbound").exists()
    assert not (destination / "daily").exists()
    assert not (destination / "uploads").exists()

    installed_dir = tmp_path / "installed"
    installed_dir.mkdir()
    copied = await seed_expert_directory(
        expert_dir=destination,
        workspace=_workspace(installed_dir),
    )

    assert copied == 3
    assert (installed_dir / MANIFEST_FILENAME).read_text(encoding="utf-8") == json.dumps(
        manifest,
        ensure_ascii=False,
    )
    assert (installed_dir / "skills" / "research" / "SKILL.md").read_bytes() == b"# Research"
    assert not (installed_dir / "MEMORY.md").exists()


@pytest.mark.asyncio
async def test_export_snapshot_rejects_invalid_manifest(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    await source.aupload_many([(MANIFEST_FILENAME, b"not json")])

    with pytest.raises(ValueError, match="valid JSON object"):
        await export_agent_workspace_to_dir(workspace=source, dest=tmp_path / "published")


@pytest.mark.asyncio
async def test_export_snapshot_keeps_existing_directory_when_export_fails(
    tmp_path: Path,
) -> None:
    class FailingWorkspace:
        async def adownload_bytes(self, path: str) -> bytes:
            if path == MANIFEST_FILENAME:
                return b"{}"
            raise RuntimeError("workspace download failed")

        async def aglob(self, _pattern: str) -> SimpleNamespace:
            return SimpleNamespace(matches=[{"path": "SOUL.md", "is_dir": False}])

    destination = tmp_path / "published"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(RuntimeError, match="workspace download failed"):
        await export_agent_workspace_to_dir(
            workspace=FailingWorkspace(),  # type: ignore[arg-type]
            dest=destination,
        )

    assert [path.name for path in destination.iterdir()] == ["existing.txt"]
    assert (destination / "existing.txt").read_text(encoding="utf-8") == "keep me"


@pytest.mark.asyncio
async def test_export_snapshot_excludes_runtime_workspace_dirs(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    manifest = {
        "id": "source-agent",
        "label": {"zh": "来源专家", "en": "Source expert"},
        "description": {"zh": "说明", "en": "Description"},
    }
    await source.aupload_many(
        [
            (MANIFEST_FILENAME, json.dumps(manifest, ensure_ascii=False).encode()),
            ("SOUL.md", b"# Source soul"),
            (f"{OCTOP_BUILTIN_SKILLS_ROOT}/skill-manager/SKILL.md", b"# Builtin"),
            ("logs/agent.log", b"runtime log line"),
        ]
    )

    destination = tmp_path / "published"
    exported = await export_agent_workspace_to_dir(
        workspace=source,
        dest=destination,
        metadata=PublishedExpertSnapshotMeta(
            name="Published Expert",
            description="Published description",
            icon_name=None,
            color=None,
            label_zh="发布专家",
            label_en="Published Expert",
            welcome_message_zh="",
            welcome_message_en="",
        ),
        manifest_id="published-expert",
    )

    assert set(exported) == {MANIFEST_FILENAME, "SOUL.md"}
    assert not (destination / OCTOP_BUILTIN_SKILLS_ROOT).exists()
    assert not (destination / "logs").exists()
    merged = json.loads((destination / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert merged["id"] == "published-expert"
    assert merged["label"] == {"zh": "发布专家", "en": "Published Expert"}
    assert merged["description"] == {
        "zh": "Published description",
        "en": "Published description",
    }


@pytest.mark.asyncio
async def test_export_snapshot_excludes_memory_sqlite_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    await source.aupload_many(
        [
            ("SOUL.md", b"# Source soul"),
            ("memory.sqlite", b"sqlite"),
            ("memory.sqlite-wal", b"wal"),
            ("memory.sqlite-shm", b"shm"),
        ]
    )

    destination = tmp_path / "published"
    exported = await export_agent_workspace_to_dir(
        workspace=source,
        dest=destination,
        metadata=PublishedExpertSnapshotMeta(
            name="Expert",
            description="desc",
            icon_name=None,
            color=None,
            label_zh="专家",
            label_en="Expert",
            welcome_message_zh="欢迎",
            welcome_message_en="Welcome",
        ),
        manifest_id="expert",
    )

    assert set(exported) == {MANIFEST_FILENAME, "SOUL.md"}
    assert not (destination / "memory.sqlite").exists()


@pytest.mark.asyncio
async def test_export_snapshot_builds_manifest_from_publish_metadata_only(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    manifest = {
        "id": "general-assistant",
        "label": {"zh": "旧名称", "en": "Old name"},
        "description": {"zh": "旧说明", "en": "Old description"},
        "welcome_message": {"zh": "欢迎回来", "en": "Welcome back"},
        "quick_prompts": [{"title": {"zh": "开始", "en": "Start"}}],
        "icon_name": "zap",
        "color": "#111111",
        "skillhub": {"manifest_generated": {"by": "test"}},
    }
    await source.aupload_many(
        [
            (MANIFEST_FILENAME, json.dumps(manifest, ensure_ascii=False).encode()),
            ("SOUL.md", b"# Source soul"),
        ]
    )

    destination = tmp_path / "published-expert"
    await export_agent_workspace_to_dir(
        workspace=source,
        dest=destination,
        metadata=PublishedExpertSnapshotMeta(
            name="Research Expert",
            description="Helps with research",
            icon_name="search",
            color="#123456",
            label_zh="研究专家",
            label_en="Research Expert",
            welcome_message_zh="开始研究吧",
            welcome_message_en="Start researching",
        ),
        manifest_id="research-expert",
    )

    merged = json.loads((destination / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert merged["id"] == "research-expert"
    assert merged["label"] == {"zh": "研究专家", "en": "Research Expert"}
    assert merged["description"] == {
        "zh": "Helps with research",
        "en": "Helps with research",
    }
    assert merged["welcome_message"] == {
        "zh": "开始研究吧",
        "en": "Start researching",
    }
    assert "quick_prompts" not in merged
    assert "skillhub" not in merged
    assert merged["icon_name"] == "search"
    assert merged["color"] == "#123456"
    assert merged["prompt_files"] == ["SOUL.md"]


@pytest.mark.asyncio
async def test_export_snapshot_includes_subagent_definitions(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    await source.aupload_many(
        [
            ("SOUL.md", b"# Soul"),
            ("references/extra.json", b"{}"),
            ("agents/reviewer.md", b"# Reviewer"),
            ("skills/demo/SKILL.md", b"# Skill"),
        ]
    )

    destination = tmp_path / "published"
    exported = await export_agent_workspace_to_dir(
        workspace=source,
        dest=destination,
        metadata=PublishedExpertSnapshotMeta(
            name="Expert",
            description="desc",
            icon_name=None,
            color=None,
            label_zh="专家",
            label_en="Expert",
            welcome_message_zh="",
            welcome_message_en="",
        ),
        manifest_id="expert",
    )

    assert set(exported) == {
        MANIFEST_FILENAME,
        "SOUL.md",
        "agents/reviewer.md",
        "skills/demo/SKILL.md",
    }
    assert not (destination / "references").exists()


@pytest.mark.asyncio
async def test_export_snapshot_builds_manifest_from_publish_metadata(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = _workspace(source_dir)
    await source.aupload_many([("SOUL.md", b"# Source soul")])
    metadata = PublishedExpertSnapshotMeta(
        name="Research Expert",
        description="Helps with research",
        icon_name="search",
        color="#123456",
        label_zh="研究专家",
        label_en="Research Expert",
        welcome_message_zh="开始研究",
        welcome_message_en="Start researching",
    )

    destination = tmp_path / "research-expert"
    exported = await export_agent_workspace_to_dir(
        workspace=source,
        dest=destination,
        metadata=metadata,
        manifest_id="research-expert",
    )

    assert set(exported) == {MANIFEST_FILENAME, "SOUL.md"}
    assert json.loads((destination / MANIFEST_FILENAME).read_text(encoding="utf-8")) == {
        "id": "research-expert",
        "label": {"zh": "研究专家", "en": "Research Expert"},
        "description": {"zh": "Helps with research", "en": "Helps with research"},
        "welcome_message": {"zh": "开始研究", "en": "Start researching"},
        "icon_name": "search",
        "color": "#123456",
        "prompt_files": ["SOUL.md"],
    }
