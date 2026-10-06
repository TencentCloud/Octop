"""Regression: a plugin manifest ``id`` must not escape the plugins directory.

``PluginManager.install_path`` derives its destination as
``self._plugins_dir / manifest.id``. ``PluginManifest.from_dict`` only checks
that ``id`` is a non-empty string, so an archive whose ``plugin.yaml`` carries
``id: ../evil-plugin`` (or any other value containing a path separator) makes
``install_path`` write *outside* the plugins directory — and, with
``force=True``, ``shutil.rmtree`` an arbitrary directory first.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from octop_harness.plugins import PluginRegistry

from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"

# Values that must never be accepted as a plugin directory name.
_UNSAFE_IDS = [
    "../evil-plugin",
    "../../evil-plugin",
    "..\\evil-plugin",
    "nested/evil-plugin",
    "nested\\evil-plugin",
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
    """Copy the loadable echo-tool fixture, then rewrite its manifest id."""
    source = tmp_path / "source"
    shutil.copytree(_FIXTURE, source)
    (source / "plugin.yaml").write_text(
        f"id: {plugin_id}\nversion: 1.0.0\nname: Escaping Plugin\nkind: tool\nentry: main.py\n",
        encoding="utf-8",
    )
    return source


@pytest.mark.parametrize("bad_id", _UNSAFE_IDS)
def test_install_path_rejects_unsafe_plugin_id(tmp_path: Path, bad_id: str) -> None:
    mgr = _manager(tmp_path)
    source = _source_with_id(tmp_path, bad_id)

    with pytest.raises(OctopError) as excinfo:
        mgr.install_path(source, force=True)

    assert excinfo.value.code == ErrorCode.PLUGIN_INVALID_ARCHIVE, (
        f"id {bad_id!r} must be rejected as an invalid plugin id, got {excinfo.value.code}"
    )

    # Nothing may be created outside the plugins directory.
    assert not (tmp_path / "evil-plugin").exists()
    assert not (tmp_path / "nested").exists()


def test_install_path_rejects_parent_dir_id(tmp_path: Path) -> None:
    """``id: ..`` targets the plugins directory itself, not an existing plugin.

    Checked with ``force=False`` so the pre-fix code path cannot reach the
    ``shutil.rmtree`` that ``force=True`` would run on the parent directory.
    """
    mgr = _manager(tmp_path)
    source = _source_with_id(tmp_path, "..")

    with pytest.raises(OctopError) as excinfo:
        mgr.install_path(source, force=False)

    assert excinfo.value.code == ErrorCode.PLUGIN_INVALID_ARCHIVE


def test_plugin_dir_rejects_traversal_id(tmp_path: Path) -> None:
    """Lookup must not resolve outside the plugins directory either."""
    mgr = _manager(tmp_path)
    # A manifest one level above the plugins dir is reachable through "..".
    (tmp_path / "plugin.yaml").write_text(
        "id: ..\nversion: 1.0.0\nkind: tool\nentry: main.py\n", encoding="utf-8"
    )

    assert mgr.plugin_dir("..") is None
    assert mgr.plugin_dir("../") is None
    with pytest.raises(OctopError) as excinfo:
        mgr.resolve_ui_file("..", "plugin.yaml")
    assert excinfo.value.code == ErrorCode.NOT_FOUND


def test_install_path_accepts_safe_plugin_id(tmp_path: Path) -> None:
    """Positive control: a normal id still installs (guard must not over-reject)."""
    mgr = _manager(tmp_path)
    loaded = mgr.install_path(_FIXTURE, force=True)
    assert loaded.manifest.id == "echo-tool"
    assert (tmp_path / "plugins" / "echo-tool" / "plugin.yaml").is_file()
