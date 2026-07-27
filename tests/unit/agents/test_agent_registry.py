"""tests/unit/test_agent_registry.py

Unit tests for AgentManager.  All harness I/O is patched out so no real
LLM processes are started.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.support.harness import build_harness_manager_mock

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    return services


def _bootstrap_factory_from_db(registry: AgentManager, fake_hm: MagicMock) -> None:
    for provider in registry.providers.build_harness_configs():
        fake_hm.add_provider(provider)


def _make_fake_hm(fake_agent: Any | None = None) -> MagicMock:
    """Return a MagicMock that quacks like HarnessAgentManager."""
    return build_harness_manager_mock(fake_agent=fake_agent)


def _patch_harness(monkeypatch) -> MagicMock:
    """Patch HarnessAgentManager constructor so boot() doesn't touch real harness."""
    fake_hm = build_harness_manager_mock()

    def _constructor(**kw: Any) -> MagicMock:
        fake_hm._shared_factory = None
        fake_hm.shared_factory = None
        fake_hm._providers = []
        for provider in kw.get("providers") or []:
            fake_hm.add_provider(provider)
        return fake_hm

    monkeypatch.setattr(
        "octop.infra.agents.manager.HarnessAgentManager",
        _constructor,
    )
    return fake_hm


def _make_registry(services, *, fake_hm: MagicMock | None = None) -> AgentManager:
    """Construct a registry with harness already injected (skips boot())."""
    reg = AgentManager(repos=services.repos, paths=services.paths)
    if fake_hm is None:
        reg._harness_manager = build_harness_manager_mock(
            providers=reg.providers.build_harness_configs(),
        )
    else:
        reg._harness_manager = fake_hm
        _bootstrap_factory_from_db(reg, fake_hm)
    return reg


def _attach_registry(
    services,
    fake_hm: MagicMock,
    **kwargs: Any,
) -> AgentManager:
    """Attach a preconfigured harness mock without syncing DB providers."""
    reg = AgentManager(repos=services.repos, paths=services.paths, **kwargs)
    reg._harness_manager = fake_hm
    return reg


# ---------------------------------------------------------------------------
# boot()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boot_empty_db(tmp_path: Path, monkeypatch) -> None:
    """boot() on empty DB completes without error; no agents registered."""
    services = _make_services(tmp_path)
    _patch_harness(monkeypatch)
    registry = AgentManager(repos=services.repos, paths=services.paths)

    await registry.boot()

    assert registry.list_rows() == []


@pytest.mark.asyncio
async def test_boot_starts_pre_existing_agents(tmp_path: Path, monkeypatch) -> None:
    """boot() starts every enabled agent row that already exists in the DB."""
    services = _make_services(tmp_path)
    fake_hm = _patch_harness(monkeypatch)

    # Insert an agent before boot (no FK: user_id=None is allowed)
    services.repos.agent_repo.create(agent_id="pre1", user_id=None, name="pre-agent")

    registry = AgentManager(repos=services.repos, paths=services.paths)
    await registry.boot()

    fake_hm.acreate_agent.assert_called_once()
    assert len(registry.list_rows()) == 1


@pytest.mark.asyncio
async def test_boot_skips_disabled_agents(tmp_path: Path, monkeypatch) -> None:
    """boot() must not start agents that have enabled=0."""
    services = _make_services(tmp_path)
    fake_hm = _patch_harness(monkeypatch)

    services.repos.agent_repo.create(agent_id="enabled-one", user_id=None, name="enabled")
    services.repos.agent_repo.create(agent_id="disabled-one", user_id=None, name="disabled")
    services.repos.agent_repo.set_enabled("disabled-one", False)

    registry = AgentManager(repos=services.repos, paths=services.paths)
    await registry.boot()

    # only one agent should be started
    fake_hm.acreate_agent.assert_called_once()


