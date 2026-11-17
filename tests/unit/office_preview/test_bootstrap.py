from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from octop.infra.office_preview import bootstrap
from octop.infra.office_preview.runtime import RuntimeProbe
from octop.infra.utils.paths import PathLayout


@pytest.mark.parametrize("reason", ["ok", "node_missing", "node_too_old"])
async def test_bootstrap_skips_ready_or_unsupported_runtime(
    monkeypatch, tmp_path: Path, reason: str
):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        bootstrap,
        "probe_runtime",
        lambda _paths: RuntimeProbe(reason == "ok", None, None, None, reason),
    )
    spawn = AsyncMock()
    monkeypatch.setattr(bootstrap.asyncio, "create_subprocess_exec", spawn)
    await bootstrap.ensure_office_preview_runtime(PathLayout(tmp_path))
    spawn.assert_not_called()


@pytest.mark.parametrize("returncode", [0, 1])
async def test_bootstrap_installs_in_child_and_failure_is_nonfatal(
    monkeypatch, tmp_path: Path, returncode: int
):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        bootstrap,
        "probe_runtime",
        lambda _paths: RuntimeProbe(False, None, None, None, "kit_missing"),
    )
    proc = Mock(returncode=returncode, wait=AsyncMock(return_value=returncode))
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(bootstrap.asyncio, "create_subprocess_exec", spawn)
    await bootstrap.ensure_office_preview_runtime(PathLayout(tmp_path))
    assert spawn.call_args.kwargs["env"]["OCTOP_HOME"] == str(tmp_path)
    assert spawn.call_args.args[1:] == ("-m", "octop.infra.office_preview.bootstrap")
    proc.kill.assert_not_called()


async def test_shutdown_cancels_install_and_reaps_child(monkeypatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        bootstrap,
        "probe_runtime",
        lambda _paths: RuntimeProbe(False, None, None, None, "helper_missing"),
    )
    waiting = asyncio.Event()
    calls = 0

    async def wait():  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            waiting.set()
            await asyncio.Event().wait()
        return -9

    proc = Mock(returncode=None, pid=123, wait=AsyncMock(side_effect=wait))
    monkeypatch.setattr(
        bootstrap.asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=[proc, Mock(wait=AsyncMock(return_value=0))]),
    )
    killpg = Mock()
    monkeypatch.setattr(bootstrap.os, "killpg", killpg, raising=False)
    task = asyncio.create_task(bootstrap.ensure_office_preview_runtime(PathLayout(tmp_path)))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.wait.await_count == 2
    if bootstrap.os.name == "posix":
        killpg.assert_called_once()
    else:
        proc.kill.assert_called_once()


def test_worker_rechecks_runtime_under_lock(monkeypatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.delenv("OCTOP_OFFICE_PREVIEW_RUNTIME", raising=False)
    available = False

    def install(**_kwargs):  # type: ignore[no-untyped-def]
        nonlocal available
        available = True

    installer = Mock(side_effect=install)
    monkeypatch.setattr(bootstrap, "install_runtime", installer)
    monkeypatch.setattr(
        bootstrap,
        "probe_runtime",
        lambda _paths: RuntimeProbe(
            available, None, None, None, "ok" if available else "kit_missing"
        ),
    )
    bootstrap._install_if_missing(PathLayout(tmp_path))
    bootstrap._install_if_missing(PathLayout(tmp_path))
    installer.assert_called_once()


async def test_server_owns_and_cancels_background_install(monkeypatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    from octop.infra.server import OctopServer

    started = asyncio.Event()

    async def install(_paths: object) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("octop.infra.server.ensure_office_preview_runtime", install)
    server = OctopServer(home=tmp_path)
    server._started = True
    server._start_office_preview_install()
    task = server._office_preview_install_task
    assert task is not None
    await started.wait()
    await server.stop()
    assert task.cancelled()
    assert server._office_preview_install_task is None


async def test_embedded_server_does_not_start_install(tmp_path: Path):
    from octop.infra.server import OctopServer

    server = OctopServer(home=tmp_path)
    server._serve_background = False
    server._start_office_preview_install()
    assert server._office_preview_install_task is None
