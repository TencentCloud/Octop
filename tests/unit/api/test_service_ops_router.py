"""Unit tests for the service control router (restart + version info)."""

from __future__ import annotations

from typing import Any

import pytest

from octop.api.routers import service_ops
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.asyncio
async def test_service_status_does_not_touch_a_package_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_ops, "get_local_version", lambda: "1.2.3")
    monkeypatch.setattr(service_ops, "detect_service_mode", lambda: "systemd")
    monkeypatch.setattr(service_ops, "is_desktop_process", lambda: False)

    result = await service_ops.service_status(_=None)

    assert result == {
        "current_version": "1.2.3",
        "service_mode": "systemd",
        "desktop": False,
    }


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

    monkeypatch.setattr(service_ops, "detect_service_mode", lambda: "systemd")
    monkeypatch.setattr(service_ops, "is_desktop_process", lambda: False)
    monkeypatch.setattr(service_ops, "build_runtime", lambda mode: fake_runtime)
    monkeypatch.setattr(service_ops, "is_service_installed", lambda *_, **__: True)
    monkeypatch.setattr(
        service_ops,
        "restart_service",
        lambda runtime: restarted.append(runtime),
    )

    from fastapi import BackgroundTasks

    bg = BackgroundTasks()
    result = await service_ops.restart_service_endpoint(bg, _=None)

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

    monkeypatch.setattr(service_ops, "detect_service_mode", lambda: "systemd")
    monkeypatch.setattr(service_ops, "is_desktop_process", lambda: False)
    monkeypatch.setattr(service_ops, "build_runtime", lambda mode: fake_runtime)
    monkeypatch.setattr(service_ops, "is_service_installed", lambda *_, **__: False)
    monkeypatch.setattr(
        service_ops,
        "restart_service",
        lambda runtime: restarted.append(runtime),
    )

    from fastapi import BackgroundTasks

    bg = BackgroundTasks()
    with pytest.raises(OctopError) as exc_info:
        await service_ops.restart_service_endpoint(bg, _=None)

    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    assert restarted == []
    assert bg.tasks == []


@pytest.mark.asyncio
async def test_restart_endpoint_desktop_schedules_process_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[object] = []
    monkeypatch.setattr(service_ops, "is_desktop_process", lambda: True)
    monkeypatch.setattr(
        service_ops,
        "_restart_desktop_process",
        lambda server: received.append(server),
    )

    from fastapi import BackgroundTasks

    fake_server: Any = object()
    bg = BackgroundTasks()
    result = await service_ops.restart_service_endpoint(bg, server=fake_server, _=None)

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
        service_ops,
        "os",
        type("os", (), {"execv": lambda _self, p, a: exec_args.append((p, a))})(),
    )
    monkeypatch.setattr(
        service_ops,
        "sys",
        type(
            "sys", (), {"executable": "/bin/python", "argv": ["octop", "run"], "orig_argv": None}
        )(),
    )
    monkeypatch.setattr(service_ops.time, "sleep", lambda _s: None)

    service_ops._restart_desktop_process(FakeServer())

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
        service_ops,
        "os",
        type("os", (), {"execv": lambda _self, p, a: exec_args.append((p, a))})(),
    )
    monkeypatch.setattr(
        service_ops,
        "sys",
        type(
            "sys", (), {"executable": "/bin/python", "argv": ["octop", "run"], "orig_argv": None}
        )(),
    )
    monkeypatch.setattr(service_ops.time, "sleep", lambda _s: None)

    service_ops._restart_desktop_process(FakeServer())

    assert len(exec_args) == 1
