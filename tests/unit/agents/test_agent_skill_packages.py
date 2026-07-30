"""Unit tests for agent skill package mounts."""

from __future__ import annotations

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
async def test_persist_skill_package_ids_writes_config_and_schedules_reload(
    manager: AgentManager,
) -> None:
    agent_id = "AGENT01"
    package_id = "PACK01"
    manager._repos.agent_repo.create(agent_id=agent_id, user_id=None, name="agent")
    manager._repos.skill_package_repo.create(
        id=package_id,
        name="Package",
        created_by="1",
    )
    await manager.persist_skill_package_ids(agent_id, [package_id])

    assert manager.get_config(agent_id)["skill_package_ids"] == [package_id]
    assert agent_id in manager._reload_dirty


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

    assert str(manager.paths.skill_packages_dir / package_id / "skills") in list(
        cfg.skills_dir or []
    )


@pytest.mark.asyncio
async def test_strip_skill_package_id_removes_it_and_schedules_reload(
    manager: AgentManager,
) -> None:
    manager._repos.agent_repo.create(
        agent_id="AGENT01",
        user_id=None,
        name="agent",
        config_json='{"skill_package_ids":["PACK01", "PACK02"]}',
    )
    manager._repos.skill_package_repo.create(id="PACK02", name="Package", created_by="1")
    await manager.strip_skill_package_id("PACK01")

    assert manager.get_config("AGENT01")["skill_package_ids"] == ["PACK02"]
    assert "AGENT01" in manager._reload_dirty


@pytest.mark.asyncio
async def test_refresh_agents_for_package_schedules_only_mounted_agents(
    manager: AgentManager,
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
    await manager.refresh_agents_for_package("PACK01")

    assert "MOUNTED" in manager._reload_dirty
    assert "OTHER" not in manager._reload_dirty
