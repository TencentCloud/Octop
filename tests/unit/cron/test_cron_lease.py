"""Cron execution leases and background reconciliation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from tests.unit.cron.test_cron_manager import (
    _cron_id,
    _cron_session_key,
    _make_agent,
    _make_manager,
    _make_services,
)

from octop.infra.db.lease import LEASE_SECONDS
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.asyncio
async def test_run_now_skips_when_another_instance_holds_the_lease(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    services.repos.cron_repo.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:3600",
        prompt="run",
        session_key=_cron_session_key(aid, cid),
    )
    held = services.repos.cron_repo.claim_run(cid, owner="other", lease_seconds=LEASE_SECONDS)
    assert held is not None

    with pytest.raises(OctopError) as exc:
        await mgr.run_now(cid, wait=True)

    assert exc.value.code is ErrorCode.CRON_ALREADY_RUNNING
    row = services.repos.cron_repo.get(cid)
    assert row is not None
    assert row.last_status is None
    assert row.run_lease_owner == "other"


@pytest.mark.asyncio
async def test_overlapping_run_now_delivers_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    first = _make_manager(services)
    second = _make_manager(services)
    cid = _cron_id()
    await first.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:3600",
        prompt="run",
    )
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def _deliver(_command: object) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    first._delivery_service.deliver = _deliver  # type: ignore[method-assign]
    second._delivery_service.deliver = _deliver  # type: ignore[method-assign]
    monkeypatch.setattr("octop.infra.cron.manager.RENEW_SECONDS", 30)

    running = asyncio.create_task(first.run_now(cid, wait=True))
    await started.wait()
    with pytest.raises(OctopError) as exc:
        await second.run_now(cid, wait=True)
    assert exc.value.code is ErrorCode.CRON_ALREADY_RUNNING
    release.set()
    await running
    assert calls == 1
    row = services.repos.cron_repo.get(cid)
    assert row is not None
    assert row.last_status == "ok"
    assert row.run_lease_token is None


@pytest.mark.asyncio
async def test_lost_lease_does_not_record_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    cid = _cron_id()
    await mgr.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:3600",
        prompt="run",
    )
    started = asyncio.Event()

    async def _deliver(_command: object) -> None:
        started.set()
        await asyncio.Event().wait()

    mgr._delivery_service.deliver = _deliver  # type: ignore[method-assign]
    monkeypatch.setattr("octop.infra.cron.manager.RENEW_SECONDS", 0.01)
    monkeypatch.setattr(services.repos.cron_repo, "renew_run_lease", lambda *_a, **_k: False)

    with pytest.raises(OctopError) as exc:
        await mgr.run_now(cid, wait=True)

    assert exc.value.code is ErrorCode.CRON_ALREADY_RUNNING
    assert started.is_set()
    row = services.repos.cron_repo.get(cid)
    assert row is not None
    assert row.last_status is None


@pytest.mark.asyncio
async def test_reconcile_schedules_job_created_outside_the_manager(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    aid, uid = _make_agent(services)
    mgr = _make_manager(services)
    await mgr.boot()
    mgr._scheduler.add_job.reset_mock()
    cid = _cron_id()
    services.repos.cron_repo.create(
        cron_id=cid,
        agent_id=aid,
        user_id=uid,
        trigger="interval:60",
        prompt="later",
        session_key=_cron_session_key(aid, cid),
    )

    await mgr.reconcile_user_jobs()

    mgr._scheduler.add_job.assert_called_once()
    assert mgr._scheduler.add_job.call_args.kwargs["id"] == cid
    await mgr.shutdown()
