"""``octop.extensions`` agent policy hooks: config, share, delete, peers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra import extensions
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.extensions import load_extensions
from octop.infra.utils.paths import PathLayout

_LOCKED = "product_lock"


class _Policy:
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, Any] | None]] = []

    def normalize_agent_config(
        self,
        config: dict[str, Any],
        *,
        agent_id: str,
        user_id: int | None,
        current: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.seen.append((agent_id, current))
        out = dict(config)
        # Clients may not set the product's own key; the stored value survives edits.
        out.pop(_LOCKED, None)
        if current is not None and _LOCKED in current:
            out[_LOCKED] = current[_LOCKED]
        if out.get("name") == "refused":
            raise OctopError(ErrorCode.FORBIDDEN, "refused by product")
        return out

    def check_agent_share(self, row: Any, shared: bool) -> None:
        if shared and _LOCKED in json.loads(row.config_json or "{}"):
            raise OctopError(ErrorCode.FORBIDDEN, "locked agents stay private")

    def check_agent_delete(self, row: Any) -> None:
        if row.name == "keep":
            raise OctopError(ErrorCode.FORBIDDEN, "cannot delete")

    def hide_agent_from_peers(self, row: Any) -> bool:
        return getattr(row, "name", "") == "hidden"


@pytest.fixture()
def policy(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Policy]:
    ext = _Policy()
    monkeypatch.setattr(
        extensions, "entry_points", lambda group: [SimpleNamespace(name="p", load=lambda: ext)]
    )
    load_extensions.cache_clear()
    yield ext
    load_extensions.cache_clear()


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AgentManager:
    from octop_harness.plugins.registry import PluginRegistry

    monkeypatch.setattr(PluginRegistry, "_instance", None)
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    mgr = AgentManager(repos=services.repos, paths=services.paths)
    harness = MagicMock()
    harness.aremove_agent = AsyncMock()
    mgr._harness_manager = harness
    return mgr


def test_normalize_runs_on_create_path_and_on_every_write(
    policy: _Policy, manager: AgentManager
) -> None:
    repo = manager._repos.agent_repo
    repo.create(agent_id="a1", user_id=None, name="a", config_json=json.dumps({_LOCKED: 1}))

    out = manager._preserve_internal_layout("a1", {_LOCKED: 2, "persona": "INTJ"})

    assert out[_LOCKED] == 1
    assert out["persona"] == "INTJ"
    assert policy.seen[-1] == ("a1", {_LOCKED: 1})


@pytest.mark.asyncio
async def test_normalize_can_refuse_a_create(policy: _Policy, manager: AgentManager) -> None:
    with pytest.raises(OctopError, match="refused by product"):
        await manager.create(AgentCreateSpec(name="refused", config={"name": "refused"}))
    assert policy.seen and policy.seen[-1][1] is None
    assert manager._repos.agent_repo.list_all(include_disabled=True) == []


@pytest.mark.asyncio
async def test_check_agent_share_can_refuse(policy: _Policy, manager: AgentManager) -> None:
    repo = manager._repos.agent_repo
    repo.create(agent_id="a1", user_id=None, name="a", config_json=json.dumps({_LOCKED: 1}))
    repo.create(agent_id="a2", user_id=None, name="b", config_json="{}")

    with pytest.raises(OctopError, match="stay private"):
        await manager.set_shared("a1", True)
    assert (await manager.set_shared("a2", True)).is_shared


@pytest.mark.asyncio
async def test_check_agent_delete_can_refuse(policy: _Policy, manager: AgentManager) -> None:
    repo = manager._repos.agent_repo
    repo.create(agent_id="a1", user_id=None, name="keep")

    with pytest.raises(OctopError, match="cannot delete"):
        await manager.delete("a1")
    assert repo.get("a1") is not None
    manager._harness_manager.aremove_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_skill_hot_update_uses_the_normalized_config(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.agents.manager import skills_disabled_set

    class _KeepsWeatherOff:
        def normalize_agent_config(self, config: dict[str, Any], **_: Any) -> dict[str, Any]:
            out = dict(config)
            out["skills_disabled"] = sorted({*(out.get("skills_disabled") or []), "weather"})
            return out

    monkeypatch.setattr(
        extensions,
        "entry_points",
        lambda group: [SimpleNamespace(name="p", load=lambda: _KeepsWeatherOff())],
    )
    load_extensions.cache_clear()
    pushed: list[set[str]] = []
    running = SimpleNamespace(set_skills_disabled=lambda disabled: pushed.append(set(disabled)))
    monkeypatch.setattr(manager, "get_agent", lambda agent_id: running)
    manager._repos.agent_repo.create(
        agent_id="a1",
        user_id=None,
        name="a",
        config_json=json.dumps({"skills_disabled": ["weather"]}),
    )
    try:
        # The user enables every skill, weather included.
        await manager.persist_skills_disabled("a1", set())
    finally:
        load_extensions.cache_clear()

    assert "weather" in skills_disabled_set(manager.get_config("a1"))
    assert pushed and "weather" in pushed[-1]
