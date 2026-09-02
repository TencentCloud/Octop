"""Unit tests for :mod:`octop.infra.agents.manager` internals."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import OctopConfig
from octop.i18n.domains.agents import NO_MODELS_CONFIGURED, format_agent_start_error
from octop.infra.agents.experts.catalog import default_library_root
from octop.infra.agents.manager import AgentManager, _memory_extract_settings
from octop.infra.backend.resolver import default_agent_backend_spec
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

# Real HarnessAgentManager starts memory maintenance (GC/vacuum) on a daemon
# thread. Closing the agent while that tick holds the SQLite handle races on
# Windows (access violation under pytest-xdist). Unit tests here only need
# workspace/config behavior — keep memory off.
_MEMORY_OFF: dict[str, Any] = {"memory": {"memory_enabled": False}}


async def _collect_async(iterator: AsyncIterator[Any]) -> list[Any]:
    return [item async for item in iterator]


def _expected_default_backend(manager: AgentManager, agent_id: str) -> dict[str, Any]:
    from octop.infra.agents.execute_env import inject_agent_execute_env

    ws = manager._paths.ensure_agent_workspace(agent_id)
    return inject_agent_execute_env(
        default_agent_backend_spec(ws),
        paths=manager.paths,
        row=_row(agent_id=agent_id),
        workspace_dir=ws,
    )


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
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


def test_memory_extract_settings_supports_legacy_harness(caplog: pytest.LogCaptureFixture) -> None:
    settings = _memory_extract_settings(
        {
            "memory": {
                "memory_enabled": False,
                "extract_on_session_end": True,
                "extract_trigger_mode": "interval",
                "extract_idle_seconds": 60,
                "extract_interval_seconds": 600,
            }
        },
        supported_fields=frozenset(
            {
                "memory_enabled",
                "memory_extract_on_session_end",
                "memory_extract_idle_seconds",
            }
        ),
    )

    assert settings == {
        "memory_enabled": False,
        "memory_extract_on_session_end": True,
        "memory_extract_idle_seconds": 600.0,
    }
    assert "lacks interval memory extraction" in caplog.text


def test_memory_extract_settings_forwards_aux_model_to_both_tiers() -> None:
    settings = _memory_extract_settings(
        {"memory": {"aux_model": "hai/MiniMax-M2.7"}},
        is_ref_usable=lambda ref: ref == "hai/MiniMax-M2.7",
    )
    assert settings == {
        "memory_aux_light_model": "hai/MiniMax-M2.7",
        "memory_aux_heavy_model": "hai/MiniMax-M2.7",
    }


def test_memory_extract_settings_drops_stale_aux_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _memory_extract_settings(
        {"memory": {"aux_model": "gone/model"}},
        is_ref_usable=lambda _ref: False,
    )
    assert settings == {}
    assert "no longer usable" in caplog.text


def test_memory_extract_settings_skips_aux_model_on_legacy_harness() -> None:
    settings = _memory_extract_settings(
        {"memory": {"aux_model": "hai/MiniMax-M2.7"}},
        supported_fields=frozenset({"memory_enabled"}),
        is_ref_usable=lambda _ref: True,
    )
    assert settings == {}


def test_build_harness_config_accepts_memory_extract_settings(manager: AgentManager) -> None:
    row = _row(
        config_json=json.dumps(
            {
                "memory": {
                    "memory_enabled": False,
                    "extract_on_session_end": True,
                    "extract_trigger_mode": "interval",
                    "extract_idle_seconds": 60,
                    "extract_interval_seconds": 600,
                }
            }
        )
    )

    cfg = manager._build_harness_config(row)

    assert cfg.memory_enabled is False
    if hasattr(cfg, "memory_extract_trigger_mode"):
        assert cfg.memory_extract_trigger_mode == "interval"
        assert cfg.memory_extract_interval_seconds == 600.0
    else:
        assert cfg.memory_extract_idle_seconds == 600.0


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
        "search_knowledge",
    }


def test_build_harness_config_includes_search_knowledge_without_cron(
    manager: AgentManager,
) -> None:
    from octop.infra.knowledge.hint import KnowledgeSearchHintMiddleware

    cfg = manager._build_harness_config(_row(agent_id="AGT001"))
    assert cfg.tools is not None
    assert {t.name for t in cfg.tools} == {"search_knowledge"}
    assert any(isinstance(item, KnowledgeSearchHintMiddleware) for item in (cfg.middleware or []))


def test_build_harness_config_defaults_local_shell_backend(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(_row(agent_id="AGT001"))
    assert cfg.backend == _expected_default_backend(manager, "AGT001")
    assert cfg.workspace_dir.name == "AGT001"
    assert cfg.workspace_dir.parent.name == "agents"
    assert cfg.bootstrap_enabled is True
    # Kept for harness FilesystemGuardMiddleware (not passed to deepagents).
    assert cfg.permissions is not None
    assert cfg.log_dir == str(manager.paths.logs_dir)


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


def test_is_bootstrapped_returns_false_when_agent_not_running(manager: AgentManager) -> None:
    assert manager.is_bootstrapped("NOPE") is False


def test_is_bootstrapped_assumes_true_when_backend_check_fails(manager: AgentManager) -> None:
    agent = MagicMock()
    agent.is_bootstrapped.side_effect = OSError("TLS CA bundle missing")
    harness_manager = MagicMock()
    harness_manager.get_agent.return_value = MagicMock(agent=agent)
    manager._harness_manager = harness_manager

    assert manager.is_bootstrapped("AGT_COS") is True


@pytest.mark.asyncio
async def test_delete_thread_checkpoint_returns_false_when_agent_not_running(
    manager: AgentManager,
) -> None:
    # Fresh fixture has no _harness_manager wired up — get_agent raises
    # OctopError, which must be swallowed (checkpoint cleanup is best-effort).
    result = await manager.delete_thread_checkpoint("NOPE", "thr_1")
    assert result is False


@pytest.mark.asyncio
async def test_delete_thread_checkpoint_delegates_to_harness_adelete_thread(
    manager: AgentManager,
) -> None:
    agent = MagicMock()
    agent.adelete_thread = AsyncMock(return_value=True)
    harness_manager = MagicMock()
    harness_manager.get_agent.return_value = MagicMock(agent=agent)
    manager._harness_manager = harness_manager

    result = await manager.delete_thread_checkpoint("AGT1", "thr_1")

    assert result is True
    agent.adelete_thread.assert_awaited_once_with("thr_1")


@pytest.mark.asyncio
async def test_delete_thread_checkpoint_returns_false_when_harness_lacks_adelete_thread(
    manager: AgentManager,
) -> None:
    agent = MagicMock(spec=[])  # no adelete_thread attribute at all
    harness_manager = MagicMock()
    harness_manager.get_agent.return_value = MagicMock(agent=agent)
    manager._harness_manager = harness_manager

    result = await manager.delete_thread_checkpoint("AGT1", "thr_1")

    assert result is False


@pytest.mark.asyncio
async def test_delete_thread_checkpoint_propagates_unexpected_errors(
    manager: AgentManager,
) -> None:
    """A live agent whose checkpointer delete genuinely fails must not report success."""
    agent = MagicMock()
    agent.adelete_thread = AsyncMock(side_effect=RuntimeError("db unavailable"))
    harness_manager = MagicMock()
    harness_manager.get_agent.return_value = MagicMock(agent=agent)
    manager._harness_manager = harness_manager

    with pytest.raises(RuntimeError, match="db unavailable"):
        await manager.delete_thread_checkpoint("AGT1", "thr_1")


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
async def test_history_backfill_refuses_while_agent_stream_is_active(
    manager: AgentManager,
) -> None:
    agent_id = "AGT_BUSY"
    started = asyncio.Event()
    release = asyncio.Event()
    harness_manager = MagicMock()

    async def fake_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[dict[str, str]]:
        started.set()
        await release.wait()
        yield {"type": "done"}

    harness_manager.stream = fake_stream
    manager._harness_manager = harness_manager

    task = asyncio.create_task(_collect_async(manager.stream(agent_id, {"thread_id": "thr-busy"})))
    await started.wait()

    assert manager.is_agent_active(agent_id) is True
    assert manager.try_begin_history_backfill(agent_id) is False

    release.set()
    await task
    assert manager.is_agent_active(agent_id) is False


@pytest.mark.asyncio
async def test_waiting_agent_stream_prevents_next_history_backfill(
    manager: AgentManager,
) -> None:
    agent_id = "AGT_PRIORITY"
    stream_started = asyncio.Event()
    stream_release = asyncio.Event()
    harness_manager = MagicMock()

    async def fake_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[dict[str, str]]:
        stream_started.set()
        await stream_release.wait()
        yield {"type": "done"}

    harness_manager.stream = fake_stream
    manager._harness_manager = harness_manager
    assert manager.try_begin_history_backfill(agent_id) is True

    task = asyncio.create_task(
        _collect_async(manager.stream(agent_id, {"thread_id": "thr-priority"}))
    )
    await asyncio.sleep(0)
    assert stream_started.is_set() is False
    assert manager.try_begin_history_backfill(agent_id) is False

    manager.end_history_backfill(agent_id)
    await stream_started.wait()
    assert manager.is_agent_active(agent_id) is True
    assert manager.try_begin_history_backfill(agent_id) is False

    stream_release.set()
    await task
    assert manager.try_begin_history_backfill(agent_id) is True
    manager.end_history_backfill(agent_id)


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


@pytest.mark.asyncio
async def test_delete_removes_workspace_directory(manager: AgentManager) -> None:
    """Deleting an agent must clean up its workspace directory on disk."""
    agent_id = "AGT_DELETE_WS"
    manager._repos.agent_repo.create(agent_id=agent_id, user_id=None, name="delete-ws")

    workspace_dir = manager._paths.ensure_agent_workspace(agent_id)
    assert workspace_dir.is_dir()
    (workspace_dir / "MEMORY.md").write_text("old memory", encoding="utf-8")

    harness_manager = MagicMock()
    harness_manager.aremove_agent = AsyncMock()
    manager._harness_manager = harness_manager

    await manager.delete(agent_id)

    harness_manager.aremove_agent.assert_awaited_once_with(agent_id)
    assert manager.get_row(agent_id) is None
    assert not workspace_dir.exists()


@pytest.mark.asyncio
async def test_delete_removes_persisted_workspace_dir(
    manager: AgentManager, tmp_path: Path
) -> None:
    agent_id = "AGT_DELETE_CUSTOM"
    custom = tmp_path / "custom-ws"
    custom.mkdir()
    (custom / "SOUL.md").write_text("keep", encoding="utf-8")
    manager._repos.agent_repo.create(
        agent_id=agent_id,
        user_id=None,
        name="delete-custom",
        config_json=json.dumps({"workspace_dir": str(custom)}),
    )
    harness_manager = MagicMock()
    harness_manager.aremove_agent = AsyncMock()
    manager._harness_manager = harness_manager

    await manager.delete(agent_id)

    assert manager.get_row(agent_id) is None
    assert not custom.exists()


@pytest.mark.asyncio
async def test_delete_still_removes_db_row_when_workspace_rmtree_fails(
    manager: AgentManager, monkeypatch: Any
) -> None:
    """A failed workspace rmtree must not abort agent deletion (mirrors user removal)."""
    import shutil

    agent_id = "AGT_DELETE_ERR"
    manager._repos.agent_repo.create(agent_id=agent_id, user_id=None, name="delete-err")

    def _fail_rmtree(path: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(shutil, "rmtree", _fail_rmtree)

    harness_manager = MagicMock()
    harness_manager.aremove_agent = AsyncMock()
    manager._harness_manager = harness_manager

    await manager.delete(agent_id)

    assert manager.get_row(agent_id) is None


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


def test_backend_spec_for_row_neutralizes_host_root_on_windows(
    manager: AgentManager, monkeypatch: Any
) -> None:
    # The dashboard persists local backends with root_dir "/" (host-root sentinel).
    # On Windows that resolves to the current-drive root, breaking cross-drive reads
    # of the workspace; the resolver must rewrite root_dir to the workspace path.
    monkeypatch.setattr(os, "name", "nt")
    row = _row(
        config_json=json.dumps(
            {"backend": {"type": "local_shell", "root_dir": "/", "virtual_mode": True}}
        )
    )
    ws = manager.resolve_workspace_dir(row.agent_id)
    assert manager._backend_spec_for_row(row) == {
        "type": "local_shell",
        "root_dir": str(ws.resolve()),
        "virtual_mode": True,
    }


def test_build_harness_config_keeps_fs_permissions_for_local_shell_guard(
    manager: AgentManager,
) -> None:
    """local_shell keeps permissions on config; harness mounts FilesystemGuard.

    Octop must not re-mount the guard (or ModelSettings) via cfg.middleware.
    """
    from harness_agent.middleware.filesystem_guard import FilesystemGuardMiddleware
    from harness_agent.middleware.model_settings import ModelSettingsMiddleware

    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"backend": {"type": "local_shell", "virtual_mode": True}})),
    )
    backend = cfg.backend
    assert isinstance(backend, dict)
    assert backend.get("type") == "local_shell"
    assert backend.get("virtual_mode") is True
    assert cfg.permissions is not None
    middleware = cfg.middleware or []
    assert not any(isinstance(item, FilesystemGuardMiddleware) for item in middleware)
    assert not any(isinstance(item, ModelSettingsMiddleware) for item in middleware)
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"backend": {"type": "filesystem", "virtual_mode": True}})),
    )
    assert cfg.permissions is not None
    assert not any(isinstance(item, FilesystemGuardMiddleware) for item in (cfg.middleware or []))


def test_build_harness_config_without_default_model(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(_row())
    assert cfg.name == "agent_01AGENT"
    assert cfg.system_prompt is None
    assert cfg.backend == _expected_default_backend(manager, "01AGENT")


def test_build_harness_config_auto_expert_falls_back_to_first_model(
    manager: AgentManager,
) -> None:
    """AUTO expert still gets a concrete default_model so the memory aux LLM works."""
    _seed_test_provider(manager)
    cfg = manager._build_harness_config(_row(default_model=None))
    assert cfg.default_model == "test-openai/gpt-4o-mini"
    assert cfg.providers == []


def test_build_harness_config_uses_active_model_before_first(
    manager: AgentManager,
) -> None:
    """AUTO expert default_model follows the global active model when usable."""
    _seed_test_provider(manager)
    manager._repos.provider_repo.create(
        name="second-openai",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models_json=json.dumps(
            [{"id": "gpt-5", "name": "gpt-5", "enabled": True}],
        ),
    )
    manager._repos.settings_repo.set_active_model("second-openai", "gpt-5")
    cfg = manager._build_harness_config(_row(default_model=None))
    assert cfg.default_model == "second-openai/gpt-5"


def test_build_harness_config_active_model_ignored_when_unusable(
    manager: AgentManager,
) -> None:
    """Active model pointing at a disabled/removed provider falls back to first."""
    _seed_test_provider(manager)
    manager._repos.settings_repo.set_active_model("deleted-provider", "gone")
    cfg = manager._build_harness_config(_row(default_model=None))
    assert cfg.default_model == "test-openai/gpt-4o-mini"


def test_build_harness_config_explicit_default_wins_over_active(
    manager: AgentManager,
) -> None:
    """Pinned expert default takes precedence over the global active model."""
    _seed_test_provider(manager)
    manager._repos.settings_repo.set_active_model("test-openai", "gpt-4o-mini")
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"default_model": "test-openai/gpt-4o-mini"})),
    )
    assert cfg.default_model == "test-openai/gpt-4o-mini"


def test_build_harness_config_no_providers_leaves_default_model_unset(
    manager: AgentManager,
) -> None:
    cfg = manager._build_harness_config(_row(default_model=None))
    assert cfg.default_model is None


def test_build_harness_config_applies_usable_aux_model(manager: AgentManager) -> None:
    _seed_test_provider(manager)
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"memory": {"aux_model": "test-openai/gpt-4o-mini"}})),
    )
    assert cfg.memory_aux_light_model == "test-openai/gpt-4o-mini"
    assert cfg.memory_aux_heavy_model == "test-openai/gpt-4o-mini"


def test_build_harness_config_ignores_stale_aux_model(manager: AgentManager) -> None:
    _seed_test_provider(manager)
    cfg = manager._build_harness_config(
        _row(config_json=json.dumps({"memory": {"aux_model": "deleted-provider/gone"}})),
    )
    assert cfg.memory_aux_light_model is None
    assert cfg.memory_aux_heavy_model is None


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
    row = manager._repos.agent_repo.create(
        agent_id="REAL01",
        user_id=None,
        name="real",
        config_json=json.dumps(_MEMORY_OFF),
    )
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
    manager._repos.agent_repo.create(
        agent_id="STOP01",
        user_id=None,
        name="stop-me",
        config_json=json.dumps(_MEMORY_OFF),
    )
    row = manager.get_row("STOP01")
    assert row is not None
    await manager._start_agent(row)
    assert manager.get_row("STOP01") is not None
    assert manager.get_row("STOP01").last_state == "running"

    await manager.stop("STOP01")
    assert manager.get_row("STOP01") is not None
    assert manager.get_row("STOP01").last_state == "stopped"
    with pytest.raises(OctopError, match="not running") as stopped_exc:
        manager.get_agent("STOP01")
    assert stopped_exc.value.code is ErrorCode.AGENT_NOT_RUNNING

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
    manager._repos.agent_repo.create(
        agent_id="SEC01",
        user_id=None,
        name="sec",
        config_json=json.dumps(_MEMORY_OFF),
    )
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
    manager._repos.agent_repo.create(
        agent_id="SKIP01",
        user_id=None,
        name="skip",
        config_json=json.dumps(_MEMORY_OFF),
    )
    row = manager.get_row("SKIP01")
    assert row is not None
    await manager._start_agent(row)
    await manager.stop("SKIP01")

    await manager.reload("SKIP01")
    assert manager.get_row("SKIP01") is not None
    assert manager.get_row("SKIP01").last_state == "stopped"
    with pytest.raises(OctopError, match="not running") as skipped_exc:
        manager.get_agent("SKIP01")
    assert skipped_exc.value.code is ErrorCode.AGENT_NOT_RUNNING

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
    row = await manager.create(AgentCreateSpec(name="seeded", config=dict(_MEMORY_OFF)))
    agent = manager.get_agent(row.agent_id)
    assert agent.workspace.exists("BOOTSTRAP.md")
    assert agent.workspace.exists("AGENTS.md")
    cfg = manager.get_config(row.agent_id)
    assert cfg.get("workspace_dir") == str(
        manager.paths.ensure_agent_workspace(row.agent_id).resolve()
    )
    assert cfg.get("system_files_path") == ".octop"
    ws = manager.resolve_workspace_dir(row.agent_id)
    assert cfg.get("workspace_dir") == str(ws)
    assert (ws / "AGENTS.md").is_file()
    assert (ws / ".octop" / "_builtin_skills").is_dir() or agent.workspace.exists(
        "_builtin_skills/skill-manager/SKILL.md"
    )
    assert not (ws / "_builtin_skills").exists()
    manager._harness_manager.close()


@pytest.mark.asyncio
async def test_create_keeps_user_workspace_dir(
    manager: AgentManager,
    tmp_path: Path,
) -> None:
    """Explicit config.workspace_dir must not be replaced by the scoped default."""
    from harness_agent import HarnessAgentManager

    from octop.infra.agents.manager import AgentCreateSpec

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    custom = tmp_path / "custom-user-ws"
    try:
        row = await manager.create(
            AgentCreateSpec(
                name="user-ws",
                config={
                    **_MEMORY_OFF,
                    "backend": {
                        "type": "local_shell",
                        "root_dir": str(tmp_path),
                        "virtual_mode": True,
                    },
                    "workspace_dir": str(custom),
                },
            )
        )
        cfg = manager.get_config(row.agent_id)
        assert cfg["workspace_dir"] == str(custom)
        assert manager.resolve_workspace_dir(row.agent_id) == custom.resolve()
        assert custom.is_dir()
    finally:
        manager._harness_manager.close()


@pytest.mark.asyncio
async def test_create_persists_rootfs_workspace_under_scoped_root(
    manager: AgentManager,
    tmp_path: Path,
) -> None:
    """Non-host root_dir → config.workspace_dir is rootfs-absolute under that root."""
    from harness_agent import HarnessAgentManager

    from octop.infra.agents.manager import AgentCreateSpec

    _seed_test_provider(manager)
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
    )
    try:
        # manager fixture uses ``{tmp_path}/.octop`` as OCTOP_HOME, so scoping
        # root_dir to tmp_path places the default workspace inside the rootfs.
        row = await manager.create(
            AgentCreateSpec(
                name="scoped-ws",
                config={
                    **_MEMORY_OFF,
                    "backend": {
                        "type": "local_shell",
                        "root_dir": str(tmp_path),
                        "virtual_mode": True,
                    },
                },
            )
        )
        cfg = manager.get_config(row.agent_id)
        assert cfg["workspace_dir"] == f"/.octop/workspaces/{row.agent_id}"
        host = manager.resolve_workspace_dir(row.agent_id)
        assert host == (tmp_path / ".octop" / "workspaces" / row.agent_id).resolve()
        assert host.is_dir()
        assert (host / "AGENTS.md").is_file()
        harness_cfg = manager._build_harness_config(row)
        # POSIX hands harness the persisted agent-facing path — not the host join.
        # Windows cannot express it as absolute, so harness gets the host mapping.
        expected_harness_ws = (
            Path(f"/.octop/workspaces/{row.agent_id}") if os.name == "posix" else host
        )
        assert Path(harness_cfg.workspace_dir) == expected_harness_ws
        assert not (tmp_path / ".octop" / "agents" / row.agent_id).exists()
    finally:
        manager._harness_manager.close()


def test_resolve_workspace_dir_uses_persisted_path(manager: AgentManager, tmp_path: Path) -> None:
    custom = tmp_path / "custom-ws"
    custom.mkdir()
    manager._repos.agent_repo.create(
        agent_id="WSDIR1",
        user_id=None,
        name="ws",
        config_json=json.dumps({"workspace_dir": str(custom)}),
    )
    assert manager.resolve_workspace_dir("WSDIR1") == custom.resolve()


def test_resolve_workspace_dir_backfills_legacy_row(manager: AgentManager) -> None:
    manager._repos.agent_repo.create(
        agent_id="WSDIR2",
        user_id=None,
        name="legacy",
        config_json="{}",
    )
    resolved = manager.resolve_workspace_dir("WSDIR2")
    assert resolved == manager.paths.ensure_agent_workspace("WSDIR2").resolve()
    assert manager.get_config("WSDIR2")["workspace_dir"] == str(resolved)


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
        AgentCreateSpec(
            name="tpl-bot",
            template_name="general-assistant",
            config=dict(_MEMORY_OFF),
        ),
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
    manifest = json.loads((ws / ".octop" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "demo"
    assert manifest["welcome_message"]["zh"] == "欢迎"


@pytest.mark.asyncio
async def test_persist_skills_disabled_does_not_schedule_reload(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """skills_disabled is hot-synced; must not tear down the running agent."""
    from octop.infra.agents.manager import AgentCreateSpec

    fake_agent = MagicMock()
    fake_hm = MagicMock()
    fake_hm.get_agent.return_value = MagicMock(agent=fake_agent)
    fake_hm.acreate_agent = AsyncMock(return_value=MagicMock(agent=fake_agent))
    fake_hm.shared_factory = object()
    manager._harness_manager = fake_hm

    row = await manager.create(AgentCreateSpec(name="skills-hot"))
    scheduled: list[str] = []
    monkeypatch.setattr(manager, "_schedule_reload", lambda aid: scheduled.append(aid))

    await manager.persist_skills_disabled(row.agent_id, {"pdf", "docx"})

    cfg = manager.get_config(row.agent_id)
    assert cfg.get("skills_disabled") == ["docx", "pdf"]
    fake_agent.set_skills_disabled.assert_called_once_with({"pdf", "docx"})
    assert scheduled == []


@pytest.mark.asyncio
async def test_persist_tools_disabled_strips_critical_and_hot_syncs(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tools_disabled is hot-synced; critical names are dropped."""
    from octop.infra.agents.manager import AgentCreateSpec

    fake_agent = MagicMock()
    fake_hm = MagicMock()
    fake_hm.get_agent.return_value = MagicMock(agent=fake_agent)
    fake_hm.acreate_agent = AsyncMock(return_value=MagicMock(agent=fake_agent))
    fake_hm.shared_factory = object()
    manager._harness_manager = fake_hm

    row = await manager.create(AgentCreateSpec(name="tools-hot"))
    scheduled: list[str] = []
    monkeypatch.setattr(manager, "_schedule_reload", lambda aid: scheduled.append(aid))

    await manager.persist_tools_disabled(row.agent_id, {"web_fetch", "read_file", "execute"})

    cfg = manager.get_config(row.agent_id)
    assert cfg.get("tools_disabled") == ["execute", "web_fetch"]
    fake_agent.set_tools_disabled.assert_called_once_with({"execute", "web_fetch"})
    assert scheduled == []


