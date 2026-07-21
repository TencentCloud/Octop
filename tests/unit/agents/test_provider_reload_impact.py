"""Tests for selective + parallel provider reload (faster confirm)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from tests.support.harness import build_harness_manager_mock

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


def _make_services(tmp_path: Path):
    db = DBPool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    services.provider_repo.create(
        name="test-openai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [{"id": "gpt-4o-mini", "name": "gpt-4o-mini", "enabled": True}],
        ),
    )
    services.provider_repo.create(
        name="other-llm",
        kind="openai",
        base_url="https://other.example.com/v1",
        api_key="sk-other",
        models_json=json.dumps(
            [{"id": "m1", "name": "m1", "enabled": True}],
        ),
    )
    return services


def _registry(services) -> AgentManager:
    reg = AgentManager(repos=services.repos, paths=services.paths)
    reg._harness_manager = build_harness_manager_mock(
        providers=reg.providers.build_harness_configs(),
    )
    return reg


def test_impact_ids_include_refs_failed_and_auto_for_active_provider(
    tmp_path: Path,
) -> None:
    services = _make_services(tmp_path)
    services.repos.settings_repo.set_active_model("test-openai", "gpt-4o-mini")

    services.repos.agent_repo.create(agent_id="ref-one", user_id=None, name="Ref")
    services.repos.agent_repo.set_state("ref-one", "running")
    services.repos.agent_repo.update_config(
        "ref-one",
        config_json=json.dumps({"providers": ["test-openai"]}),
    )

    services.repos.agent_repo.create(agent_id="pinned-other", user_id=None, name="Pinned")
    services.repos.agent_repo.set_state("pinned-other", "running")
    services.repos.agent_repo.update_config(
        "pinned-other",
        default_model="other-llm/m1",
    )

    services.repos.agent_repo.create(agent_id="auto-one", user_id=None, name="Auto")
    services.repos.agent_repo.set_state("auto-one", "running")

    services.repos.agent_repo.create(agent_id="failed-one", user_id=None, name="Failed")
    services.repos.agent_repo.set_state("failed-one", "failed")

    registry = _registry(services)
    ids = registry._provider_reload_impact_ids(provider_name="test-openai")
    assert set(ids) == {"ref-one", "auto-one", "failed-one"}
    assert "pinned-other" not in ids


def test_impact_ids_active_model_changed_only_auto_and_needing(
    tmp_path: Path,
) -> None:
    services = _make_services(tmp_path)
    services.repos.settings_repo.set_active_model("test-openai", "gpt-4o-mini")

    services.repos.agent_repo.create(agent_id="auto-one", user_id=None, name="Auto")
    services.repos.agent_repo.set_state("auto-one", "running")

    services.repos.agent_repo.create(agent_id="pinned", user_id=None, name="Pinned")
    services.repos.agent_repo.set_state("pinned", "running")
    services.repos.agent_repo.update_config("pinned", default_model="other-llm/m1")

    services.repos.agent_repo.create(agent_id="created-one", user_id=None, name="Created")
    services.repos.agent_repo.set_state("created-one", "created")

    registry = _registry(services)
    ids = registry._provider_reload_impact_ids(active_model_changed=True)
    assert set(ids) == {"auto-one", "created-one"}


@pytest.mark.asyncio
async def test_reload_agents_runs_in_parallel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = _make_services(tmp_path)
    registry = _registry(services)
    started = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow_reload(_agent_id: str) -> None:
        nonlocal started, peak
        async with lock:
            started += 1
            peak = max(peak, started)
        await asyncio.sleep(0.05)
        async with lock:
            started -= 1

    monkeypatch.setattr(registry, "_reload_agent", slow_reload)
    t0 = time.perf_counter()
    await registry._reload_agents(["a", "b", "c", "d"])
    elapsed = time.perf_counter() - t0
    assert peak >= 2
    assert elapsed < 0.15


@pytest.mark.asyncio
async def test_on_provider_changed_selective_skips_unrelated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = _make_services(tmp_path)
    services.repos.settings_repo.set_active_model("other-llm", "m1")
    services.repos.agent_repo.create(agent_id="ref-one", user_id=None, name="Ref")
    services.repos.agent_repo.set_state("ref-one", "running")
    services.repos.agent_repo.update_config(
        "ref-one",
        config_json=json.dumps({"providers": ["test-openai"]}),
    )
    services.repos.agent_repo.create(agent_id="unrelated", user_id=None, name="Unrelated")
    services.repos.agent_repo.set_state("unrelated", "running")
    services.repos.agent_repo.update_config("unrelated", default_model="other-llm/m1")

    registry = _registry(services)
    reload_mock = AsyncMock()
    monkeypatch.setattr(registry, "_reload_agents", reload_mock)

    await registry.on_provider_changed(provider_name="test-openai")

    reload_mock.assert_awaited_once()
    called_ids = set(reload_mock.await_args.args[0])
    assert called_ids == {"ref-one"}