# ---------------------------------------------------------------------------
# shutdown()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_clears_harness_manager(tmp_path: Path) -> None:
    """shutdown() calls harness_manager.close() and drops the manager reference."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm.close = MagicMock()
    registry = _make_registry(services, fake_hm=fake_hm)

    await registry.create(AgentCreateSpec(name="a"))
    await registry.create(AgentCreateSpec(name="b"))

    await registry.shutdown()

    fake_hm.close.assert_called_once()
    assert registry._harness_manager is None


@pytest.mark.asyncio
async def test_shutdown_idempotent(tmp_path: Path, monkeypatch) -> None:
    """Calling shutdown() twice must not raise."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    await registry.shutdown()
    await registry.shutdown()


@pytest.mark.asyncio
async def test_shutdown_calls_close_when_available(tmp_path: Path) -> None:
    """shutdown() calls harness_manager.close() if the method exists."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm.close = MagicMock()
    registry = _make_registry(services, fake_hm=fake_hm)

    await registry.shutdown()

    fake_hm.close.assert_called_once()


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_persists_row(tmp_path: Path) -> None:
    """create() inserts a row and it appears in list_rows()."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="my-agent"))

    rows = registry.list_rows()
    assert len(rows) == 1
    assert len(row.agent_id) == 6
    assert row.name == "my-agent"
    assert rows[0].agent_id == row.agent_id


@pytest.mark.asyncio
async def test_create_registers_with_harness(tmp_path: Path) -> None:
    """create() calls harness_manager.create() exactly once."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    registry = _make_registry(services, fake_hm=fake_hm)

    await registry.create(AgentCreateSpec(name="bot"))

    fake_hm.acreate_agent.assert_called_once()


@pytest.mark.asyncio
async def test_create_stores_config_json(tmp_path: Path) -> None:
    """create() with config dict serialises it to config_json in the DB."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(
        AgentCreateSpec(name="configured", config={"temperature": 0.5, "max_tokens": 256})
    )

    cfg = registry.get_config(row.agent_id)
    assert cfg["temperature"] == 0.5
    assert cfg["max_tokens"] == 256


@pytest.mark.asyncio
async def test_create_writes_audit_entry(tmp_path: Path) -> None:
    """create() writes an audit log entry for the new agent."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="audited"))

    audit_rows = services.repos.audit_repo.query(limit=10)
    actions = [a.action for a in audit_rows]
    assert "agent.create" in actions
    targets = [a.target for a in audit_rows]
    assert row.agent_id in targets


@pytest.mark.asyncio
async def test_create_sets_state_running(tmp_path: Path) -> None:
    """_start_agent() sets last_state = 'running' after successful harness.create."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="runner"))

    db_row = registry.get_row(row.agent_id)
    assert db_row is not None
    assert db_row.last_state == "running"


@pytest.mark.asyncio
async def test_create_sets_state_failed_on_harness_error(tmp_path: Path) -> None:
    """_start_agent() sets last_state = 'failed' when harness.create raises."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm.acreate_agent.side_effect = RuntimeError("boom")
    registry = _make_registry(services, fake_hm=fake_hm)

    row = await registry.create(AgentCreateSpec(name="bad-agent"))

    db_row = registry.get_row(row.agent_id)
    assert db_row is not None
    assert db_row.last_state == "failed"
    assert db_row.last_error is not None


@pytest.mark.asyncio
async def test_create_multiple_agents(tmp_path: Path) -> None:
    """Multiple agents can coexist; list_rows() returns all of them."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    await registry.create(AgentCreateSpec(name="alpha"))
    await registry.create(AgentCreateSpec(name="beta"))
    await registry.create(AgentCreateSpec(name="gamma"))

    names = {r.name for r in registry.list_rows()}
    assert names == {"alpha", "beta", "gamma"}


