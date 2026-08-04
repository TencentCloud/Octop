"""Unit tests for agent skill package mounts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager, skill_package_ids_list
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return AgentManager(repos=services.repos, paths=services.paths)


def test_skill_package_ids_list_keeps_only_non_empty_list_items() -> None:
    assert skill_package_ids_list({"skill_package_ids": ["PACK01", "", 2]}) == ["PACK01", "2"]
    assert skill_package_ids_list({"skill_package_ids": "PACK01"}) == []


@pytest.mark.asyncio
async def test_persist_skill_package_ids_hot_syncs_without_reload(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mounting packages must hot-sync skills_dir — not tear down the agent."""
    from unittest.mock import MagicMock

    agent_id = "AGENT01"
    package_id = "PACK01"
    manager._repos.agent_repo.create(agent_id=agent_id, user_id=None, name="agent")
    manager._repos.skill_package_repo.create(
        id=package_id,
        name="Package",
        created_by="1",
    )

    fake_agent = MagicMock()
    fake_agent.config = MagicMock()
    fake_hm = MagicMock()
    fake_hm.get_agent.return_value = MagicMock(agent=fake_agent)
    manager._harness_manager = fake_hm

    scheduled: list[str] = []
    monkeypatch.setattr(manager, "_schedule_reload", lambda aid: scheduled.append(aid))

    await manager.persist_skill_package_ids(agent_id, [package_id])

    assert manager.get_config(agent_id)["skill_package_ids"] == [package_id]
    expected = str((manager.paths.skill_packages_dir / package_id / "skills").resolve())
    assert fake_agent.config.skills_dir == [expected]
    fake_agent.reload_subagents.assert_called_once_with()
    assert scheduled == []
    assert agent_id not in manager._reload_dirty


@pytest.mark.asyncio
async def test_persist_skill_package_ids_rejects_non_host_root_backend(
    manager: AgentManager,
) -> None:
    agent_id = "AGENT01"
    package_id = "PACK01"
    manager._repos.agent_repo.create(
        agent_id=agent_id,
        user_id=None,
        name="agent",
        config_json='{"backend":{"type":"local_shell","root_dir":"/tmp/octop","virtual_mode":true}}',
    )
    manager._repos.skill_package_repo.create(id=package_id, name="Package", created_by="1")

    with pytest.raises(OctopError) as exc_info:
        await manager.persist_skill_package_ids(agent_id, [package_id])

    assert exc_info.value.code is ErrorCode.SKILL_PACKAGE_BACKEND_UNSUPPORTED


def test_assert_backend_supports_skill_packages_rejects_non_host_root(
    manager: AgentManager,
) -> None:
    with pytest.raises(OctopError) as exc_info:
        manager.assert_backend_supports_skill_packages(
            {"type": "local_shell", "root_dir": "/tmp/octop", "virtual_mode": True}
        )
    assert exc_info.value.code is ErrorCode.SKILL_PACKAGE_BACKEND_UNSUPPORTED


def test_assert_backend_supports_skill_packages_accepts_host_root(
    manager: AgentManager,
) -> None:
    manager.assert_backend_supports_skill_packages(
        {"type": "local_shell", "root_dir": "/", "virtual_mode": True}
    )


def test_assert_backend_supports_skill_packages_accepts_workspace_scoped_default(
    manager: AgentManager,
    tmp_path: Path,
) -> None:
    """Windows default scopes root_dir to the agent workspace — still local host."""
    workspace = tmp_path / "agent-ws"
    workspace.mkdir()
    manager.assert_backend_supports_skill_packages(
        {
            "type": "local_shell",
            "root_dir": str(workspace.resolve()),
            "virtual_mode": True,
        },
        workspace_dir=workspace,
    )


