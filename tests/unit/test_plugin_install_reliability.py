"""Regression coverage for transactional installs and event-loop ownership."""

from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path

import pytest
from octop_harness.plugins import PluginRegistry

from octop.infra.agents.plugins import manager as module
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/plugins/echo-tool"


@pytest.fixture
def manager(tmp_path: Path) -> PluginManager:
    PluginRegistry.reset()
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    return PluginManager(plugins_dir=tmp_path / "plugins", config_path=config)


def test_conflict_before_dependencies(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager.install_path(FIXTURE)

    def forbidden(_: Path) -> None:
        pytest.fail("conflict must not execute pip")

    monkeypatch.setattr(module, "install_dependencies", forbidden)
    with pytest.raises(OctopError) as exc:
        manager.install_path(FIXTURE)
    assert exc.value.code is ErrorCode.PLUGIN_ALREADY_EXISTS


def test_failed_update_restores_registration(manager: PluginManager, tmp_path: Path) -> None:
    old = manager.install_path(FIXTURE)
    source = tmp_path / "broken"
    shutil.copytree(FIXTURE, source)
    (source / "main.py").write_text("raise RuntimeError('broken update')", encoding="utf-8")
    with pytest.raises(OctopError):
        manager.install_path(source, force=True)
    assert PluginRegistry().get("echo-tool") is old
    assert (manager.plugins_dir / "echo-tool/main.py").read_bytes() == (
        FIXTURE / "main.py"
    ).read_bytes()


def test_rename_failure_preserves_old_registry(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = manager.install_path(FIXTURE)

    def fail(self: Path, target: Path) -> Path:
        raise OSError("rename denied")

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OctopError):
        manager.install_path(FIXTURE, force=True)
    assert PluginRegistry().get("echo-tool") is old


def test_disabled_force_stays_unloaded(manager: PluginManager) -> None:
    manager.install_path(FIXTURE)
    manager.set_enabled("echo-tool", False)
    manager.install_path(FIXTURE, force=True)
    assert PluginRegistry().get("echo-tool") is None
    assert manager.global_enabled_map()["echo-tool"] is False


async def test_worker_and_registration_threads(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = threading.get_ident()
    worker: list[int] = []
    registered: list[int] = []
    load = module._load_plugin_dir
    monkeypatch.setattr(
        module, "install_dependencies", lambda _: worker.append(threading.get_ident())
    )

    def record(path: Path, *, install_deps: bool):  # type: ignore[no-untyped-def]
        registered.append(threading.get_ident())
        return load(path, install_deps=install_deps)

    monkeypatch.setattr(module, "_load_plugin_dir", record)
    await manager.install_async("install_path", FIXTURE)
    assert worker and worker[0] != main
    assert registered == [main]


async def test_cancellation_holds_lock_until_worker_finishes(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def dependencies(_: Path) -> None:
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(module, "install_dependencies", dependencies)
    task = asyncio.create_task(manager.install_async("install_path", FIXTURE))
    while not entered.is_set():
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    try:
        with pytest.raises(OctopError) as exc:
            await manager.install_async("install_path", FIXTURE, force=True)
        assert exc.value.code is ErrorCode.PLUGIN_ALREADY_EXISTS
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert PluginRegistry().get("echo-tool") is not None


def test_disabled_market_force_stays_disabled(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manager, "market_plugin_dir", lambda _: FIXTURE)
    manager.install_from_market("echo-tool")
    manager.set_enabled("echo-tool", False)
    manager.install_from_market("echo-tool", force=True)
    assert manager.global_enabled_map()["echo-tool"] is False
    assert PluginRegistry().get("echo-tool") is None


def test_dependency_failure_keeps_old_files(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = manager.install_path(FIXTURE)

    def fail(_: Path) -> None:
        raise RuntimeError("pip failed")

    monkeypatch.setattr(module, "install_dependencies", fail)
    with pytest.raises(OctopError, match="pip failed"):
        manager.install_path(FIXTURE, force=True)
    assert PluginRegistry().get("echo-tool") is old
    assert (manager.plugins_dir / "echo-tool/plugin.yaml").is_file()
