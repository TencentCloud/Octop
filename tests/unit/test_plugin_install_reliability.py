"""Regression coverage for transactional installs and event-loop ownership."""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
import zipfile
from pathlib import Path

import pytest
from octop_harness.plugins import PluginRegistry

from octop.infra.agents.plugins import installation
from octop.infra.agents.plugins import manager as module
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/plugins/echo-tool"
MARKET_ARCHIVE = "https://download.octop.cloud/plugins/echo-tool.zip"


def mock_market_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "get_market_plugin",
        lambda plugin_id: {
            "id": plugin_id,
            "version": "1.0.0",
            "download_url": MARKET_ARCHIVE,
        },
    )

    def download(_url: str, archive: Path, *, max_bytes: int | None = None) -> None:
        with zipfile.ZipFile(archive, "w") as zipped:
            for path in FIXTURE.rglob("*"):
                if path.is_file():
                    zipped.write(
                        path,
                        arcname=f"echo-tool/{path.relative_to(FIXTURE).as_posix()}",
                    )

    monkeypatch.setattr(module, "download", download)


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
    mock_market_install(monkeypatch)
    manager.install_from_market("echo-tool")
    manager.set_enabled("echo-tool", False)
    manager.install_from_market("echo-tool", force=True)
    assert manager.global_enabled_map()["echo-tool"] is False
    assert PluginRegistry().get("echo-tool") is None


async def test_market_install_persists_enabled_and_preserves_settings(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "config.json"
    settings = {"database": {"backend": "sqlite"}, "plugins": {"other": {"enabled": False}}}
    config.write_text(json.dumps(settings), encoding="utf-8")
    mock_market_install(monkeypatch)
    await manager.install_async("install_from_market", "echo-tool")
    settings["plugins"]["echo-tool"] = {"enabled": True}
    assert json.loads(config.read_text(encoding="utf-8")) == settings


@pytest.mark.parametrize("installed", [False, True])
async def test_market_config_failure_rolls_back(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installed: bool
) -> None:
    old = manager.install_path(FIXTURE) if installed else None
    dest = manager.plugins_dir / "echo-tool"
    previous = (dest / "main.py").read_bytes() if installed else None
    config = tmp_path / "config.json"
    corrupt = b"{broken config"
    config.write_bytes(corrupt)
    mock_market_install(monkeypatch)
    with pytest.raises(OctopError) as exc:
        await manager.install_async("install_from_market", "echo-tool", force=installed)
    assert exc.value.code is ErrorCode.CONFIG_FILE_CORRUPT
    assert config.read_bytes() == corrupt
    assert PluginRegistry().get("echo-tool") is old
    assert dest.exists() is installed
    if installed:
        assert (dest / "main.py").read_bytes() == previous


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


async def test_prepare_reload_skips_broken_plugins_and_continues(
    manager: PluginManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins_dir = manager.plugins_dir
    malformed = plugins_dir / "01-malformed"
    malformed.mkdir(parents=True)
    (malformed / "plugin.yaml").write_text("id: [invalid", encoding="utf-8")
    failed = plugins_dir / "02-failed-dependencies"
    shutil.copytree(FIXTURE, failed)
    healthy = plugins_dir / "03-healthy"
    shutil.copytree(FIXTURE, healthy)
    prepared: list[Path] = []

    def prepare_dependencies(path: Path) -> None:
        prepared.append(path)
        if path == failed:
            raise RuntimeError("pip failed")

    monkeypatch.setattr(module, "install_dependencies", prepare_dependencies)

    await manager.prepare_reload()

    assert prepared == [failed, healthy]


@pytest.mark.parametrize(
    "requirement",
    ["--index-url=https://example.org/simple", "invalid requirement !!!"],
)
def test_plugin_manifest_requirements_must_be_pep508(
    manager: PluginManager,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requirement: str,
) -> None:
    source = tmp_path / "with-invalid-requirement"
    shutil.copytree(FIXTURE, source)
    manifest = source / "plugin.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + f'\nrequires:\n  - "{requirement}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        installation.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("pip must not run"),
    )

    with pytest.raises(ValueError, match="invalid plugin requirement"):
        installation.install_dependencies(source)