def test_backend_supports_host_skill_packages_accepts_workspace_root(
    manager: AgentManager,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    assert (
        manager._backend_supports_host_skill_packages(
            {
                "type": "local_shell",
                "root_dir": str(workspace.resolve()),
                "virtual_mode": True,
            },
            workspace_dir=workspace,
        )
        is True
    )
    assert (
        manager._backend_supports_host_skill_packages(
            {
                "type": "local_shell",
                "root_dir": str(workspace.resolve()),
                "virtual_mode": True,
            },
            workspace_dir=tmp_path / "other",
        )
        is False
    )


@pytest.mark.asyncio
async def test_persist_skill_package_ids_accepts_workspace_scoped_backend(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default Windows agents use workspace root_dir, not '/'."""
    from unittest.mock import MagicMock

    agent_id = "AGENT01"
    package_id = "PACK01"
    workspace = manager.paths.ensure_agent_workspace(agent_id)
    manager._repos.agent_repo.create(
        agent_id=agent_id,
        user_id=None,
        name="agent",
        config_json=(
            '{"backend":{"type":"local_shell","root_dir":'
            + json.dumps(str(workspace.resolve()))
            + ',"virtual_mode":true}}'
        ),
    )
    manager._repos.skill_package_repo.create(id=package_id, name="Package", created_by="1")

    fake_agent = MagicMock()
    fake_agent.config = MagicMock()
    fake_hm = MagicMock()
    fake_hm.get_agent.return_value = MagicMock(agent=fake_agent)
    manager._harness_manager = fake_hm
    monkeypatch.setattr(manager, "_schedule_reload", lambda _aid: None)

    await manager.persist_skill_package_ids(agent_id, [package_id])

    assert manager.get_config(agent_id)["skill_package_ids"] == [package_id]
    expected = str((manager.paths.skill_packages_dir / package_id / "skills").resolve())
    assert fake_agent.config.skills_dir == [expected]


@pytest.mark.asyncio
async def test_persist_skill_package_ids_rejects_unknown_package(
    manager: AgentManager,
) -> None:
    manager._repos.agent_repo.create(agent_id="AGENT01", user_id=None, name="agent")

    with pytest.raises(OctopError) as exc_info:
        await manager.persist_skill_package_ids("AGENT01", ["MISSING"])

    assert exc_info.value.code is ErrorCode.SKILL_PACKAGE_NOT_FOUND
    assert manager.get_config("AGENT01") == {}


def test_build_harness_config_includes_existing_skill_package_dirs(manager: AgentManager) -> None:
    package_id = "PACK01"
    agent_id = "AGENT01"
    manager._repos.skill_package_repo.create(
        id=package_id,
        name="Package",
        created_by="1",
    )
    manager._repos.agent_repo.create(
        agent_id=agent_id,
        user_id=None,
        name="agent",
        config_json='{"skill_package_ids":["PACK01", "MISSING"]}',
    )
    row = manager.get_row(agent_id)
    assert row is not None

    cfg = manager._build_harness_config(row)

    expected = str((manager.paths.skill_packages_dir / package_id / "skills").resolve())
    assert expected in list(cfg.skills_dir or [])


@pytest.mark.asyncio
async def test_strip_skill_package_id_removes_it_and_hot_syncs(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager._repos.agent_repo.create(
        agent_id="AGENT01",
        user_id=None,
        name="agent",
        config_json='{"skill_package_ids":["PACK01", "PACK02"]}',
    )
    manager._repos.skill_package_repo.create(id="PACK02", name="Package", created_by="1")
    synced: list[str] = []
    monkeypatch.setattr(manager, "sync_skill_package_dirs", synced.append)
    monkeypatch.setattr(
        manager, "_schedule_reload", lambda aid: (_ for _ in ()).throw(AssertionError(aid))
    )

    await manager.strip_skill_package_id("PACK01")

    assert manager.get_config("AGENT01")["skill_package_ids"] == ["PACK02"]
    assert synced == ["AGENT01"]


@pytest.mark.asyncio
async def test_refresh_agents_for_package_hot_syncs_only_mounted_agents(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager._repos.skill_package_repo.create(id="PACK01", name="Package", created_by="1")
    manager._repos.agent_repo.create(
        agent_id="MOUNTED",
        user_id=None,
        name="mounted",
        config_json='{"skill_package_ids":["PACK01"]}',
    )
    manager._repos.agent_repo.create(
        agent_id="OTHER",
        user_id=None,
        name="other",
        config_json='{"skill_package_ids":["PACK02"]}',
    )
    synced: list[str] = []
    monkeypatch.setattr(manager, "sync_skill_package_dirs", synced.append)
    monkeypatch.setattr(
        manager, "_schedule_reload", lambda aid: (_ for _ in ()).throw(AssertionError(aid))
    )

    await manager.refresh_agents_for_package("PACK01")

    assert synced == ["MOUNTED"]


@pytest.mark.asyncio
async def test_list_skill_summaries_relabels_mounted_package_skills(
    manager: AgentManager,
) -> None:
    """Harness lists package dirs as workspace; Octop marks mounted package slugs."""
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.skills.skill_package_store import SkillPackageStore

    agent_id = "AGENT01"
    package_id = "PACK01"
    manager._repos.agent_repo.create(
        agent_id=agent_id,
        user_id=None,
        name="agent",
        config_json=json.dumps(
            {
                "skill_package_ids": [package_id],
                "skills_disabled": ["pdf-reader"],
            }
        ),
    )
    manager._repos.skill_package_repo.create(id=package_id, name="Office", created_by="1")
    store = SkillPackageStore(
        repo=manager._repos.skill_package_repo,
        root=manager.paths.skill_packages_dir,
    )
    store.write_skill(
        package_id,
        "pdf-reader",
        [
            (
                "SKILL.md",
                b"---\nname: pdf-reader\ndescription: Read PDF documents\n---\n# PDF\n",
            )
        ],
    )
    store.write_skill(
        package_id,
        "sheet-helper",
        [
            (
                "SKILL.md",
                b"---\nname: sheet-helper\ndescription: package copy\n---\n# Sheets\n",
            )
        ],
    )

    async def _aread_text(path: str) -> str | None:
        if path == "skills/sheet-helper/SKILL.md":
            return "---\nname: sheet-helper\ndescription: workspace wins\n---\n# WS\n"
        return None

    fake_agent = MagicMock()
    fake_agent.workspace = MagicMock()
    fake_agent.workspace.aread_text = AsyncMock(side_effect=_aread_text)
    # Harness sees both via skills_dir / workspace, all as kind=workspace.
    fake_agent.list_skill_summaries = AsyncMock(
        return_value=[
            {
                "slug": "local-note",
                "name": "local-note",
                "description": "workspace skill",
                "enabled": True,
                "kind": "workspace",
            },
            {
                "slug": "pdf-reader",
                "name": "pdf-reader",
                "description": "Read PDF documents",
                "enabled": True,
                "kind": "workspace",
            },
            {
                "slug": "sheet-helper",
                "name": "sheet-helper",
                "description": "workspace wins",
                "enabled": True,
                "kind": "workspace",
            },
        ]
    )
    fake_hm = MagicMock()
    fake_hm.get_agent.return_value = MagicMock(agent=fake_agent)
    manager._harness_manager = fake_hm

    rows = await manager.list_skill_summaries(agent_id)
    by_slug = {row["slug"]: row for row in rows}

    assert set(by_slug) == {"local-note", "sheet-helper", "pdf-reader"}
    assert by_slug["pdf-reader"]["kind"] == "package"
    assert by_slug["pdf-reader"]["package_id"] == package_id
    assert by_slug["pdf-reader"]["enabled"] is False
    assert by_slug["sheet-helper"]["kind"] == "workspace"
    assert by_slug["local-note"]["kind"] == "workspace"
