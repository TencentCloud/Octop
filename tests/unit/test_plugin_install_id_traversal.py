"""Regression tests for unsafe plugin manifest ids (issue #1692).

``PluginManager.install_path()`` used to derive its destination straight from
``manifest.id``, so an archive declaring ``id: ../evil-plugin`` (or ``..`` with
``force=True``) could write — or delete — outside the plugins directory.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
from octop_harness.plugins import PluginRegistry

from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"

_UNSAFE_IDS = [
    "../evil-plugin",
    "nested/evil-plugin",
    "..",
    ".",
    "..\\evil-plugin",
    "/abs/evil-plugin",
    "C:evil-plugin",
]


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def _manager(tmp_path: Path) -> PluginManager:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    return PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)


def _source_with_id(tmp_path: Path, plugin_id: str) -> Path:
    source = tmp_path / "src"
    shutil.copytree(_FIXTURE, source)
    manifest = (source / "plugin.yaml").read_text(encoding="utf-8")
    (source / "plugin.yaml").write_text(
        manifest.replace("id: echo-tool", f"id: {plugin_id}"),
        encoding="utf-8",
    )
    return source


@pytest.mark.parametrize("plugin_id", _UNSAFE_IDS)
def test_install_path_rejects_unsafe_manifest_id(tmp_path: Path, plugin_id: str) -> None:
    mgr = _manager(tmp_path)
    source = _source_with_id(tmp_path, plugin_id)

    with pytest.raises(OctopError) as excinfo:
        mgr.install_path(source, force=True)

    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    assert excinfo.value.status == 400
    # Nothing was written above the plugins directory.
    assert not (tmp_path / "evil-plugin").exists()
    assert not (tmp_path / "nested").exists()


def test_install_path_dot_id_does_not_wipe_plugins_dir(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    plugins_dir = tmp_path / "plugins"
    (plugins_dir / "keep").mkdir(parents=True)
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=config_path)
    source = _source_with_id(tmp_path, ".")

    with pytest.raises(OctopError) as excinfo:
        mgr.install_path(source, force=True)

    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    assert (plugins_dir / "keep").is_dir()


def test_install_archive_rejects_unsafe_manifest_id(tmp_path: Path) -> None:
    mgr = _manager(tmp_path)
    source = _source_with_id(tmp_path, "../evil-plugin")
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in source.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=f"evil/{path.relative_to(source).as_posix()}")

    with pytest.raises(OctopError) as excinfo:
        mgr.install_archive(archive, force=True)

    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    assert not (tmp_path / "evil-plugin").exists()


def test_plugin_dir_rejects_traversal_id(tmp_path: Path) -> None:
    # A manifest one level above plugins_dir would satisfy the old lookup.
    (tmp_path / "plugin.yaml").write_text("id: parent\nversion: 0.1.0\n", encoding="utf-8")
    mgr = _manager(tmp_path)

    assert mgr.plugin_dir("..") is None
    assert mgr.plugin_dir("../evil-plugin") is None
    assert mgr.plugin_dir(".") is None
    assert mgr.plugin_dir("") is None


def test_resolve_ui_file_rejects_traversal_id(tmp_path: Path) -> None:
    (tmp_path / "plugin.yaml").write_text("id: parent\nversion: 0.1.0\n", encoding="utf-8")
    mgr = _manager(tmp_path)

    with pytest.raises(OctopError) as excinfo:
        mgr.resolve_ui_file("..", "plugin.yaml")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_uninstall_rejects_traversal_id(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=config_path)

    with pytest.raises(OctopError) as excinfo:
        mgr.uninstall("..")

    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    assert sentinel.is_file()
    assert plugins_dir.is_dir()
