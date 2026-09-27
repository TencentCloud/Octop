"""Unit tests for update API router helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from octop.api.routers import update as update_router
from octop.api.routers import update_store
from octop.api.routers.update_store import UpgradeTaskStatus, create_task, get_task
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.setup import self_update
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

    server = _settings_server()
    first = await update_router.update_status(_=None, server=server)
    second = await update_router.update_status(_=None, server=server)
    assert first["latest_version"] == second["latest_version"]
    assert first["has_update"] == second["has_update"]
    assert builds == 1

    update_store.cache_status(
        first,
        cached_at=0.0,  # force expiry on next read
    )
    third = await update_router.update_status(_=None, server=server)
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
    monkeypatch.setattr(update_router, "_is_desktop_process", lambda: False)
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
    monkeypatch.setattr(update_router, "_is_desktop_process", lambda: False)
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
async def test_restart_endpoint_desktop_schedules_process_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[object] = []
    monkeypatch.setattr(update_router, "_is_desktop_process", lambda: True)
    monkeypatch.setattr(
        update_router,
        "_restart_desktop_process",
        lambda server: received.append(server),
    )

    from fastapi import BackgroundTasks

    fake_server = object()
    bg = BackgroundTasks()
    result = await update_router.restart_service_endpoint(bg, server=fake_server, _=None)

    assert result == {"status": "restarting", "service_mode": "desktop"}
    assert received == []
    for task in bg.tasks:
        await task()
    assert received == [fake_server]


@pytest.mark.asyncio
async def test_restart_desktop_process_checkpoints_sqlite_wal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for #800: desktop restart must flush WAL before execv."""
    checkpoints: list[str] = []
    closes: list[bool] = []
    exec_args: list[tuple[str, list[str]]] = []

    class FakeConn:
        def execute(self, sql: str) -> None:
            checkpoints.append(sql)

    class FakePool:
        dialect = "sqlite"

        def connect(self):
            class Ctx:
                def __enter__(_self):
                    return FakeConn()

                def __exit__(_self, *args):
                    return None

            return Ctx()

        def close(self) -> None:
            closes.append(True)

    class FakeServices:
        db = FakePool()

    class FakeServer:
        services = FakeServices()

    monkeypatch.setattr(
        update_router,
        "os",
        type("os", (), {"execv": lambda _self, p, a: exec_args.append((p, a))})(),
    )
    monkeypatch.setattr(
        update_router,
        "sys",
        type(
            "sys", (), {"executable": "/bin/python", "argv": ["octop", "run"], "orig_argv": None}
        )(),
    )
    monkeypatch.setattr(update_router.time, "sleep", lambda _s: None)

    update_router._restart_desktop_process(FakeServer())

    assert len(checkpoints) == 1
    assert "PRAGMA wal_checkpoint(TRUNCATE)" in checkpoints[0]
    assert closes == [True]
    assert len(exec_args) == 1


