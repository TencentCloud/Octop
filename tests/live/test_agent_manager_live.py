"""Live integration tests for :class:`octop.infra.agents.manager.AgentManager`.

Requires ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, and ``OPENAI_MODEL_NAME`` in
the repo-root ``.env``. Skipped by default — run with::

    uv run pytest tests/live/test_agent_manager_live.py -m live -v
"""

from __future__ import annotations

import pytest

from octop.infra.agents.manager import AgentCreateSpec
from octop.infra.agents.providers import KIND_TO_PROTOCOL
from octop.infra.errors import OctopError

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_boot_registers_provider_from_db(live_agent_manager, live_openai_config) -> None:
    providers = live_agent_manager.providers.build_harness_configs()
    assert len(providers) == 1
    p = providers[0]
    assert p.id == live_openai_config.provider_name
    assert p.base_url == live_openai_config.base_url
    assert KIND_TO_PROTOCOL["openai"] == "openai"


@pytest.mark.asyncio
async def test_create_agent_seeds_workspace_and_starts(
    live_agent_manager,
    live_openai_config,
    tmp_path,
) -> None:
    row = await live_agent_manager.create(
        AgentCreateSpec(
            name="live-bot",
            default_model=live_openai_config.default_model,
            system_prompt="You are a terse assistant.",
        ),
    )

    db_row = live_agent_manager.get_row(row.agent_id)
    assert db_row is not None
    assert db_row.last_state == "running"
    ws = live_agent_manager._paths.agent_workspace(row.agent_id)
    assert (ws / "AGENTS.md").is_file()

    harness = live_agent_manager.get_agent(row.agent_id)
    assert harness is not None
    entry = live_agent_manager._harness_manager.get_agent(row.agent_id)  # type: ignore[union-attr]
    assert entry.agent_id == row.agent_id
    cfg = live_agent_manager._build_harness_config(row)
    assert cfg.backend == {
        "type": "local_shell",
        "root_dir": "/",
        "virtual_mode": True,
    }
    assert str(cfg.workspace_dir) == str(ws)


@pytest.mark.asyncio
async def test_create_with_expert_template_writes_soul(
    live_agent_manager,
    live_openai_config,
) -> None:
    row = await live_agent_manager.create(
        AgentCreateSpec(
            name="general",
            default_model=live_openai_config.default_model,
            template_name="general-assistant",
        ),
    )

    ws = live_agent_manager._paths.agent_workspace(row.agent_id)
    assert (ws / "SOUL.md").is_file()
    soul = (ws / "SOUL.md").read_text(encoding="utf-8")
    assert len(soul) > 20


@pytest.mark.asyncio
async def test_update_reloads_running_agent(live_agent_manager, live_openai_config) -> None:
    row = await live_agent_manager.create(
        AgentCreateSpec(name="reload-me", default_model=live_openai_config.default_model),
    )
    updated = await live_agent_manager.update(
        row.agent_id,
        name="reload-me-v2",
        system_prompt="Updated prompt.",
    )
    assert updated.name == "reload-me-v2"
    assert live_agent_manager.get_row(row.agent_id).last_state == "running"
    assert live_agent_manager.get_agent(row.agent_id) is not None


@pytest.mark.asyncio
async def test_delete_removes_agent(live_agent_manager, live_openai_config) -> None:
    row = await live_agent_manager.create(
        AgentCreateSpec(name="delete-me", default_model=live_openai_config.default_model),
    )
    agent_id = row.agent_id
    await live_agent_manager.delete(agent_id)

    assert live_agent_manager.get_row(agent_id) is None
    with pytest.raises(OctopError):
        live_agent_manager.get_agent(agent_id)


@pytest.mark.asyncio
async def test_on_provider_changed_hot_reload(live_agent_manager, live_openai_config) -> None:
    await live_agent_manager.on_provider_changed()
    providers = live_agent_manager.providers.build_harness_configs()
    assert any(p.id == live_openai_config.provider_name for p in providers)


@pytest.mark.asyncio
async def test_agent_call_returns_reply(live_agent_manager, live_openai_config) -> None:
    row = await live_agent_manager.create(
        AgentCreateSpec(
            name="caller",
            default_model=live_openai_config.default_model,
            system_prompt="Reply with exactly one word: pong",
        ),
    )
    agent = live_agent_manager.get_agent(row.agent_id)
    result = await agent.call("ping")
    assert result is not None
    text = str(result).lower()
    assert len(text) > 0
