"""Unit tests for update API router helpers."""

from __future__ import annotations

import pytest

from octop.api.routers import update as update_router
from octop.api.routers import update_store
from octop.api.routers.update_store import UpgradeTaskStatus, create_task, get_task
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.setup.self_update import UpgradeResult


@pytest.fixture(autouse=True)
def _clear_update_status_cache() -> None:
    update_store.clear_cached_status()
    yield
    update_store.clear_cached_status()


@pytest.mark.asyncio
async def test_update_status_reprobes_after_cache_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds = 0

    def fake_build(**_: object) -> dict[str, object]:
        nonlocal builds
        builds += 1
        payload = {
            "current_version": "1.0.0",
            "latest_version": "1.0.1",
            "has_update": True,
            "is_editable": False,
            "service_mode": None,
            "error": None,
            "last_check_time": "2026-01-01T00:00:00Z",
            "release_notes": None,
        }
        update_store.cache_status(payload)
        return payload

    monkeypatch.setattr(update_router, "_build_status", fake_build)

    first = await update_router.update_status(_=None)
    second = await update_router.update_status(_=None)
    assert first == second
    assert builds == 1

    update_store.cache_status(
        first,
        cached_at=0.0,  # force expiry on next read
    )
    third = await update_router.update_status(_=None)
    assert third["has_update"] is True
    assert builds == 2


@pytest.mark.asyncio
async def test_restart_endpoint_schedules_background_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restarted: list[object] = []
    fake_runtime = type(
        "Runtime",
        (),
        {"mode": "systemd", "scope": None, "run_as_user": None},
    )()

    monkeypatch.setattr(update_router, "detect_service_mode", lambda: "systemd")
    monkeypatch.setattr(update_router, "build_runtime", lambda mode: fake_runtime)
    monkeypatch.setattr(update_router, "is_service_installed", lambda *_, **__: True)
    monkeypatch.setattr(
        update_router,
        "restart_service",
        lambda runtime: restarted.append(runtime),
    )

    from fastapi import BackgroundTasks

    bg = BackgroundTasks()
    result = await update_router.restart_service_endpoint(bg, _=None)

    assert result == {"status": "restarting", "service_mode": "systemd"}
    assert restarted == []

    for task in bg.tasks:
        await task()

    assert restarted == [fake_runtime]


@pytest.mark.asyncio
async def test_restart_endpoint_rejects_when_service_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restarted: list[object] = []
    fake_runtime = type(
        "Runtime",
        (),
        {"mode": "systemd", "scope": None, "run_as_user": None},
    )()

    monkeypatch.setattr(update_router, "detect_service_mode", lambda: "systemd")
    monkeypatch.setattr(update_router, "build_runtime", lambda mode: fake_runtime)
    monkeypatch.setattr(update_router, "is_service_installed", lambda *_, **__: False)
    monkeypatch.setattr(
        update_router,
        "restart_service",
        lambda runtime: restarted.append(runtime),
    )

    from fastapi import BackgroundTasks

    bg = BackgroundTasks()
    with pytest.raises(OctopError) as exc_info:
        await update_router.restart_service_endpoint(bg, _=None)

    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    assert restarted == []
    assert bg.tasks == []


@pytest.mark.asyncio
async def test_upgrade_worker_records_mirror_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        update_router,
        "run_upgrade",
        lambda verbose=False: UpgradeResult(
            success=False,
            error="upgrade failed on all mirrors",
            mirror_errors=["mirror-a: timeout", "pypi.org: denied"],
        ),
    )

    task = await create_task()
    await update_router._upgrade_worker(task.task_id)

    stored = await get_task(task.task_id)
    assert stored is not None
    assert stored.status == UpgradeTaskStatus.ERROR
    assert stored.mirror_errors == ["mirror-a: timeout", "pypi.org: denied"]


@pytest.mark.asyncio
async def test_upgrade_worker_success_includes_mirror_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        update_router,
        "run_upgrade",
        lambda verbose=False: UpgradeResult(
            success=True,
            installed_version="1.2.3",
            mirror_errors=["mirror-a: skipped"],
        ),
    )

    task = await create_task()
    await update_router._upgrade_worker(task.task_id)

    stored = await get_task(task.task_id)
    assert stored is not None
    assert stored.status == UpgradeTaskStatus.COMPLETE
    assert stored.new_version == "1.2.3"
    assert stored.mirror_errors == ["mirror-a: skipped"]