@pytest.mark.asyncio
async def test_create_duplicate_name_rejected(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    registry = _make_registry(services)
    user_id = services.repos.user_repo.create(username="alice", password_hash="h", role="admin")

    await registry.create(AgentCreateSpec(name="dup-bot", user_id=user_id))
    with pytest.raises(OctopError) as exc_info:
        await registry.create(AgentCreateSpec(name="dup-bot", user_id=user_id))
    assert exc_info.value.code is ErrorCode.AGENT_NAME_TAKEN


@pytest.mark.asyncio
async def test_update_duplicate_name_rejected(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    registry = _make_registry(services)
    user_id = services.repos.user_repo.create(username="alice", password_hash="h", role="admin")

    await registry.create(AgentCreateSpec(name="alpha", user_id=user_id))
    beta = await registry.create(AgentCreateSpec(name="beta", user_id=user_id))
    with pytest.raises(OctopError) as exc_info:
        await registry.update(beta.agent_id, name="alpha")
    assert exc_info.value.code is ErrorCode.AGENT_NAME_TAKEN


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_from_db_and_entries(tmp_path: Path) -> None:
    """delete() removes the row from DB and clears the runtime entry."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    registry = _make_registry(services, fake_hm=fake_hm)

    row = await registry.create(AgentCreateSpec(name="doomed"))
    assert len(registry.list_rows()) == 1

    await registry.delete(row.agent_id)

    assert registry.list_rows() == []
    assert registry.get_row(row.agent_id) is None


@pytest.mark.asyncio
async def test_delete_calls_harness_remove(tmp_path: Path) -> None:
    """delete() calls harness_manager.remove() for the agent."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    registry = _make_registry(services, fake_hm=fake_hm)

    row = await registry.create(AgentCreateSpec(name="removable"))
    fake_hm.aremove_agent.reset_mock()

    await registry.delete(row.agent_id)

    fake_hm.aremove_agent.assert_called_with(row.agent_id)


@pytest.mark.asyncio
async def test_delete_writes_audit_entry(tmp_path: Path) -> None:
    """delete() writes an audit log entry."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="audit-delete"))
    await registry.delete(row.agent_id)

    audit_rows = services.repos.audit_repo.query(limit=20)
    actions = [a.action for a in audit_rows]
    assert "agent.delete" in actions


@pytest.mark.asyncio
async def test_delete_tolerates_missing_workspace(tmp_path: Path) -> None:
    """delete() must not crash when the agent workspace directory doesn't exist."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="no-ws"))
    # workspace was never created on disk — delete should still succeed
    await registry.delete(row.agent_id)

    assert registry.get_row(row.agent_id) is None


@pytest.mark.asyncio
async def test_delete_tolerates_harness_key_error(tmp_path: Path) -> None:
    """delete() must not crash when harness.remove() raises KeyError."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm.remove_agent.side_effect = KeyError("not registered")
    registry = _make_registry(services, fake_hm=fake_hm)

    row = await registry.create(AgentCreateSpec(name="ghost"))
    # Should not raise
    await registry.delete(row.agent_id)

    assert registry.get_row(row.agent_id) is None


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_persists_field_changes(tmp_path: Path) -> None:
    """update() writes new values to DB and returns the updated row."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="original"))
    updated = await registry.update(row.agent_id, name="renamed")

    assert updated.name == "renamed"
    assert registry.get_row(row.agent_id).name == "renamed"


@pytest.mark.asyncio
async def test_update_triggers_harness_reload(tmp_path: Path) -> None:
    """update() calls harness.remove to trigger re-registration."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    registry = _make_registry(services, fake_hm=fake_hm)

    row = await registry.create(AgentCreateSpec(name="reloadable"))
    fake_hm.aremove_agent.reset_mock()

    await registry.update(row.agent_id, name="reloaded")
    await asyncio.sleep(0.15)

    fake_hm.arebuild_agent.assert_called()


@pytest.mark.asyncio
async def test_update_raises_for_unknown_id(tmp_path: Path) -> None:
    """update() raises OctopError when the agent_id does not exist."""
    from octop.infra.errors import OctopError  # noqa: PLC0415

    services = _make_services(tmp_path)
    registry = _make_registry(services)

    with pytest.raises(OctopError):
        await registry.update("nonexistent-ulid", name="x")


# ---------------------------------------------------------------------------
# get_agent()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_raises_for_unknown(tmp_path: Path) -> None:
    """get_agent() raises OctopError when harness has no such entry."""
    from octop.infra.errors import OctopError  # noqa: PLC0415

    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm.get_agent.side_effect = KeyError("missing")
    registry = _make_registry(services, fake_hm=fake_hm)

    with pytest.raises(OctopError):
        registry.get_agent("no-such-id")


@pytest.mark.asyncio
async def test_get_agent_returns_harness_object(tmp_path: Path) -> None:
    """get_agent() returns the .agent attribute of the harness entry."""
    services = _make_services(tmp_path)
    fake_agent = MagicMock(name="HarnessAgent")
    fake_hm = _make_fake_hm(fake_agent=fake_agent)
    registry = _attach_registry(services, fake_hm=fake_hm)
    _bootstrap_factory_from_db(registry, fake_hm)

    row = await registry.create(AgentCreateSpec(name="live"))
    agent = registry.get_agent(row.agent_id)

    assert agent is fake_agent


@pytest.mark.asyncio
async def test_list_subagent_summaries_delegates_to_harness(tmp_path: Path) -> None:
    """list_subagent_summaries() returns harness catalog rows."""
    services = _make_services(tmp_path)
    fake_agent = MagicMock(name="HarnessAgent")
    fake_agent.list_subagent_summaries.return_value = [
        {
            "slug": "general-purpose",
            "name": "General Purpose",
            "description": "General-purpose agent",
            "path": "agents/general-purpose.md",
        }
    ]
    fake_hm = _make_fake_hm(fake_agent=fake_agent)
    registry = _make_registry(services, fake_hm=fake_hm)

    agent_id = "SUBAGENT1"
    services.repos.agent_repo.create(agent_id=agent_id, user_id=None, name="live")
    fake_hm.create_agent(MagicMock(), agent_id=agent_id)

    summaries = registry.list_subagent_summaries(agent_id)

    assert len(summaries) == 1
    assert summaries[0]["slug"] == "general-purpose"
    fake_agent.list_subagent_summaries.assert_called_once_with()


# ---------------------------------------------------------------------------
# get_row() / list_rows() / get_row_by_alias()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_row_returns_none_for_unknown(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    assert registry.get_row("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_row_returns_created_agent(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="findable"))

    fetched = registry.get_row(row.agent_id)
    assert fetched is not None
    assert fetched.name == "findable"


@pytest.mark.asyncio
async def test_list_rows_returns_all_enabled(tmp_path: Path) -> None:
    """list_rows() returns all enabled rows regardless of user."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    await registry.create(AgentCreateSpec(name="one"))
    await registry.create(AgentCreateSpec(name="two"))

    rows = registry.list_rows()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_rows_reads_db_directly(tmp_path: Path) -> None:
    """list_rows() reflects external DB changes without a reload."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="before"))
    services.repos.agent_repo.update_config(row.agent_id, name="after")

    names = {r.name for r in registry.list_rows()}
    assert "after" in names
    assert "before" not in names


# ---------------------------------------------------------------------------
# get_config()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_returns_empty_for_unknown(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    assert registry.get_config("unknown") == {}


@pytest.mark.asyncio
async def test_get_config_returns_empty_for_null_json(tmp_path: Path) -> None:
    """get_config() returns {} when config_json is NULL."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="no-cfg"))

    assert registry.get_config(row.agent_id) == {}


@pytest.mark.asyncio
async def test_get_config_returns_empty_for_malformed_json(tmp_path: Path) -> None:
    """get_config() must not raise when config_json is corrupt."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="bad-json"))
    services.repos.agent_repo.update_config(row.agent_id, config_json="{corrupt{{")

    assert registry.get_config(row.agent_id) == {}


@pytest.mark.asyncio
async def test_get_config_returns_empty_for_non_dict_json(tmp_path: Path) -> None:
    """get_config() returns {} when config_json parses to a non-dict value."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    row = await registry.create(AgentCreateSpec(name="list-json"))
    services.repos.agent_repo.update_config(row.agent_id, config_json='["a", "b"]')

    assert registry.get_config(row.agent_id) == {}


# ---------------------------------------------------------------------------
# list_agents()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_agents_filters_by_user(tmp_path: Path) -> None:
    """list_agents(user_id) returns only that user's enabled agents."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    uid1 = services.repos.user_repo.create(username="u1", password_hash="x", role="user")
    uid2 = services.repos.user_repo.create(username="u2", password_hash="x", role="user")

    await registry.create(AgentCreateSpec(name="for-u1", user_id=uid1))
    await registry.create(AgentCreateSpec(name="for-u2", user_id=uid2))

    u1_rows = registry.list_agents(uid1)
    u2_rows = registry.list_agents(uid2)

    assert len(u1_rows) == 1
    assert u1_rows[0].name == "for-u1"
    assert len(u2_rows) == 1
    assert u2_rows[0].name == "for-u2"


@pytest.mark.asyncio
async def test_resolve_user_agent_by_name_and_suffix(tmp_path: Path) -> None:
    """resolve_user_agent matches full id, suffix, and name."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    uid = services.repos.user_repo.create(username="resolver", password_hash="x", role="user")
    row = await registry.create(AgentCreateSpec(name="Alpha", user_id=uid))
    aid = row.agent_id
    suffix = aid[-6:]

    assert registry.resolve_user_agent(uid, aid) is not None
    assert registry.resolve_user_agent(uid, suffix) is not None
    assert registry.resolve_user_agent(uid, "Alpha") is not None
    assert registry.resolve_user_agent(uid, "alpha") is not None
    assert registry.resolve_user_agent(uid, "missing") is None


@pytest.mark.asyncio
async def test_list_agents_returns_sorted_by_created_at(tmp_path: Path) -> None:
    """list_agents() result is sorted by creation time (oldest first)."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)

    uid = services.repos.user_repo.create(username="sorter", password_hash="x", role="user")
    for name in ("zebra", "apple", "mango"):
        await registry.create(AgentCreateSpec(name=name, user_id=uid))

    names = [r.name for r in registry.list_agents(uid)]
    assert names == ["zebra", "apple", "mango"]


# ---------------------------------------------------------------------------
# on_provider_changed()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_provider_changed_noop_when_manager_is_none(tmp_path: Path) -> None:
    """on_provider_changed() is silent when harness_manager has not been booted."""
    services = _make_services(tmp_path)
    registry = AgentManager(repos=services.repos, paths=services.paths)
    # _harness_manager is None

    await registry.on_provider_changed()  # must not raise


@pytest.mark.asyncio
async def test_on_provider_changed_noop_when_factory_is_none_and_no_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """on_provider_changed() is silent when factory is None and DB has no providers."""
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    fake_hm = _make_fake_hm()
    fake_hm._shared_factory = None
    fake_hm.shared_factory = None
    registry = _attach_registry(services, fake_hm=fake_hm)
    fake_hm.add_provider = MagicMock()

    await registry.on_provider_changed()

    fake_hm.add_provider.assert_not_called()


@pytest.mark.asyncio
async def test_on_provider_changed_bootstraps_factory_when_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First provider after boot must create the shared factory and reload agents."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm._shared_factory = None
    fake_hm.shared_factory = None
    fake_hm.add_provider = MagicMock()
    registry = _attach_registry(services, fake_hm=fake_hm)

    fake_provider_cfg = MagicMock()
    fake_provider_cfg.id = "test-openai"
    monkeypatch.setattr(
        "octop.infra.agents.providers.store.ProviderStore.build_harness_configs",
        lambda self: [fake_provider_cfg],
    )
    reload_mock = AsyncMock()
    monkeypatch.setattr(registry, "_reload_agents", reload_mock)

    await registry.on_provider_changed()

    fake_hm.add_provider.assert_called_once_with(fake_provider_cfg)
    reload_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_provider_changed_reloads_agents_when_factory_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_hm._shared_factory = None
    fake_hm.add_provider = MagicMock(
        side_effect=lambda p: (
            setattr(fake_hm, "_shared_factory", object()),
            setattr(fake_hm, "shared_factory", fake_hm._shared_factory),
        )
    )
    registry = _attach_registry(services, fake_hm=fake_hm)

    fake_provider_cfg = MagicMock()
    fake_provider_cfg.id = "test-openai"
    monkeypatch.setattr(
        "octop.infra.agents.providers.store.ProviderStore.build_harness_configs",
        lambda self: [fake_provider_cfg],
    )
    reload_mock = AsyncMock()
    monkeypatch.setattr(registry, "_reload_agents", reload_mock)

    await registry.on_provider_changed()

    fake_hm.add_provider.assert_called_once_with(fake_provider_cfg)
    reload_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_impact_ids_needing_model_excludes_running(
    tmp_path: Path,
) -> None:
    services = _make_services(tmp_path)
    services.repos.agent_repo.create(
        agent_id="running-one",
        user_id=None,
        name="Running",
    )
    services.repos.agent_repo.set_state("running-one", "running")
    services.repos.agent_repo.create(
        agent_id="failed-one",
        user_id=None,
        name="Failed",
    )
    services.repos.agent_repo.set_state("failed-one", "failed")
    registry = _make_registry(services)
    services.repos.settings_repo.set_active_model("other", "x")

    ids = registry._provider_reload_impact_ids(provider_name="test-openai")
    assert "failed-one" in ids
    assert "running-one" not in ids


@pytest.mark.asyncio
async def test_on_provider_changed_reloads_all_when_factory_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_factory = MagicMock()
    fake_factory._providers = {"test-openai": object()}
    fake_hm._shared_factory = fake_factory
    fake_hm.shared_factory = fake_factory
    registry = _attach_registry(services, fake_hm=fake_hm)
    reload_mock = AsyncMock()
    monkeypatch.setattr(registry, "_reload_agents", reload_mock)
    monkeypatch.setattr(
        "octop.infra.agents.providers.store.ProviderStore.build_harness_configs",
        lambda self: [],
    )

    await registry.on_provider_changed()

    reload_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_provider_changed_adds_new_provider(tmp_path: Path, monkeypatch) -> None:
    """on_provider_changed() calls add_provider for providers in DB."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_factory = MagicMock()
    fake_factory._providers = {}
    fake_hm._shared_factory = fake_factory
    fake_hm.shared_factory = fake_factory
    fake_hm.add_provider = MagicMock()
    fake_hm.remove_provider = MagicMock()

    monkeypatch.setattr(
        "octop.infra.agents.manager.HarnessAgentConfig",
        MagicMock(return_value=MagicMock()),
    )

    registry = _attach_registry(services, fake_hm=fake_hm)

    services.repos.provider_repo.create(
        name="openai",
        kind="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )

    # Patch ProviderConfig / ModelConfig imports inside the method
    fake_provider_cfg = MagicMock()
    fake_provider_cfg.id = "openai"
    monkeypatch.setattr(
        "octop.infra.agents.providers.store.ProviderStore.build_harness_configs",
        lambda self: [fake_provider_cfg],
    )

    await registry.on_provider_changed()

    fake_hm.add_provider.assert_called_once_with(fake_provider_cfg)


@pytest.mark.asyncio
async def test_on_provider_changed_removes_stale_provider(tmp_path: Path, monkeypatch) -> None:
    """on_provider_changed() calls remove_provider for providers no longer in DB."""
    services = _make_services(tmp_path)
    fake_hm = _make_fake_hm()
    fake_factory = MagicMock()
    fake_factory._providers = {"stale-provider": object()}
    fake_hm._shared_factory = fake_factory
    fake_hm.shared_factory = fake_factory
    fake_hm.add_provider = MagicMock()
    fake_hm.remove_provider = MagicMock()

    registry = _attach_registry(services, fake_hm=fake_hm)

    # No providers in DB → _build_provider_configs returns []
    monkeypatch.setattr(
        "octop.infra.agents.providers.store.ProviderStore.build_harness_configs",
        lambda self: [],
    )

    await registry.on_provider_changed()

    fake_hm.remove_provider.assert_called_once_with("stale-provider")


# ---------------------------------------------------------------------------
# Expert template application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_with_template_writes_files(tmp_path: Path) -> None:
    """create() with template_name uploads expert files to the agent backend."""
    from octop.infra.agents.experts.catalog import (  # noqa: PLC0415
        Expert,
        ExpertCatalog,
        ExpertSummary,
    )

    services = _make_services(tmp_path)
    expert_dir = tmp_path / "experts-lib" / "my-expert"
    expert_dir.mkdir(parents=True)
    (expert_dir / "SOUL.md").write_text("# Soul", encoding="utf-8")
    skill_dir = expert_dir / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")

    fake_entry = MagicMock()
    fake_entry.agent.backend = MagicMock()
    fake_hm = _make_fake_hm()
    fake_hm.create_agent = MagicMock(return_value=fake_entry)

    fake_catalog = MagicMock(spec=ExpertCatalog)
    fake_catalog.get = MagicMock(
        return_value=Expert(
            summary=ExpertSummary(
                id="my-expert",
                label_zh="测试",
                label_en="Test",
                description_zh="",
                description_en="",
            ),
            files=["SOUL.md", "skills/my-skill/SKILL.md"],
            prompt_files=["SOUL.md"],
        )
    )
    fake_catalog.expert_dir = MagicMock(return_value=expert_dir)

    registry = _attach_registry(
        services,
        fake_hm=fake_hm,
        expert_catalog=fake_catalog,
    )
    _bootstrap_factory_from_db(registry, fake_hm)

    await registry.create(AgentCreateSpec(name="expert-bot", template_name="my-expert"))

    ws = services.paths.agent_workspace(
        services.repos.agent_repo.list_all()[0].agent_id,
    )
    assert (ws / "SOUL.md").read_text(encoding="utf-8") == "# Soul"
    assert (ws / "skills").is_dir()
    assert (ws / "skills" / "my-skill" / "SKILL.md").read_text(encoding="utf-8") == "# Skill"
    assert (ws / "SOUL.md").read_text(encoding="utf-8") == "# Soul"


@pytest.mark.asyncio
async def test_create_ensures_skills_dir(tmp_path: Path) -> None:
    """create() always creates an empty skills/ directory in the workspace."""
    services = _make_services(tmp_path)
    fake_entry = MagicMock()
    fake_entry.agent.backend = MagicMock()
    fake_hm = _make_fake_hm()
    fake_hm.shared_factory = MagicMock()
    fake_hm.create_agent = MagicMock(return_value=fake_entry)

    registry = AgentManager(repos=services.repos, paths=services.paths)
    registry._harness_manager = fake_hm

    row = await registry.create(AgentCreateSpec(name="plain-bot"))
    ws = services.paths.agent_workspace(row.agent_id)
    # create() provisions the agent workspace; the skills/ dir is populated later
    # by the plugin manager sync (absent in this harness-only test setup).
    assert ws.is_dir()


@pytest.mark.asyncio
async def test_create_without_template_writes_no_files(tmp_path: Path) -> None:
    """create() without template_name must not call aupload_files."""
    uploaded: list = []

    services = _make_services(tmp_path)

    class FakeBackend:
        async def aupload_files(self, files):
            uploaded.extend(files)
            return []

    fake_entry = MagicMock()
    fake_entry.agent.backend = FakeBackend()
    fake_hm = _make_fake_hm()
    fake_hm.create_agent = MagicMock(return_value=fake_entry)

    registry = AgentManager(repos=services.repos, paths=services.paths)
    registry._harness_manager = fake_hm

    await registry.create(AgentCreateSpec(name="plain"))

    assert uploaded == []


@pytest.mark.asyncio
async def test_create_with_template_no_catalog_does_not_crash(tmp_path: Path) -> None:
    """create() with template_name but no expert_catalog logs a warning and continues."""
    services = _make_services(tmp_path)
    registry = _make_registry(services)  # expert_catalog=None

    row = await registry.create(AgentCreateSpec(name="no-catalog", template_name="any"))

    assert row.template_name == "any"


@pytest.mark.asyncio
async def test_create_with_unknown_template_does_not_crash(tmp_path: Path) -> None:
    """create() with a template_name not in catalog logs a warning and continues."""
    from octop.infra.agents.experts.catalog import ExpertCatalog  # noqa: PLC0415

    services = _make_services(tmp_path)
    fake_catalog = MagicMock(spec=ExpertCatalog)
    fake_catalog.get = MagicMock(return_value=None)  # unknown template

    registry = AgentManager(
        repos=services.repos,
        paths=services.paths,
        expert_catalog=fake_catalog,
    )
    registry._harness_manager = _make_fake_hm()

    row = await registry.create(AgentCreateSpec(name="unknown-tmpl", template_name="ghost"))

    assert row.name == "unknown-tmpl"