@pytest.mark.asyncio
async def test_restart_desktop_process_swallows_checkpoint_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing checkpoint should not prevent restart; data loss is logged."""
    exec_args: list[tuple[str, list[str]]] = []

    class BadPool:
        dialect = "sqlite"

        def connect(self):
            class Ctx:
                def __enter__(_self):
                    raise RuntimeError("db busy")

                def __exit__(_self, *args):
                    return None

            return Ctx()

        def close(self) -> None:
            pass

    class FakeServices:
        db = BadPool()

    class FakeServer:
        services = FakeServices()

    monkeypatch.setattr(
        update_router,
        "os",
        type("os", (), {"execv": lambda _self, p, a: exec_args.append((p, a))})(),
    )
    monkeypatch.setattr(
        update_router,
        "sys",
        type(
            "sys", (), {"executable": "/bin/python", "argv": ["octop", "run"], "orig_argv": None}
        )(),
    )
    monkeypatch.setattr(update_router.time, "sleep", lambda _s: None)

    update_router._restart_desktop_process(FakeServer())

    assert len(exec_args) == 1


@pytest.mark.asyncio
async def test_upgrade_worker_records_mirror_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        update_router,
        "run_upgrade",
        lambda verbose=False, allow_prerelease=False, version=None: UpgradeResult(
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
        lambda verbose=False, allow_prerelease=False, version=None: UpgradeResult(
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


@pytest.mark.asyncio
async def test_upgrade_worker_records_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_upgrade(
        *,
        verbose: bool = False,
        allow_prerelease: bool = False,
        version: str | None = None,
    ) -> UpgradeResult:
        del verbose, allow_prerelease, version
        raise RuntimeError("installer crashed")

    monkeypatch.setattr(update_router, "run_upgrade", fail_upgrade)

    task = await create_task()
    await update_router._upgrade_worker(task.task_id)

    stored = await get_task(task.task_id)
    assert stored is not None
    assert stored.status == UpgradeTaskStatus.ERROR
    assert stored.stage == "error"
    assert stored.error == "installer crashed"


@pytest.mark.asyncio
async def test_upgrade_worker_advances_percent_while_installing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    percents: list[int] = []
    original_update_task = update_router.update_task

    async def tracking_update_task(task_id: str, **fields: Any) -> Any:
        result = await original_update_task(task_id, **fields)
        percent = fields.get("percent")
        if isinstance(percent, int):
            percents.append(percent)
        return result

    real_wait_for = asyncio.wait_for

    async def wait_for_fast(awaitable: Any, timeout: float | None = None) -> Any:
        del timeout
        return await real_wait_for(awaitable, timeout=0.01)

    monkeypatch.setattr(update_router, "update_task", tracking_update_task)
    monkeypatch.setattr(update_router.asyncio, "wait_for", wait_for_fast)
    monkeypatch.setattr(
        update_router,
        "run_upgrade",
        lambda verbose=False, allow_prerelease=False, version=None: (
            time.sleep(0.05) or UpgradeResult(success=True, installed_version="1.2.3")
        ),
    )

    task = await create_task()
    await update_router._upgrade_worker(task.task_id)

    stored = await get_task(task.task_id)
    assert stored is not None
    assert stored.status == UpgradeTaskStatus.COMPLETE
    assert 25 in percents


def _settings_server(stable_only: bool | None = None) -> Any:
    store: dict[str, str] = {}
    if stable_only is not None:
        store["update.stable_only"] = "true" if stable_only else "false"

    class Repo:
        def get(self, key: str) -> str | None:
            return store.get(key)

        def set(self, key: str, value: str) -> None:
            store[key] = value

    return type("Server", (), {"services": type("Svc", (), {"settings_repo": Repo()})()})()


def test_build_status_success_reports_source(monkeypatch: pytest.MonkeyPatch) -> None:
    info = self_update.PyPIInfo(version="1.2.3", description="desc", source="mirrors.aliyun.com")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)

    payload = update_router._build_status()

    assert payload["latest_version"] == "1.2.3"
    assert payload["error"] is None
    assert payload["error_code"] is None
    assert payload["source"] == "mirrors.aliyun.com"


def test_build_status_failure_via_check_keeps_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = update_router._build_status(
        latest=None, error="could not reach PyPI", error_code="pypi_unreachable"
    )

    assert payload["latest_version"] is None
    assert payload["error"] == "could not reach PyPI"
    assert payload["error_code"] == "pypi_unreachable"


@pytest.mark.asyncio
async def test_check_endpoint_reports_error_code_when_pypi_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: None)

    result = await update_router.check_for_updates(_=None, server=_settings_server())

    assert result["latest_version"] is None
    assert result["error"] == "could not reach PyPI"
    assert result["error_code"] == "pypi_unreachable"


@pytest.mark.asyncio
async def test_check_endpoint_success_passes_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = self_update.PyPIInfo(version="1.2.3", source="pypi.org")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)

    result = await update_router.check_for_updates(_=None, server=_settings_server())

    assert result["latest_version"] == "1.2.3"
    assert result["source"] == "pypi.org"
    assert result["error"] is None
    assert result["stable_only"] is True
    assert result["latest_is_prerelease"] is False


@pytest.mark.asyncio
async def test_status_stable_only_ignores_prerelease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = self_update.PyPIInfo(version="0.9.34b1", latest_stable="0.9.33", source="pypi.org")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)
    monkeypatch.setattr(update_router, "get_local_version", lambda: "0.9.32")

    auto = await update_router.update_status(_=None, server=_settings_server(True))
    assert auto["latest_version"] == "0.9.33"
    assert auto["has_update"] is True
    assert auto["latest_is_prerelease"] is False
    assert auto["stable_only"] is True

    manual = await update_router.check_for_updates(_=None, server=_settings_server(True))
    assert manual["latest_version"] == "0.9.34b1"
    assert manual["has_update"] is True
    assert manual["latest_is_prerelease"] is True


@pytest.mark.asyncio
async def test_status_includes_prerelease_when_stable_only_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = self_update.PyPIInfo(version="0.9.34b1", latest_stable="0.9.33", source="pypi.org")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)
    monkeypatch.setattr(update_router, "get_local_version", lambda: "0.9.33")

    auto = await update_router.update_status(_=None, server=_settings_server(False))
    assert auto["latest_version"] == "0.9.34b1"
    assert auto["has_update"] is True
    assert auto["latest_is_prerelease"] is True


@pytest.mark.asyncio
async def test_patch_settings_remaps_cached_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = self_update.PyPIInfo(version="0.9.34b1", latest_stable="0.9.33", source="pypi.org")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)
    monkeypatch.setattr(update_router, "get_local_version", lambda: "0.9.33")
    server = _settings_server(True)

    first = await update_router.update_status(_=None, server=server)
    assert first["latest_version"] == "0.9.33"
    assert first["has_update"] is False

    body = update_router.UpdateSettingsBody(stable_only=False)
    patched = await update_router.update_settings(body, server=server, _=None)
    assert patched["stable_only"] is False
    assert patched["latest_version"] == "0.9.34b1"
    assert patched["has_update"] is True
    assert server.services.settings_repo.get("update.stable_only") == "false"


@pytest.mark.asyncio
async def test_trigger_upgrade_pins_stable_when_prerelease_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = self_update.PyPIInfo(version="0.9.34b1", latest_stable="0.9.33", source="pypi.org")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)
    monkeypatch.setattr(update_router, "get_editable_path", lambda: None)

    captured: dict[str, object] = {}

    async def fake_worker(
        task_id: str,
        *,
        allow_prerelease: bool = False,
        version: str | None = None,
    ) -> None:
        captured["task_id"] = task_id
        captured["allow_prerelease"] = allow_prerelease
        captured["version"] = version

    monkeypatch.setattr(update_router, "_upgrade_worker", fake_worker)

    body = update_router.UpgradeBody(version="0.9.33")
    result = await update_router.trigger_upgrade(
        body=body,
        server=_settings_server(True),
        _=None,
    )
    await asyncio.sleep(0)
    assert result["status"] == "started"
    assert captured["version"] == "0.9.33"
    assert captured["allow_prerelease"] is False


@pytest.mark.asyncio
async def test_trigger_upgrade_defaults_to_channel_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = self_update.PyPIInfo(version="0.9.34b1", latest_stable="0.9.33", source="pypi.org")
    monkeypatch.setattr(update_router, "fetch_pypi_info", lambda: info)
    monkeypatch.setattr(update_router, "get_editable_path", lambda: None)

    captured: dict[str, object] = {}

    async def fake_worker(
        task_id: str,
        *,
        allow_prerelease: bool = False,
        version: str | None = None,
    ) -> None:
        captured["allow_prerelease"] = allow_prerelease
        captured["version"] = version

    monkeypatch.setattr(update_router, "_upgrade_worker", fake_worker)

    result = await update_router.trigger_upgrade(
        body=update_router.UpgradeBody(),
        server=_settings_server(True),
        _=None,
    )
    await asyncio.sleep(0)
    assert result["status"] == "started"
    assert captured["version"] == "0.9.33"
    assert captured["allow_prerelease"] is False


@pytest.mark.asyncio
async def test_upgrade_worker_falls_back_to_pinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        update_router,
        "run_upgrade",
        lambda verbose=False, allow_prerelease=False, version=None: UpgradeResult(
            success=True,
            installed_version=None,
        ),
    )

    task = await create_task()
    await update_router._upgrade_worker(task.task_id, version="0.9.33")

    stored = await get_task(task.task_id)
    assert stored is not None
    assert stored.status == UpgradeTaskStatus.COMPLETE
    assert stored.new_version == "0.9.33"
