"""CLI cron runs must finish before their embedded runtime is torn down."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support import embedded_ops, offline_ops
from octop.config import OctopConfig
from octop.infra.cron.manager import CronManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def cron_runtime(tmp_path, monkeypatch):
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    services = build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())
    repos = services.repos
    uid = repos.user_repo.create(username="owner", password_hash="x", role="user")
    repos.agent_repo.create(agent_id="agent-1", user_id=uid, name="test-agent")
    repos.cron_repo.create(
        cron_id="job-1",
        agent_id="agent-1",
        user_id=uid,
        trigger="interval:3600",
        prompt="test",
        session_key="agent-1:dashboard:1:dm",
    )
    delivery = MagicMock()
    mgr = CronManager(gateway=MagicMock(), delivery_service=delivery, repos=repos)
    server = SimpleNamespace(app_runtime=SimpleNamespace(cron_manager=mgr))
    snapshots = []

    @asynccontextmanager
    async def runtime():
        try:
            yield server
        finally:
            row = repos.cron_repo.get("job-1")
            audit = repos.audit_repo.query(limit=10)
            snapshots.append((row.last_status, row.last_run_at, [entry.action for entry in audit]))

    monkeypatch.setattr(embedded_ops, "embedded_runtime", runtime)
    monkeypatch.setattr(offline_ops, "resolve_cron_user_id", lambda *_: uid)
    try:
        yield mgr, delivery, snapshots
    finally:
        db.close()


@pytest.mark.parametrize(
    "error",
    [
        None,
        RuntimeError("delivery failed"),
        OctopError(ErrorCode.AGENT_NOT_RUNNING, "agent stopped"),
    ],
)
def test_cli_waits_for_delivery_and_bookkeeping(cron_runtime, error):
    _, delivery, snapshots = cron_runtime

    async def deliver(_command):
        # Real delivery yields to model / channel I/O before it completes.
        await asyncio.sleep(0)
        if error is not None:
            raise error

    delivery.deliver = deliver
    result = CliRunner().invoke(cli, ["cron", "run-now", "job-1", "--agent", "agent-1"])

    status, timestamp, actions = snapshots[0]
    assert status == ("ok" if error is None else "error")
    assert timestamp is not None
    assert actions == ["cron.run_ok" if error is None else "cron.run_failed"]
    if error is None:
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "ok"
    else:
        assert result.exit_code == 1
        assert str(error) in result.output
        assert "ok" not in result.output.splitlines()


@pytest.mark.parametrize("agent_id,cron_id", [("other-agent", "job-1"), ("agent-1", "missing")])
def test_cli_rejects_missing_or_wrong_agent_job(cron_runtime, agent_id, cron_id):
    _, delivery, _ = cron_runtime
    result = CliRunner().invoke(cli, ["cron", "run-now", cron_id, "--agent", agent_id])
    assert result.exit_code == 1
    assert "cron job not found" in result.output
    delivery.deliver.assert_not_called()


@pytest.mark.asyncio
async def test_default_run_now_does_not_wait_for_delivery(cron_runtime):
    mgr, delivery, _ = cron_runtime
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def deliver(_command):
        started.set()
        await release.wait()
        finished.set()

    delivery.deliver = deliver
    trigger = asyncio.create_task(mgr.run_now("job-1"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        assert trigger.done(), "HTTP/tool callers must return while delivery is still running"
        assert not finished.is_set()
    finally:
        release.set()
        await trigger
        await asyncio.wait_for(finished.wait(), timeout=5)


@pytest.mark.asyncio
async def test_waiting_run_propagates_cancellation(cron_runtime):
    mgr, delivery, _ = cron_runtime
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def deliver(_command):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    delivery.deliver = deliver
    task = asyncio.create_task(embedded_ops.cron_run_now_async("agent-1", "job-1"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert stopped.is_set()
