"""Named local storage must share one workspace with runtime skill discovery."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from deepagents.middleware.skills import SkillsMiddleware
from langgraph.runtime import Runtime
from octop_harness.backends import resolve_backend
from octop_harness.backends.workspace import BackendWorkspace

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.skills.skill_transfer import copy_workspace_skill_to_workspace
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = PathLayout(tmp_path / "octop-home")
    paths.ensure_root()
    pool = SqlitePool(paths.db)
    run_migrations(pool)
    services = build_shared_services(db=pool, paths=paths, config=OctopConfig())
    result = AgentManager(repos=services.repos, paths=paths)
    monkeypatch.setattr(result, "_start_agent", AsyncMock(return_value=None))
    try:
        yield result
    finally:
        pool.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["filesystem", "shell"])
@pytest.mark.parametrize("composite", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
async def test_named_local_workspace_remains_visible_to_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    composite: bool,
    explicit: bool,
) -> None:
    paths = PathLayout(tmp_path / "octop-home")
    paths.ensure_root()
    pool = SqlitePool(paths.db)
    run_migrations(pool)
    services = build_shared_services(db=pool, paths=paths, config=OctopConfig())
    root = tmp_path / "selected-storage"
    root.mkdir()
    services.storage_backend_repo.create(
        name="local-files", kind=kind, config_json=json.dumps({"root_dir": str(root)})
    )
    named = {"type": "named", "name": "local-files"}
    backend = {"type": "composite", "default": named, "routes": {}} if composite else named
    config = {"backend": backend}
    if explicit:
        config["workspace_dir"] = str(root / "custom-workspace")
    manager = AgentManager(repos=services.repos, paths=paths)
    # Only model/graph startup is replaced. DB, backend, copy and discovery are real.
    monkeypatch.setattr(manager, "_start_agent", AsyncMock(return_value=None))
    try:
        row = await manager.create(AgentCreateSpec(name="storage probe", config=config))
        workspace = manager.workspace_for_agent(row.agent_id)
        assert workspace is not None
        stored = manager.get_config(row.agent_id)
        assert stored["backend"] == backend
        expected = (
            root / "custom-workspace" if explicit else root / ".octop" / "workspaces" / row.agent_id
        ).resolve()

        source_root = tmp_path / "source"
        source_root.mkdir()
        source = BackendWorkspace(
            resolve_backend({"type": "filesystem", "root_dir": str(source_root)}),
            source_root,
        )
        manifest = "---\nname: demo\ndescription: A copied demo skill\n---\n# Demo\n"
        await source.awrite_text("skills/demo/SKILL.md", manifest)
        await source.awrite_text("skills/demo/refs/note.txt", "supporting file")
        await copy_workspace_skill_to_workspace(source=source, destination=workspace, slug="demo")

        restarted = AgentManager(repos=services.repos, paths=paths)
        reopened = restarted.workspace_for_agent(row.agent_id)
        assert reopened is not None
        assert await reopened.aread_text("skills/demo/refs/note.txt") == "supporting file"
        middleware = SkillsMiddleware(backend=reopened.backend, sources=reopened.skill_paths())
        discovered = await middleware.abefore_agent({}, Runtime(), {})
        assert discovered is not None
        assert [skill["name"] for skill in discovered["skills_metadata"]] == ["demo"]
        assert manager.resolve_workspace_dir(row.agent_id) == expected
        assert (expected / ".octop" / "skills" / "demo" / "SKILL.md").read_text() == manifest
        assert not (paths.agent_workspace(row.agent_id) / ".octop" / "skills").exists()
        if kind == "shell":
            harness_config = restarted._build_harness_config(row)
            spec = harness_config.backend
            if composite:
                spec = spec["default"]
            relative = expected.relative_to(root).as_posix()
            assert spec["env"]["OCTOP_SKILLS_DIR"] == f"/{relative}/.octop/skills"
    finally:
        pool.close()


@pytest.mark.asyncio
async def test_named_host_root_retains_classic_workspace(manager: AgentManager) -> None:
    manager._repos.storage_backend_repo.create(
        name="host-files", kind="filesystem", config_json=json.dumps({"root_dir": "/"})
    )
    backend = {"type": "named", "name": "host-files"}
    row = await manager.create(AgentCreateSpec(name="host", config={"backend": backend}))
    assert manager.resolve_workspace_dir(row.agent_id) == manager.paths.agent_workspace(
        row.agent_id
    )
    assert manager.get_config(row.agent_id)["backend"] == backend


@pytest.mark.asyncio
async def test_named_cloud_retains_local_state_directory(manager: AgentManager) -> None:
    manager._repos.storage_backend_repo.create(
        name="cloud",
        kind="s3",
        bucket="demo-bucket",
        access_key="test-id",
        secret_key="test-secret",
    )
    backend = {"type": "named", "name": "cloud"}
    row = await manager.create(AgentCreateSpec(name="cloud", config={"backend": backend}))
    assert manager.resolve_workspace_dir(row.agent_id) == manager.paths.agent_workspace(
        row.agent_id
    )
    assert manager.get_config(row.agent_id)["backend"] == backend
    assert "test-secret" not in manager.get_row(row.agent_id).config_json


@pytest.mark.asyncio
async def test_inline_scoped_default_keeps_agent_facing_config(
    manager: AgentManager, tmp_path: Path
) -> None:
    root = tmp_path / "inline-root"
    row = await manager.create(
        AgentCreateSpec(
            name="inline", config={"backend": {"type": "filesystem", "root_dir": str(root)}}
        )
    )
    assert manager.get_config(row.agent_id)["workspace_dir"] == f"/.octop/workspaces/{row.agent_id}"
    assert (
        manager.resolve_workspace_dir(row.agent_id)
        == (root / ".octop" / "workspaces" / row.agent_id).resolve()
    )


@pytest.mark.asyncio
async def test_missing_named_storage_does_not_create_workspace(manager: AgentManager) -> None:
    with pytest.raises(ValueError, match="not found"):
        await manager.create(
            AgentCreateSpec(
                agent_id="MISS01",
                name="missing",
                config={"backend": {"type": "named", "name": "missing"}},
            )
        )
    assert manager._repos.agent_repo.get("MISS01") is None
    assert not manager.paths.agent_workspace("MISS01").exists()


def test_existing_named_workspace_is_not_relocated(manager: AgentManager, tmp_path: Path) -> None:
    original = tmp_path / "existing-workspace"
    original.mkdir()
    (original / "keep.txt").write_text("existing data", encoding="utf-8")
    manager._repos.storage_backend_repo.create(
        name="local",
        kind="filesystem",
        config_json=json.dumps({"root_dir": str(tmp_path / "storage")}),
    )
    config = {"backend": {"type": "named", "name": "local"}, "workspace_dir": str(original)}
    manager._repos.agent_repo.create(
        agent_id="OLD001", name="existing", user_id=None, config_json=json.dumps(config)
    )
    assert manager.resolve_workspace_dir("OLD001") == original.resolve()
    assert manager.get_config("OLD001") == config
    assert (original / "keep.txt").read_text(encoding="utf-8") == "existing data"


@pytest.mark.asyncio
async def test_explicit_relative_workspace_keeps_its_original_meaning(
    manager: AgentManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    manager._repos.storage_backend_repo.create(
        name="local",
        kind="filesystem",
        config_json=json.dumps({"root_dir": str(tmp_path / "storage")}),
    )
    row = await manager.create(
        AgentCreateSpec(
            name="relative",
            config={
                "backend": {"type": "named", "name": "local"},
                "workspace_dir": "custom/./workspace",
            },
        )
    )
    assert manager.get_config(row.agent_id)["workspace_dir"] == "custom/./workspace"
    assert (
        manager.resolve_workspace_dir(row.agent_id) == (tmp_path / "custom" / "workspace").resolve()
    )