@pytest.mark.asyncio
async def test_update_config_json_still_schedules_reload(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.agents.manager import AgentCreateSpec

    fake_agent = MagicMock()
    fake_hm = MagicMock()
    fake_hm.get_agent.return_value = MagicMock(agent=fake_agent)
    fake_hm.acreate_agent = AsyncMock(return_value=MagicMock(agent=fake_agent))
    fake_hm.shared_factory = object()
    manager._harness_manager = fake_hm

    row = await manager.create(AgentCreateSpec(name="cfg-reload"))
    scheduled: list[str] = []
    monkeypatch.setattr(manager, "_schedule_reload", lambda aid: scheduled.append(aid))

    await manager.update_config_json(row.agent_id, json.dumps({"foo": 1}))
    assert scheduled == [row.agent_id]


@pytest.mark.asyncio
async def test_update_config_json_cannot_change_system_files_path(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``system_files_path`` is an internal layout knob; user updates must not mutate it."""
    from octop.infra.agents.manager import AgentCreateSpec

    # Avoid starting harness runtime in this unit-test context.
    row = await manager.create(AgentCreateSpec(name="sysfiles-fixed"), defer_bootstrap=True)
    monkeypatch.setattr(manager, "_schedule_reload", lambda _aid: None)

    assert manager.get_config(row.agent_id).get("system_files_path") == ".octop"

    await manager.update_config_json(
        row.agent_id,
        json.dumps({"system_files_path": "", "foo": 1}),
    )

    assert manager.get_config(row.agent_id).get("system_files_path") == ".octop"


@pytest.mark.asyncio
async def test_reload_agent_does_not_block_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Harness create/remove must run off the event loop (MCP init blocks the loop)."""
    import asyncio
    import time
    from unittest.mock import MagicMock

    from octop.infra.agents.manager import AgentCreateSpec, AgentManager

    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    registry = AgentManager(repos=services.repos, paths=services.paths)

    fake_hm = MagicMock()
    fake_entry = MagicMock()
    fake_entry.agent = MagicMock()
    fake_hm.shared_factory = object()
    fake_hm.acreate_agent = AsyncMock(return_value=fake_entry)

    rebuild_started = asyncio.Event()
    rebuild_finished = asyncio.Event()
    post_start_finished = asyncio.Event()

    async def slow_rebuild(*_args: object, **_kwargs: object) -> MagicMock:
        rebuild_started.set()
        await asyncio.to_thread(time.sleep, 0.15)
        rebuild_finished.set()
        return fake_entry

    async def fake_post_start(*_args: object, **_kwargs: object) -> None:
        post_start_finished.set()

    fake_hm.arebuild_agent = AsyncMock(side_effect=slow_rebuild)
    fake_hm.aremove_agent = AsyncMock()
    registry._harness_manager = fake_hm
    monkeypatch.setattr(registry, "_post_start_agent", fake_post_start)

    row = await registry.create(AgentCreateSpec(name="block-test"))
    post_start_finished.clear()

    tick = asyncio.Event()

    async def ticker() -> None:
        await rebuild_started.wait()
        tick.set()

    ticker_task = asyncio.create_task(ticker())
    await registry.update(row.agent_id, name="block-test-v2")
    await asyncio.wait_for(tick.wait(), timeout=1.0)
    assert not rebuild_finished.is_set()
    await asyncio.wait_for(post_start_finished.wait(), timeout=1.0)
    await ticker_task


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


def test_prepare_stream_request_maps_max_iters_to_recursion_limit(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_id = "01AGENT"
    monkeypatch.setattr(
        manager,
        "get_config",
        lambda _agent_id: {"max_iters": 17},
    )
    req = manager._prepare_stream_request(agent_id, {"messages": "hi"})
    assert req["recursion_limit"] == 17


def test_prepare_stream_request_maps_model_settings_and_max_input_tokens(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_id = "01AGENT"
    monkeypatch.setattr(
        manager,
        "get_config",
        lambda _agent_id: {
            "temperature": 0.2,
            "top_p": 0.95,
            "max_tokens": 2048,
            "max_input_length": 32000,
        },
    )
    req = manager._prepare_stream_request(agent_id, {"messages": "hi"})
    assert req["configurable"]["model_settings"] == {
        "temperature": 0.2,
        "top_p": 0.95,
        "max_tokens": 2048,
    }
    assert req["configurable"]["max_input_tokens"] == 32000
