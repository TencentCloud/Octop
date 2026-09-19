"""Tests for selective + parallel provider reload (faster confirm)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from tests.support.harness import build_harness_manager_mock

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


def _make_services(tmp_path: Path):
    db = SqlitePool(tmp_path / "octop.db")
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


@pytest.mark.asyncio
async def test_connector_reload_waits_before_setting_override_and_reads_latest_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    services = _make_services(tmp_path)
    services.repos.agent_repo.create(agent_id="a", user_id=None, name="Before")
    registry = _registry(services)
    bundle = MagicMock(side_effect=lambda row: (row.name, {}, [], "User"))
    monkeypatch.setattr(registry, "_agent_runtime_bundle", bundle)
    monkeypatch.setattr(registry, "_post_start_agent", AsyncMock())
    entered, release, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen = []

    async def rebuild(agent_id, config, **kwargs):
        seen.append((config, registry._connector_user_override.get(agent_id)))
        if len(seen) == 1:
            entered.set()
            await release.wait()
        return SimpleNamespace(agent=object())

    monkeypatch.setattr(registry._harness_manager, "arebuild_agent", AsyncMock(side_effect=rebuild))

    async def reload_connectors():
        second_started.set()
        await registry.reload_connectors("a", connector_user_id=11)

    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        tasks.create_task(registry.reload("a"))
        await entered.wait()
        tasks.create_task(reload_connectors())
        await second_started.wait()
        assert bundle.call_count == 1
        assert seen == [("Before", None)]
        assert registry._connector_user_override == {}
        services.repos.agent_repo.update_config("a", name="After")
        release.set()

    assert seen == [("Before", None), ("After", 11)]
    assert registry._connector_user_override == {}


@pytest.mark.asyncio
async def test_reload_lock_preserves_cross_agent_parallelism(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    services = _make_services(tmp_path)
    for agent_id in ("a", "b"):
        services.repos.agent_repo.create(agent_id=agent_id, user_id=None, name=agent_id)
    registry = _registry(services)
    monkeypatch.setattr(registry, "_agent_runtime_bundle", lambda row: (row.name, {}, [], "User"))
    monkeypatch.setattr(registry, "_post_start_agent", AsyncMock())
    entered = {agent_id: asyncio.Event() for agent_id in ("a", "b")}
    release = asyncio.Event()

    async def rebuild(agent_id, config, **kwargs):
        entered[agent_id].set()
        await release.wait()
        return SimpleNamespace(agent=object())

    monkeypatch.setattr(registry._harness_manager, "arebuild_agent", AsyncMock(side_effect=rebuild))
    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        tasks.create_task(registry._reload_agents(["a", "b"]))
        await asyncio.gather(*(event.wait() for event in entered.values()))
        release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["credentials", "rebuild"])
async def test_connector_reload_failure_clears_override_and_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    services = _make_services(tmp_path)
    services.repos.agent_repo.create(agent_id="a", user_id=None, name="Agent")
    registry = _registry(services)
    bundle = MagicMock(side_effect=lambda row: (row.name, {}, [], "User"))
    monkeypatch.setattr(registry, "_agent_runtime_bundle", bundle)
    monkeypatch.setattr(registry, "_post_start_agent", AsyncMock())
    visible = MagicMock(
        return_value=[SimpleNamespace(status="active", instance_id="connector", kind="test")]
    )
    monkeypatch.setattr(services.repos.connector_repo, "list_visible", visible)
    refresh = AsyncMock()
    rebuild = AsyncMock(return_value=SimpleNamespace(agent=object()))
    monkeypatch.setattr(registry._connector_svc, "ensure_fresh_credentials", refresh)
    monkeypatch.setattr(registry._harness_manager, "arebuild_agent", rebuild)
    failing = refresh if failure_stage == "credentials" else rebuild
    failing.side_effect = RuntimeError("reload failed")

    async with asyncio.timeout(5):
        if failure_stage == "credentials":
            with pytest.raises(RuntimeError, match="reload failed"):
                await registry.reload_connectors("a", connector_user_id=11)
        else:
            await registry.reload_connectors("a", connector_user_id=11)
            assert registry.get_row("a").last_state == "failed"
        assert registry._connector_user_override == {}
        assert not registry._lifecycle_lock_for("a").locked()

        failing.side_effect = None
        await registry.reload_connectors("a", connector_user_id=22)

    assert visible.call_args_list == [call(11), call(22)]
    assert registry.get_row("a").last_state == "running"
    assert registry._connector_user_override == {}
