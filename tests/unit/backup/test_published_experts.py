"""Published expert snapshots must survive system backup and restore."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.config import DatabaseConfig
from octop.infra.agents.experts.published_creation import (
    PublishedExpertInstallOptions,
    install_published_expert,
)
from octop.infra.backup.auto import create_and_store_auto_backup
from octop.infra.backup.store import peek_backup_contents
from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.published_experts import PublishedExpertRepo
from octop.infra.users.identity import Role, User
from octop.infra.utils.paths import PathLayout


@pytest.mark.parametrize("automatic", [False, True], ids=["manual", "automatic"])
async def test_restored_published_expert_can_be_installed(tmp_path: Path, automatic: bool) -> None:
    source = PathLayout(tmp_path / "source")
    source_pool = SqlitePool(source.db)
    run_migrations(source_pool)
    PublishedExpertRepo(source_pool).create(
        id="published01", slug="writer", name="Writer", created_by="1"
    )
    snapshot = source.published_experts_dir / "published01"
    snapshot.mkdir(parents=True)
    (snapshot / "SOUL.md").write_text("# Published writer", encoding="utf-8")
    skill = snapshot / "skills" / "writer" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: writer\ndescription: Write\n---\n", encoding="utf-8")
    manifest_data = {"id": "writer", "welcome_message": {"en": "Welcome"}}
    (snapshot / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    try:
        if automatic:
            entry, _ = create_and_store_auto_backup(
                paths=source,
                agent_rows=[],
                pool=source_pool,
                db_config=DatabaseConfig(),
                retention_count=1,
            )
            archive = source.backup_file(entry.name)
        else:
            create_system_backup(
                paths=source,
                agent_rows=[],
                pool=source_pool,
                db_config=DatabaseConfig(),
                dest=archive,
            )
    finally:
        source_pool.close()

    target = PathLayout(tmp_path / "target")
    stale = target.published_experts_dir / "stale" / "SOUL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("outdated", encoding="utf-8")
    target_pool = SqlitePool(target.db)
    run_migrations(target_pool)
    try:
        result = restore_system_backup(
            archive, paths=target, pool=target_pool, db_config=DatabaseConfig()
        )
        workspace_root = target.ensure_agent_workspace("installed01")
        workspace = BackendWorkspace(
            LocalShellBackend(root_dir=str(workspace_root), virtual_mode=False), workspace_root
        )
        created = SimpleNamespace(
            id="installed01",
            agent_id="installed01",
            user_id=1,
            name="Installed writer",
            description="",
            default_model=None,
            last_state="stopped",
        )

        async def create_agent(spec: Any, **kwargs: Any) -> Any:
            assert spec.published_expert_id == "published01"
            await kwargs["workspace_initializer"](created, workspace)
            return created

        registry = SimpleNamespace(
            create=AsyncMock(side_effect=create_agent), is_bootstrapped=lambda _: False
        )
        installed = await install_published_expert(
            services=SimpleNamespace(
                paths=target, published_expert_repo=PublishedExpertRepo(target_pool)
            ),
            registry=registry,
            user=User(id=1, username="owner", role=Role.ADMIN, display_name=None),
            expert_id="published01",
            options=PublishedExpertInstallOptions(name="Installed writer"),
        )
        assert installed["published_expert_id"] == "published01"
        assert result["published_expert_files"] == 3
        assert not stale.exists()
        assert peek_backup_contents(archive).includes_workspaces is True
        if automatic:
            assert entry.includes_workspaces is True
        assert await workspace.aread_text("SOUL.md") == "# Published writer"
        assert await workspace.aread_text("skills/writer/SKILL.md") == skill.read_text(
            encoding="utf-8"
        )
        assert json.loads(await workspace.aread_text(".octop/manifest.json")) == manifest_data
    finally:
        target_pool.close()


@pytest.mark.parametrize("mode", ["omitted", "legacy", "legacy-workspaces", "empty"])
def test_restore_published_snapshots_respects_manifest(tmp_path: Path, mode: str) -> None:
    source = PathLayout(tmp_path / "source")
    source_pool = SqlitePool(source.db)
    run_migrations(source_pool)
    if mode in {"omitted", "legacy"}:
        snapshot = source.published_experts_dir / "published01" / "SOUL.md"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text("snapshot", encoding="utf-8")
    agent_rows = []
    if mode == "legacy-workspaces":
        workspace = source.ensure_agent_workspace("source01")
        (workspace / "SOUL.md").write_text("# Source agent", encoding="utf-8")
        agent_rows.append(SimpleNamespace(agent_id="source01", name="Source agent"))
    include_workspaces = mode in {"empty", "legacy-workspaces"}
    archive = tmp_path / "backup.tar.gz"
    try:
        create_system_backup(
            paths=source,
            agent_rows=agent_rows,
            pool=source_pool,
            db_config=DatabaseConfig(),
            dest=archive,
            include_workspaces=include_workspaces,
        )
    finally:
        source_pool.close()
    with tarfile.open(archive) as tf:
        manifest = json.loads(tf.extractfile("manifest.json").read())
        assert manifest["includes_published_experts"] is include_workspaces
        assert not any(name.startswith("published_experts/") for name in tf.getnames())
        if mode.startswith("legacy"):
            extracted = tmp_path / "extracted"
            tf.extractall(extracted, filter=tarfile.data_filter)
    if mode.startswith("legacy"):
        del manifest["includes_published_experts"]
        (extracted / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with tarfile.open(archive, "w:gz") as tf:
            for name in ("manifest.json", "db/octop.db"):
                tf.add(extracted / name, arcname=name)
            if mode == "legacy-workspaces":
                tf.add(extracted / "workspaces", arcname="workspaces")

    target = PathLayout(tmp_path / "target")
    current = target.published_experts_dir / "current" / "SOUL.md"
    current.parent.mkdir(parents=True)
    current.write_text("keep", encoding="utf-8")
    target_pool = SqlitePool(target.db)
    run_migrations(target_pool)
    try:
        result = restore_system_backup(
            archive, paths=target, pool=target_pool, db_config=DatabaseConfig()
        )
    finally:
        target_pool.close()
    assert result["published_expert_files"] == 0
    if mode == "legacy-workspaces":
        assert (target.agent_workspace("source01") / "SOUL.md").read_text(
            encoding="utf-8"
        ) == "# Source agent"
    if mode == "empty":
        assert not current.exists()
    else:
        assert current.read_text(encoding="utf-8") == "keep"
