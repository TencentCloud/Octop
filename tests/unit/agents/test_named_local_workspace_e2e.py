"""End-to-end check for #1641: named local storage seeds under the storage root."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from tests.support.harness import build_harness_manager_mock

from octop.config import OctopConfig
from octop.infra.agents.experts.catalog import Expert, ExpertCatalog, ExpertSummary
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


def _make_services(tmp_path: Path):
    octop_home = tmp_path / "octop-home"
    db = SqlitePool(octop_home / "octop.db")
    run_migrations(db)
    services = build_shared_services(
        db=db,
        paths=PathLayout(octop_home),
        config=OctopConfig(),
    )
    services.provider_repo.create(
        name="test-openai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [{"id": "gpt-4o-mini", "name": "gpt-4o-mini", "enabled": True}],
        ),
    )
    return services, octop_home


@pytest.mark.asyncio
async def test_named_filesystem_backend_seeds_soul_under_storage_root(
    tmp_path: Path,
) -> None:
    """Create named local storage + expert; SOUL/.octop live under storage, not OCTOP_HOME."""
    services, octop_home = _make_services(tmp_path)
    storage_root = tmp_path / "vol3" / "1000" / "workspaces"
    storage_root.mkdir(parents=True)
    services.repos.storage_backend_repo.create(
        name="fnos-disk",
        kind="filesystem",
        bucket=str(storage_root),
    )

    expert_dir = tmp_path / "experts-lib" / "plain"
    expert_dir.mkdir(parents=True)
    (expert_dir / "SOUL.md").write_text("# Named storage soul\n", encoding="utf-8")
    skill_dir = expert_dir / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo skill\n", encoding="utf-8")

    fake_catalog = MagicMock(spec=ExpertCatalog)
    fake_catalog.get = MagicMock(
        return_value=Expert(
            summary=ExpertSummary(
                id="plain",
                label_zh="测试",
                label_en="Test",
                description_zh="",
                description_en="",
            ),
            files=["SOUL.md", "skills/demo/SKILL.md"],
            prompt_files=["SOUL.md"],
        )
    )
    fake_catalog.expert_dir = MagicMock(return_value=expert_dir)

    fake_hm = build_harness_manager_mock(
        providers=AgentManager(
            repos=services.repos,
            paths=services.paths,
        ).providers.build_harness_configs(),
    )
    registry = AgentManager(
        repos=services.repos,
        paths=services.paths,
        expert_catalog=fake_catalog,
    )
    registry._harness_manager = fake_hm

    row = await registry.create(
        AgentCreateSpec(
            name="named-ws-bot",
            template_name="plain",
            config={"backend": {"type": "named", "name": "fnos-disk"}},
        )
    )

    cfg = json.loads(row.config_json or "{}")
    assert cfg["backend"] == {"type": "named", "name": "fnos-disk"}
    assert cfg["workspace_dir"] == f"/.octop/workspaces/{row.agent_id}"

    host_ws = registry.resolve_workspace_dir(row.agent_id)
    expected = (storage_root / ".octop" / "workspaces" / row.agent_id).resolve()
    assert host_ws == expected
    assert host_ws.is_dir()

    soul = host_ws / "SOUL.md"
    assert soul.is_file(), f"SOUL.md missing under storage workspace: {host_ws}"
    assert soul.read_text(encoding="utf-8") == "# Named storage soul\n"

    skill_md = host_ws / ".octop" / "skills" / "demo" / "SKILL.md"
    assert skill_md.is_file(), f"skill missing under storage .octop: {host_ws}"
    assert skill_md.read_text(encoding="utf-8") == "# Demo skill\n"

    legacy = octop_home / "agents" / row.agent_id
    assert not legacy.exists(), f"workspace incorrectly created under OCTOP_HOME: {legacy}"
    assert not (octop_home / "agents" / row.agent_id / "SOUL.md").exists()

    # Runtime read through the harness workspace should see SOUL on the
    # storage-backed mount (skills live under system_files_path=.octop).
    agent = registry.get_agent(row.agent_id)
    text = await agent.workspace.aread_text("SOUL.md")
    assert text == "# Named storage soul\n"
