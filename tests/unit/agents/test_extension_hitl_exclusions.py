"""``hitl_excluded_tools`` reaches what the harness enforces, not only the picker."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from octop_harness.security.models import SecurityPolicy

from octop.config import OctopConfig
from octop.infra import extensions
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.security.policy_store import without_hitl_tools
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.extensions import clear_extension_caches
from octop.infra.utils.paths import PathLayout


@pytest.fixture(autouse=True)
def excludes_write_file(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    product = SimpleNamespace(hitl_excluded_tools=lambda: ["write_file"])
    monkeypatch.setattr(
        extensions, "entry_points", lambda group: [SimpleNamespace(name="p", load=lambda: product)]
    )
    clear_extension_caches()
    yield
    clear_extension_caches()


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AgentManager:
    from octop_harness.plugins.registry import PluginRegistry

    monkeypatch.setattr(PluginRegistry, "_instance", None)
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return AgentManager(repos=services.repos, paths=services.paths)


def _row(config: dict[str, object]) -> AgentRow:
    return AgentRow(
        id=1,
        agent_id="01AGENT",
        user_id=1,
        name="bot",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json=json.dumps(config),
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
    )


def test_without_hitl_tools_handles_default_and_explicit_lists() -> None:
    default = SecurityPolicy.from_dict({"hitl": {"enabled": True, "tools": "default"}})
    trimmed = without_hitl_tools(default, {"write_file"})
    assert "write_file" not in (trimmed.resolve_interrupt_on() or {})
    assert "bash" in (trimmed.resolve_interrupt_on() or {})
    explicit = SecurityPolicy.from_dict({"hitl": {"enabled": True, "tools": ["write_file"]}})
    assert without_hitl_tools(explicit, {"write_file"}).resolve_interrupt_on() is None
    assert without_hitl_tools(explicit, set()) is explicit


def test_build_and_hot_update_leave_excluded_tools_out(manager: AgentManager) -> None:
    harness = MagicMock()
    manager._harness_manager = harness
    # A saved global policy that explicitly asks approval for write_file.
    manager.save_security({"hitl": {"enabled": True, "tools": ["write_file", "bash"]}})

    pushed = harness.set_security_policy.call_args.args[0]
    assert set(pushed.resolve_interrupt_on() or {}) == {"bash"}
    # The stored policy (what the settings page edits) is unchanged.
    assert manager._security.load().hitl.tools == ["write_file", "bash"]

    # An agent override that lists write_file again does not bring it back.
    override = {"security": {"hitl": {"enabled": True, "tools": ["write_file", "edit_file"]}}}
    cfg = manager._build_harness_config(_row(override))
    assert "write_file" not in (cfg.interrupt_on or {})
    assert "edit_file" in (cfg.interrupt_on or {})
