"""Unit tests for :mod:`octop.infra.agents.manager` internals."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import OctopConfig
from octop.i18n.domains.agents import NO_MODELS_CONFIGURED, format_agent_start_error
from octop.infra.agents.experts.catalog import default_library_root
from octop.infra.agents.manager import AgentManager
from octop.infra.backend.resolver import default_agent_backend_spec
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.errors import OctopError
from octop.infra.utils.paths import PathLayout


def _expected_default_backend(manager: AgentManager, agent_id: str) -> dict[str, str | bool]:
    ws = manager._paths.ensure_agent_workspace(agent_id)
    return default_agent_backend_spec(ws)


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = DBPool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return AgentManager(repos=services.repos, paths=services.paths)


def _seed_test_provider(manager: AgentManager) -> None:
    manager._repos.provider_repo.create(
        name="test-openai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [{"id": "gpt-4o-mini", "name": "gpt-4o-mini", "enabled": True}],
        ),
    )


def _row(
    *,
    agent_id: str = "01AGENT",
    config_json: str | None = None,
    default_model: str | None = None,
) -> AgentRow:
    return AgentRow(
        id=1,
        agent_id=agent_id,
        user_id=1,
        name="bot",
        description=None,
        persona_mbti=None,
        default_model=default_model,
        system_prompt=None,
        enabled=1,
        config_json=config_json,
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
    )


def test_format_agent_start_error_no_providers_message() -> None:
    exc = RuntimeError("HarnessAgent requires providers on the config, an injected model_factory (")
    assert format_agent_start_error(exc) == NO_MODELS_CONFIGURED


def test_format_agent_start_error_no_enabled_models_message() -> None:
    exc = RuntimeError("No enabled models found in providers")
    assert format_agent_start_error(exc) == NO_MODELS_CONFIGURED


def test_format_agent_start_error_unknown_passthrough() -> None:
    exc = RuntimeError("disk full")
    assert format_agent_start_error(exc) == "disk full"


def test_format_agent_start_error_unwraps_exception_group() -> None:
    exc = BaseExceptionGroup(
        "unhandled errors in a TaskGroup (1 sub-exception)",
        [ValueError("storage backend 'cos' not found")],
    )
    assert format_agent_start_error(exc) == "storage backend 'cos' not found"


def test_build_harness_config_includes_cronjob_tools_when_cron_manager_set(
    manager: AgentManager,
    tmp_path: Path,
) -> None:
    from unittest.mock import MagicMock

    from octop.infra.cron.manager import CronManager

    gw = MagicMock()
    gw.thread_registry = MagicMock()
    cron_mgr = CronManager(gateway=gw, repos=manager._repos, timezone="UTC")
    cron_mgr._scheduler = MagicMock()
    manager.set_cron_manager(cron_mgr)

    cfg = manager._build_harness_config(_row(agent_id="AGT001"))
    assert cfg.tools is not None
    names = {t.name for t in cfg.tools}
    assert names == {
        "cronjob_list",
        "cronjob_get",
        "cronjob_create",
        "cronjob_update",
        "cronjob_delete",
        "cronjob_run_now",
    }


def test_build_harness_config_without_cron_manager_has_no_extra_tools(
    manager: AgentManager,
) -> None:
    cfg = manager._build_harness_config(_row(agent_id="AGT001"))
    assert cfg.tools is None


def test_build_harness_config_defaults_local_shell_backend(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(_row(agent_id="AGT001"))
    assert cfg.backend == _expected_default_backend(manager, "AGT001")
    assert cfg.workspace_dir.name == "AGT001"
    assert cfg.workspace_dir.parent.name == "agents"
    assert cfg.bootstrap_enabled is True
    assert cfg.permissions is None


def test_build_harness_config_enables_bootstrap_for_expert_template(manager: AgentManager) -> None:
    from dataclasses import replace

    cfg = manager._build_harness_config(
        replace(_row(agent_id="AGT001"), template_name="cvm-ai-doctor"),
    )
    assert cfg.bootstrap_enabled is True


def _fs_backend(ws: Path) -> dict[str, str]:
    return {"type": "filesystem", "root_dir": str(ws), "virtual_mode": False}


def test_build_harness_config_suppresses_system_prompt_while_bootstrap_pending(
    manager: AgentManager,
) -> None:
    from dataclasses import replace

    agent_id = "AGT_BOOT"
    ws = manager._paths.ensure_agent_workspace(agent_id)
    row = replace(
        _row(agent_id=agent_id),
        system_prompt="MBTI persona prompt",
        config_json=json.dumps({"backend": _fs_backend(ws)}),
    )
    cfg = manager._build_harness_config(row)
    assert cfg.system_prompt is None
    assert cfg.memory == ()


def test_build_harness_config_keeps_memory_after_bootstrap(
    manager: AgentManager,
) -> None:
    from dataclasses import replace

    agent_id = "AGT_MEM"
    ws = manager._paths.ensure_agent_workspace(agent_id)
    (ws / ".bootstrapped").write_text("", encoding="utf-8")
    row = replace(
        _row(agent_id=agent_id),
        system_prompt="MBTI persona prompt",
        config_json=json.dumps({"backend": _fs_backend(ws)}),
    )
    cfg = manager._build_harness_config(row)
    assert cfg.memory is None


def test_build_harness_config_keeps_system_prompt_after_bootstrap(
    manager: AgentManager,
) -> None:
    from dataclasses import replace

    agent_id = "AGT_DONE"
    ws = manager._paths.ensure_agent_workspace(agent_id)
    (ws / ".bootstrapped").write_text("", encoding="utf-8")
    row = replace(
        _row(agent_id=agent_id),
        system_prompt="MBTI persona prompt",
        config_json=json.dumps({"backend": _fs_backend(ws)}),
    )
    cfg = manager._build_harness_config(row)
    assert cfg.system_prompt == "MBTI persona prompt"


def test_bootstrap_complete_defers_graph_refresh(manager: AgentManager) -> None:
    agent_id = "AGT_BOOT"
    manager._repos.agent_repo.create(agent_id=agent_id, user_id=None, name="boot")
    manager._repos.agent_repo.update_config(agent_id, system_prompt="Persona from DB")

    agent = MagicMock()
    cfg = MagicMock()
    cfg.memory = ()
    cfg.system_prompt = None
    agent._config = cfg

    manager._mark_bootstrap_graph_refresh_pending(agent_id, agent)

    assert cfg.system_prompt == "Persona from DB"
    assert cfg.memory is None
    agent._init_graph.assert_not_called()
    assert agent_id in manager._bootstrap_graph_refresh_pending


def test_apply_pending_bootstrap_graph_refresh_recompiles_graph(manager: AgentManager) -> None:
    agent_id = "AGT_BOOT2"
    agent = MagicMock()
    harness_manager = MagicMock()
    harness_manager.get_agent.return_value = MagicMock(agent=agent)
    manager._harness_manager = harness_manager
    manager._bootstrap_graph_refresh_pending.add(agent_id)

    manager._apply_pending_bootstrap_graph_refresh(agent_id)

    agent._init_graph.assert_called_once()
    assert agent_id not in manager._bootstrap_graph_refresh_pending


@pytest.mark.asyncio
async def test_stream_applies_bootstrap_refresh_after_turn(manager: AgentManager) -> None:
    agent_id = "AGT_STREAM"
    agent = MagicMock()
    harness_manager = MagicMock()

    async def fake_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[dict[str, str]]:
        yield {"type": "token", "content": "hi"}

    harness_manager.stream = fake_stream
    harness_manager.get_agent.return_value = MagicMock(agent=agent)
    manager._harness_manager = harness_manager
    manager._bootstrap_graph_refresh_pending.add(agent_id)

    chunks = [chunk async for chunk in manager.stream(agent_id, {"thread_id": "thr1"})]

    assert chunks == [{"type": "token", "content": "hi"}]
    agent._init_graph.assert_called_once()
    assert agent_id not in manager._bootstrap_graph_refresh_pending


@pytest.mark.asyncio
async def test_reload_agent_clears_bootstrap_refresh_pending(manager: AgentManager) -> None:
    agent_id = "AGT_RELOAD"
    manager._repos.agent_repo.create(agent_id=agent_id, user_id=None, name="reload")
    manager._repos.agent_repo.set_state(agent_id, "stopped")
    manager._bootstrap_graph_refresh_pending.add(agent_id)

    harness_manager = MagicMock()
    harness_manager.aremove_agent = AsyncMock()
    manager._harness_manager = harness_manager

    await manager._reload_agent(agent_id)

    assert agent_id not in manager._bootstrap_graph_refresh_pending
    harness_manager.aremove_agent.assert_awaited_once_with(agent_id)


def test_bootstrap_pending_detects_unfinished_onboarding(tmp_path: Path) -> None:
    from harness_agent.backends import resolve_backend
    from harness_agent.backends.workspace import BackendWorkspace
    from harness_agent.middleware.bootstrap import bootstrap_marker_exists

    backend = resolve_backend(
        {"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        workspace_dir=tmp_path,
    )
    ws = BackendWorkspace(backend, tmp_path)
    assert not bootstrap_marker_exists(ws)
    (tmp_path / ".bootstrapped").write_text("", encoding="utf-8")
    assert bootstrap_marker_exists(ws)


def test_build_harness_config_respects_config_json_backend(manager: AgentManager) -> None:
    custom = {"type": "filesystem", "root_dir": "/srv/data"}
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"backend": custom})),
    )
    assert cfg.backend == custom


def test_build_harness_config_omits_fs_permissions_for_local_shell(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"backend": {"type": "local_shell", "virtual_mode": True}})),
    )
    assert cfg.backend == {"type": "local_shell", "virtual_mode": True}
    assert cfg.permissions is None
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"backend": {"type": "filesystem", "virtual_mode": True}})),
    )
    assert cfg.permissions is not None


def test_build_harness_config_without_default_model(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(_row())
    assert cfg.name == "agent_01AGENT"
    assert cfg.system_prompt is None
    assert cfg.backend == _expected_default_backend(manager, "01AGENT")


def test_build_harness_config_auto_expert_omits_providers_and_default(
    manager: AgentManager,
) -> None:
    _seed_test_provider(manager)
    cfg = manager._build_harness_config(_row(default_model=None))
    assert cfg.default_model is None
    assert cfg.providers == []


@pytest.mark.skip(
    reason="HarnessAgentConfig monkeypatch incompatible with SecurityPolicy.apply_to_config"
)
def test_build_harness_config_passes_default_model_without_embedded_providers(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """default_model is forwarded; providers stay on HarnessAgentManager, not per-agent config."""
    from octop.infra.agents import manager as mgr_mod

    captured: list[dict] = []

    class _FakeCfg:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(mgr_mod, "HarnessAgentConfig", _FakeCfg)
    manager._build_harness_config(_row(default_model="openai-live/MiniMax-M2.7"))
    assert captured[0]["default_model"] == "openai-live/MiniMax-M2.7"
    assert "providers" not in captured[0]


def test_build_harness_config_tolerates_bad_config_json(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(_row(config_json="{not-json"))
    assert cfg.backend == _expected_default_backend(manager, "01AGENT")


@pytest.mark.asyncio
async def test_start_agent_real_harness_seeds_agents_md(manager: AgentManager) -> None:
    """Uses real HarnessAgentManager — no LLM call, only workspace init."""
    from harness_agent import HarnessAgentManager

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    row = manager._repos.agent_repo.create(agent_id="REAL01", user_id=None, name="real")
    row = manager._repos.agent_repo.get("REAL01")
    assert row is not None

    from harness_agent import HarnessAgent

    agent = await manager._start_agent(row)
    assert isinstance(agent, HarnessAgent)
    assert agent.workspace.exists("AGENTS.md")

    db_row = manager.get_row("REAL01")
    assert db_row is not None
    assert db_row.last_state == "running"

    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_stop_and_start_round_trip(manager: AgentManager) -> None:
    from harness_agent import HarnessAgentManager

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    manager._repos.agent_repo.create(agent_id="STOP01", user_id=None, name="stop-me")
    row = manager.get_row("STOP01")
    assert row is not None
    await manager._start_agent(row)
    assert manager.get_row("STOP01") is not None
    assert manager.get_row("STOP01").last_state == "running"

    await manager.stop("STOP01")
    assert manager.get_row("STOP01") is not None
    assert manager.get_row("STOP01").last_state == "stopped"
    with pytest.raises(OctopError, match="not running"):
        manager.get_agent("STOP01")

    await manager.start("STOP01")
    assert manager.get_row("STOP01") is not None
    assert manager.get_row("STOP01").last_state == "running"
    manager.get_agent("STOP01")

    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_save_security_rebuilds_running_harness_agent(manager: AgentManager) -> None:
    from harness_agent import HarnessAgentManager

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    manager._repos.agent_repo.create(agent_id="SEC01", user_id=None, name="sec")
    row = manager.get_row("SEC01")
    assert row is not None
    await manager._start_agent(row)

    policy = manager.save_security(
        {"hitl": {"enabled": False}, "tool_guard": {"enabled": True, "mode": "warn"}}
    )
    assert policy.hitl.enabled is False
    assert policy.tool_guard.mode == "warn"
    manager.get_agent("SEC01")

    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_reload_skips_stopped_agent(manager: AgentManager) -> None:
    from harness_agent import HarnessAgentManager

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    manager._repos.agent_repo.create(agent_id="SKIP01", user_id=None, name="skip")
    row = manager.get_row("SKIP01")
    assert row is not None
    await manager._start_agent(row)
    await manager.stop("SKIP01")

    await manager.reload("SKIP01")
    assert manager.get_row("SKIP01") is not None
    assert manager.get_row("SKIP01").last_state == "stopped"
    with pytest.raises(OctopError, match="not running"):
        manager.get_agent("SKIP01")

    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_create_seeds_bootstrap_files(manager: AgentManager) -> None:
    """create() must seed harness workspace (BOOTSTRAP.md, AGENTS.md, …) before start."""
    from harness_agent import HarnessAgentManager

    from octop.infra.agents.manager import AgentCreateSpec

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    row = await manager.create(AgentCreateSpec(name="seeded"))
    agent = manager.get_agent(row.agent_id)
    assert agent.workspace.exists("BOOTSTRAP.md")
    assert agent.workspace.exists("AGENTS.md")
    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_templated_agent_keeps_expert_soul_on_reload(manager: AgentManager) -> None:
    """Reload must not overwrite expert template SOUL.md with persona defaults."""
    from harness_agent import HarnessAgentManager

    from octop.infra.agents.experts.catalog import ExpertCatalog
    from octop.infra.agents.manager import AgentCreateSpec

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    ga = catalog.get("general-assistant")
    assert ga is not None

    manager._expert_catalog = catalog
    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    row = await manager.create(
        AgentCreateSpec(name="tpl-bot", template_name="general-assistant"),
    )
    agent = manager.get_agent(row.agent_id)
    expected_soul = (default_library_root() / "general-assistant" / "SOUL.md").read_text(
        encoding="utf-8"
    )
    soul_text = agent.workspace.read_text("SOUL.md") or ""
    assert expected_soul.strip() in soul_text.strip()

    await manager._reload_agent(row.agent_id)
    soul_after = manager.get_agent(row.agent_id).workspace.read_text("SOUL.md") or ""
    assert "Persona: Default" not in soul_after
    assert expected_soul.strip() in soul_after
    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_seed_expert_template_writes_workspace_files(
    manager: AgentManager, tmp_path: Path
) -> None:
    from octop.infra.agents.experts.catalog import Expert, ExpertCatalog, ExpertSummary

    expert_dir = tmp_path / "demo"
    expert_dir.mkdir()
    (expert_dir / "SOUL.md").write_text("# Soul", encoding="utf-8")
    (expert_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "label": {"zh": "演示", "en": "Demo"},
                "description": {"zh": "", "en": ""},
                "welcome_message": {"zh": "欢迎", "en": "Welcome"},
                "quick_prompts": [],
            }
        ),
        encoding="utf-8",
    )

    catalog = MagicMock(spec=ExpertCatalog)
    catalog.get = MagicMock(
        return_value=Expert(
            summary=ExpertSummary(
                id="demo",
                label_zh="演示",
                label_en="Demo",
                description_zh="",
                description_en="",
            ),
            files=["SOUL.md"],
            prompt_files=["SOUL.md"],
        ),
    )
    catalog.expert_dir = MagicMock(return_value=expert_dir)
    manager._expert_catalog = catalog

    manager._repos.agent_repo.create(agent_id="AGT1", user_id=None, name="demo-bot")
    agent_row = manager._repos.agent_repo.get("AGT1")
    assert agent_row is not None
    await manager._seed_expert_template(agent_row, "demo")

    ws = manager._paths.ensure_agent_workspace("AGT1")
    assert (ws / "SOUL.md").read_text(encoding="utf-8") == "# Soul"
    manifest = json.loads((ws / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "demo"
    assert manifest["welcome_message"]["zh"] == "欢迎"


@pytest.mark.asyncio
async def test_reload_agent_does_not_block_event_loop(tmp_path: Path) -> None:
    """Harness create/remove must run off the event loop (MCP init blocks the loop)."""
    import asyncio
    import time
    from unittest.mock import MagicMock

    from octop.infra.agents.manager import AgentCreateSpec, AgentManager

    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = DBPool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    registry = AgentManager(repos=services.repos, paths=services.paths)

    fake_hm = MagicMock()
    fake_entry = MagicMock()
    fake_entry.agent = MagicMock()

    async def slow_rebuild(*_args: object, **_kwargs: object) -> MagicMock:
        await asyncio.to_thread(time.sleep, 0.15)
        return fake_entry

    fake_hm.arebuild_agent = AsyncMock(side_effect=slow_rebuild)
    fake_hm.aremove_agent = AsyncMock()
    registry._harness_manager = fake_hm

    row = await registry.create(AgentCreateSpec(name="block-test"))

    tick = asyncio.Event()

    async def ticker() -> None:
        await asyncio.sleep(0.05)
        tick.set()

    asyncio.create_task(ticker())
    await registry.update(row.agent_id, name="block-test-v2")
    await asyncio.wait_for(tick.wait(), timeout=0.2)
    # Background reload may still be running; wait for it to finish.
    await asyncio.sleep(0.3)


def test_build_mcp_configs_registers_gateway_without_transport(manager: AgentManager) -> None:
    """Gateway connectors register a name-only placeholder; tools inject in-process."""
    from octop.infra.connectors.builder import mcp_server_name
    from octop.infra.connectors.crypto import encrypt_credentials
    from octop.infra.utils.ulid import new_ulid

    with manager._repos.db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("gw", "h", "user"),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = 'gw'").fetchone()["id"]
    agent_id = manager._repos.agent_repo.create(agent_id="GWAGENT", user_id=uid, name="gw-agent")
    iid = new_ulid()
    mcp_name = mcp_server_name("tencent-ima", iid)
    manager._repos.connector_repo.create(
        instance_id=iid,
        user_id=uid,
        kind="tencent-ima",
        display_name="IMA",
        mcp_server_name=mcp_name,
    )
    creds = encrypt_credentials(
        manager._repos.secret_repo,
        {"api_key": "k", "client_id": "c", "internal_token": "tok"},
    )
    manager._repos.connector_repo.upsert_credentials(instance_id=iid, blob=creds, expires_at=None)

    configs = manager._build_harness_config(manager.get_row(agent_id) or _row()).mcp_server_configs
    assert mcp_name in configs
    assert configs[mcp_name] == {}


def test_build_mcp_configs_shared_agent_uses_connector_user_override(manager: AgentManager) -> None:
    """Shared agents (user_id=NULL) need connector_user_override to resolve connectors."""
    from octop.infra.connectors.builder import mcp_server_name
    from octop.infra.connectors.crypto import encrypt_credentials
    from octop.infra.utils.ulid import new_ulid

    with manager._repos.db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("shared-gw", "h", "user"),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = 'shared-gw'").fetchone()["id"]
    agent_id = manager._repos.agent_repo.create(agent_id="SHAREDAG", user_id=None, name="shared")
    assert (
        manager._build_harness_config(manager.get_row(agent_id) or _row()).mcp_server_configs == {}
    )

    iid = new_ulid()
    mcp_name = mcp_server_name("tencent-ima", iid)
    manager._repos.connector_repo.create(
        instance_id=iid,
        user_id=uid,
        kind="tencent-ima",
        display_name="IMA",
        mcp_server_name=mcp_name,
    )
    creds = encrypt_credentials(
        manager._repos.secret_repo,
        {"api_key": "k", "client_id": "c", "internal_token": "tok"},
    )
    manager._repos.connector_repo.upsert_credentials(instance_id=iid, blob=creds, expires_at=None)

    manager._connector_user_override[agent_id] = uid
    try:
        configs = manager._build_harness_config(
            manager.get_row(agent_id) or _row()
        ).mcp_server_configs
    finally:
        manager._connector_user_override.pop(agent_id, None)
    assert mcp_name in configs


def test_mcp_tool_filter_uses_server_prefix(manager: AgentManager) -> None:
    """Harness exposes MCP tools as {mcp_server_name}_{tool}; chat filters by prefix."""
    from harness_agent.mcp import filter_tools_for_mcp_servers, mcp_tool_names

    mcp_name = "tencent-ima__01INST"
    tools = [{"name": f"{mcp_name}_list_notes"}, {"name": f"{mcp_name}_search_notes"}]
    tool_set = mcp_tool_names(tools)
    filtered = filter_tools_for_mcp_servers(
        tools,
        mcp_tool_names=tool_set,
        server_names=frozenset({mcp_name}),
        active_servers=[mcp_name],
    )
    assert len(filtered) == 2
