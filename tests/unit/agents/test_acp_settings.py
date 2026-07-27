"""tests/unit/test_acp_settings.py — user-scoped global ACP runner settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.agents.acp_settings import ACPSettingsStore
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo


@pytest.fixture
def acp_store(tmp_path: Path) -> tuple[ACPSettingsStore, AgentRepo, int]:
    db = SqlitePool(tmp_path / "test.db")
    run_migrations(db)
    settings = SettingsRepo(db)
    agents = AgentRepo(db)
    user_id = UserRepo(db).create(username="u", password_hash="h", role="user")
    store = ACPSettingsStore(settings_repo=settings, agents_repo=agents)
    return store, agents, user_id


def test_load_defaults_include_codebuddy(
    acp_store: tuple[ACPSettingsStore, AgentRepo, int],
) -> None:
    store, _, user_id = acp_store
    runners = store.load_runners(user_id=user_id)
    assert "opencode" in runners
    assert "codebuddy" in runners
    assert "qwen_code" not in runners


def test_save_and_load_round_trip(acp_store: tuple[ACPSettingsStore, AgentRepo, int]) -> None:
    store, _, user_id = acp_store
    saved = store.save_runners(
        user_id,
        {
            "opencode": {
                "enabled": True,
                "command": "opencode",
                "args": ["acp"],
                "env": {},
                "trusted": True,
                "tool_parse_mode": "update_detail",
                "stdio_buffer_limit_bytes": 52428800,
            },
        },
    )
    assert saved["opencode"]["enabled"] is True
    reloaded = store.load_runners(user_id)
    assert reloaded["opencode"]["enabled"] is True


def test_migrate_legacy_per_agent_runners(
    acp_store: tuple[ACPSettingsStore, AgentRepo, int],
) -> None:
    store, agents, user_id = acp_store
    legacy = {
        "acp": {
            "tool_enabled": True,
            "runners": {
                "opencode": {
                    "enabled": True,
                    "command": "opencode",
                    "args": ["acp"],
                    "env": {},
                    "trusted": True,
                    "tool_parse_mode": "update_detail",
                    "stdio_buffer_limit_bytes": 52428800,
                },
            },
        },
    }
    agents.create(
        agent_id="bot1",
        user_id=user_id,
        name="bot",
        config_json=json.dumps(legacy),
    )
    runners = store.load_runners(user_id)
    assert runners["opencode"]["enabled"] is True
    row = agents.get("bot1")
    assert row is not None
    cfg = json.loads(row.config_json or "{}")
    assert "runners" not in (cfg.get("acp") or {})
    assert cfg["acp"]["tool_enabled"] is True
