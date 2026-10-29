"""``plugins/simple-theme`` must stay installable, buildable and attributed."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from octop_harness.plugins import PluginManifest, PluginRegistry, load_plugin_dir

_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "simple-theme"


def _load_main() -> object:
    spec = importlib.util.spec_from_file_location("_simple_theme_main", _PLUGIN_DIR / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_declares_theme_plugin_and_ui() -> None:
    manifest = PluginManifest.load(_PLUGIN_DIR / "plugin.yaml")
    assert manifest.id == "simple-theme"
    assert manifest.version == "1.0.4"
    assert manifest.kind == "tool"
    assert manifest.name == "简单主题"
    assert (_PLUGIN_DIR / "ui" / "index.js").is_file()
    assert (_PLUGIN_DIR / "ui" / "manifest.json").is_file()


def test_plugin_loads_and_registers_status_tool() -> None:
    PluginRegistry.reset()
    try:
        loaded = load_plugin_dir(_PLUGIN_DIR, install_deps=False)
        assert loaded.manifest.id == "simple-theme"
        assert [tool.name for tool in loaded.tools] == ["simple_theme_info"]
    finally:
        PluginRegistry.reset()


def test_status_tool_returns_theme_card_payload() -> None:
    module = _load_main()
    payload = json.loads(asyncio.run(module.simple_theme_info()))  # type: ignore[attr-defined]
    assert payload["octop_ui"] == {"renderer": "theme_card", "version": 1}
    assert payload["data"]["version"] == "1.0.4"
    assert payload["text"]


def test_plugin_does_not_patch_dashboard_fallback() -> None:
    from octop.api import app as app_module

    original = app_module._dashboard_fallback
    PluginRegistry.reset()
    try:
        load_plugin_dir(_PLUGIN_DIR, install_deps=False)
        assert app_module._dashboard_fallback is original
    finally:
        PluginRegistry.reset()


def test_built_bundle_renders_model_as_read_only_status() -> None:
    """The native composer menu stays the only model switch; the dock is a status."""
    bundle = (_PLUGIN_DIR / "ui" / "index.js").read_text(encoding="utf-8")
    assert 'role="status" aria-live="polite"' in bundle
    assert "simple-model-trigger" not in bundle
    assert "simple-model-remove" not in bundle
    assert "自动选择" in bundle
    assert "composer-plus" not in bundle
    css = (_PLUGIN_DIR / "ui" / "theme.css").read_text(encoding="utf-8")
    assert ".simple-model-name {min-width:0" in css
    assert "max-width:100%" in css
    assert "max-width:calc(100vw - 24px)" in css


def test_built_bundle_contains_current_css() -> None:
    """``build.py`` inlines ``theme.css`` (backslash-escaped) into ``index.js``."""
    css = (_PLUGIN_DIR / "ui" / "theme.css").read_text(encoding="utf-8").strip()
    bundle = (_PLUGIN_DIR / "ui" / "index.js").read_text(encoding="utf-8")
    assert "const CSS = `" in bundle
    assert css.replace("\\", "\\\\") in bundle


def test_third_party_licenses_are_shipped() -> None:
    licenses = _PLUGIN_DIR / "LICENSES"
    ofl = (licenses / "Inter-OFL-1.1.txt").read_text(encoding="utf-8")
    mit = (licenses / "LobeHub-icons-MIT.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in ofl
    assert "The Inter Project Authors" in ofl
    assert "MIT License" in mit
    assert "LobeHub" in mit
    readme = (_PLUGIN_DIR / "README.md").read_text(encoding="utf-8")
    assert "LICENSES/README.md" in readme


@pytest.mark.parametrize("prefix", ["", "simple-theme/"])
def test_plugin_archive_installs_in_both_supported_layouts(tmp_path: Path, prefix: str) -> None:
    from octop.infra.agents.plugins.manager import PluginManager

    archive = tmp_path / "simple-theme.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in _PLUGIN_DIR.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, prefix + path.relative_to(_PLUGIN_DIR).as_posix())
    manager = PluginManager(
        plugins_dir=tmp_path / "installed", config_path=tmp_path / "config.json"
    )
    PluginRegistry.reset()
    try:
        loaded = manager.install_archive(archive)
        assert loaded.manifest.id == "simple-theme"
        assert [tool.name for tool in loaded.tools] == ["simple_theme_info"]
    finally:
        PluginRegistry.reset()
