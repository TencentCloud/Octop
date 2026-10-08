"""Plugin IDs must not select paths outside a single plugin directory."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from octop_harness.plugins import PluginRegistry

from octop.infra.agents.plugins import manager as plugin_manager
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"
_INVALID_IDS = [
    ".",
    "..",
    "../outside",
    "nested/plugin",
    "..\\outside",
    "nested\\plugin",
    "C:outside",
    "C:\\outside",
    "absolute-path",
    ". ",
    "bad\x00id",
]


@pytest.fixture(autouse=True)
def _reset_registry() -> Iterator[None]:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PluginManager:
    home = tmp_path / "octop"
    monkeypatch.setenv("OCTOP_HOME", str(home))
    mgr = PluginManager(plugins_dir=home / "plugins", config_path=home / "config.json")
    (home / "config.json").write_text("{}", encoding="utf-8")
    return mgr


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return Path(shutil.copytree(_FIXTURE, tmp_path / "source"))


def _set_id(source: Path, plugin_id: str) -> None:
    manifest = source / "plugin.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["id"] = plugin_id
    manifest.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.mark.parametrize("plugin_id", _INVALID_IDS)
@pytest.mark.parametrize("force", [False, True])
def test_invalid_install_id_is_rejected_before_filesystem_or_registry_changes(
    manager: PluginManager,
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plugin_id: str,
    force: bool,
) -> None:
    if plugin_id == "absolute-path":
        plugin_id = str(tmp_path / "outside")
    _set_id(source, plugin_id)
    # Keep even the unfixed code safe to run: no real copy, removal, or plugin execution.
    copy = Mock()
    remove = Mock()
    unload = Mock()
    load = Mock()
    monkeypatch.setattr(plugin_manager, "shutil", SimpleNamespace(copytree=copy, rmtree=remove))
    monkeypatch.setattr(plugin_manager, "unload_plugin", unload)
    monkeypatch.setattr(plugin_manager, "_load_plugin_dir", load)

    with pytest.raises(OctopError) as excinfo:
        manager.install_path(source, force=force)

    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    copy.assert_not_called()
    remove.assert_not_called()
    unload.assert_not_called()
    load.assert_not_called()
    assert (manager.plugins_dir.parent / "config.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("plugin_id", [".", "..", "../outside", "nested/plugin", "absolute-path"])
def test_invalid_lookup_id_cannot_expose_files(
    manager: PluginManager, tmp_path: Path, plugin_id: str
) -> None:
    if plugin_id == "absolute-path":
        plugin_id = str(tmp_path / "outside")
    target = manager.plugins_dir / plugin_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "plugin.yaml").write_text("id: outside\nversion: 1.0.0\n", encoding="utf-8")
    (target / "private.txt").write_text("private", encoding="utf-8")

    assert manager.plugin_dir(plugin_id) is None
    with pytest.raises(OctopError) as excinfo:
        manager.resolve_ui_file(plugin_id, "private.txt")
    assert excinfo.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(OctopError) as excinfo:
        manager.set_enabled(plugin_id, False)
    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert (manager.plugins_dir.parent / "config.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("plugin_id", _INVALID_IDS)
def test_invalid_uninstall_id_cannot_delete_files_or_unload_plugins(
    manager: PluginManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plugin_id: str
) -> None:
    if plugin_id == "absolute-path":
        plugin_id = str(tmp_path / "outside")
    remove = Mock()
    unload = Mock()
    monkeypatch.setattr(plugin_manager, "shutil", SimpleNamespace(rmtree=remove))
    monkeypatch.setattr(plugin_manager, "unload_plugin", unload)

    with pytest.raises(OctopError) as excinfo:
        manager.uninstall(plugin_id)

    assert excinfo.value.code is ErrorCode.NOT_FOUND
    remove.assert_not_called()
    unload.assert_not_called()


@pytest.mark.parametrize("plugin_id", ["echo-tool", "echo_tool", "echo.v1", "自定义插件"])
def test_valid_ids_still_support_install_lookup_overwrite_and_uninstall(
    manager: PluginManager, source: Path, plugin_id: str
) -> None:
    _set_id(source, plugin_id)
    loaded = manager.install_path(source)
    dest = manager.plugins_dir / plugin_id
    assert loaded.manifest.id == plugin_id
    assert manager.plugin_dir(plugin_id) == dest
    assert manager.resolve_ui_file(plugin_id, "plugin.yaml") == dest / "plugin.yaml"

    (source / "updated.txt").write_text("updated", encoding="utf-8")
    manager.install_path(source, force=True)
    assert (dest / "updated.txt").read_text(encoding="utf-8") == "updated"

    manager.uninstall(plugin_id)
    assert not dest.exists()
    assert PluginRegistry().get(plugin_id) is None


def test_uninstall_missing_valid_id_remains_a_noop(manager: PluginManager) -> None:
    manager.uninstall("missing-plugin")
    assert manager.plugins_dir.is_dir()
