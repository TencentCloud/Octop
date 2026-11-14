"""Deletion must not leave a runtime registered after its row has disappeared."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from octop_harness import HarnessAgent, HarnessAgentManager

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


class ObservedLock(asyncio.Lock):
    """Expose contention without changing asyncio's real locking behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.waiting = asyncio.Event()

    async def acquire(self) -> bool:
        if self.locked():
            self.waiting.set()
        return await super().acquire()


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[AgentManager]:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=paths)
    manager._repos.provider_repo.create(
        name="offline",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="test",
        models_json=json.dumps([{"id": "gpt-4o-mini", "enabled": True}]),
    )
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
        file_logging=False,
    )
    manager._repos.agent_repo.create(
        agent_id="race-agent",
        user_id=None,
        name="race-agent",
        config_json=json.dumps({"memory": {"memory_enabled": False}}),
    )
    try:
        yield manager
    finally:
        await manager._harness_manager.aclose()
        db.close()


async def wait_for_contention_or_completion(task: asyncio.Task[Any], lock: ObservedLock) -> None:
    """Let the old implementation finish, or wait until the fixed one is blocked."""
    waiter = asyncio.create_task(lock.waiting.wait())
    try:
        done, _ = await asyncio.wait(
            {task, waiter}, timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        assert done, "lifecycle operation neither completed nor waited for its peer"
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


@pytest.mark.parametrize("operation", ["start", "reload"])
async def test_delete_waits_for_inflight_graph_registration(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """A compilation already holding the lock must finish before deletion removes it."""
    if operation == "reload":
        await manager.start("race-agent")
    lock = ObservedLock()
    manager._agent_lifecycle_locks["race-agent"] = lock
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = HarnessAgent._init_graph

    def compile_graph(agent: HarnessAgent) -> None:
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10), "test did not release graph compilation"
        original(agent)

    monkeypatch.setattr(HarnessAgent, "_init_graph", compile_graph)
    row = manager.get_row("race-agent")
    assert row is not None
    # Boot and background reload do not hold start()'s global manager lock.
    loading = asyncio.create_task(
        manager._start_agent(row, init_workspace=False)
        if operation == "start"
        else manager.reload("race-agent")
    )
    deleting: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        deleting = asyncio.create_task(manager.delete("race-agent"))
        await wait_for_contention_or_completion(deleting, lock)
        release.set()
        await asyncio.wait_for(asyncio.gather(loading, deleting), timeout=20)
        assert manager.get_row("race-agent") is None
        with pytest.raises(KeyError):
            manager._harness_manager.get_agent("race-agent")
        assert not manager.paths.agent_workspace("race-agent").exists()
    finally:
        release.set()
        await asyncio.gather(loading, *([deleting] if deleting else []), return_exceptions=True)


@pytest.mark.parametrize("operation", ["start", "reload"])
async def test_queued_loader_cannot_resurrect_an_agent_during_delete_cleanup(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """Queued starts must also discard the row they fetched before waiting."""
    await manager.start("race-agent")
    lock = ObservedLock()
    manager._agent_lifecycle_locks["race-agent"] = lock
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def purge(**_kwargs: Any) -> None:
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10), "test did not release memory cleanup"

    monkeypatch.setattr(
        "octop.infra.agents.memory.thread_cleanup.delete_agent_memory_and_checkpoints",
        purge,
    )
    deleting = asyncio.create_task(manager.delete("race-agent"))
    loading: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        loading = asyncio.create_task(getattr(manager, operation)("race-agent"))
        await wait_for_contention_or_completion(loading, lock)
        release.set()
        await asyncio.wait_for(deleting, timeout=20)
        if operation == "start":
            with pytest.raises(OctopError) as exc:
                await asyncio.wait_for(loading, timeout=20)
            assert exc.value.code is ErrorCode.AGENT_NOT_FOUND
        else:
            await asyncio.wait_for(loading, timeout=20)
        assert manager.get_row("race-agent") is None
        with pytest.raises(KeyError):
            manager._harness_manager.get_agent("race-agent")
    finally:
        release.set()
        await asyncio.gather(deleting, *([loading] if loading else []), return_exceptions=True)


async def test_failed_delete_releases_lifecycle_lock_and_can_be_retried(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed storage purge keeps the row and must not deadlock a later start/delete."""
    await manager.start("race-agent")
    calls = 0

    def purge(**_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("memory store unavailable")

    monkeypatch.setattr(
        "octop.infra.agents.memory.thread_cleanup.delete_agent_memory_and_checkpoints",
        purge,
    )
    with pytest.raises(RuntimeError, match="memory store unavailable"):
        await manager.delete("race-agent")
    assert manager.get_row("race-agent") is not None
    await asyncio.wait_for(manager.start("race-agent"), timeout=20)
    manager.get_agent("race-agent")
    await asyncio.wait_for(manager.delete("race-agent"), timeout=20)
    assert calls == 2
    assert manager.get_row("race-agent") is None


async def test_delete_cleanup_does_not_hold_the_global_manager_lock(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow purge for one agent must not prevent an independent agent from starting."""
    manager._repos.agent_repo.create(
        agent_id="other-agent",
        user_id=None,
        name="other-agent",
        config_json=json.dumps({"memory": {"memory_enabled": False}}),
    )
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def purge(**_kwargs: Any) -> None:
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10), "test did not release memory cleanup"

    monkeypatch.setattr(
        "octop.infra.agents.memory.thread_cleanup.delete_agent_memory_and_checkpoints",
        purge,
    )
    deleting = asyncio.create_task(manager.delete("race-agent"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        await asyncio.wait_for(manager.start("other-agent"), timeout=5)
        manager.get_agent("other-agent")
        assert not deleting.done()
    finally:
        release.set()
        await asyncio.wait_for(deleting, timeout=20)


async def test_delete_preserves_coordination_with_inflight_team_creation(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wait for a team to finish seeding before removing its deleted member."""
    from octop.infra.agents.teams import service

    manager._repos.agent_repo.create(agent_id="other-agent", user_id=None, name="other")
    global_lock = ObservedLock()
    manager._lock = global_lock
    entered = asyncio.Event()
    release = asyncio.Event()
    original = service.seed_team_template

    async def seed(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "seed_team_template", seed)
    creating = asyncio.create_task(
        manager.create(
            AgentCreateSpec(
                name="New team",
                agent_id="new-team",
                kind="team",
                member_ids=["race-agent", "other-agent"],
                config={"memory": {"memory_enabled": False}},
            )
        )
    )
    deleting: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        deleting = asyncio.create_task(manager.delete("race-agent"))
        await wait_for_contention_or_completion(deleting, global_lock)
        release.set()
        await asyncio.wait_for(asyncio.gather(creating, deleting), timeout=30)
        assert manager.get_row("race-agent") is None
        assert "race-agent" not in manager._harness_manager.get_agent("new-team").config.team_peers
        assert "race-agent" not in manager._teams.member_ids("new-team")
    finally:
        release.set()
        await asyncio.gather(creating, *([deleting] if deleting else []), return_exceptions=True)
