"""Discover and load plugins from directories."""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.plugins.context import PluginContext, register_loaded
from octop_harness.plugins.manifest import PluginManifest
from octop_harness.plugins.registry import LoadedPlugin, PluginRegistry

logger = logging.getLogger(__name__)


def discover_plugin_dirs(plugins_root: Path) -> list[Path]:
    if not plugins_root.is_dir():
        return []
    out: list[Path] = []
    for item in sorted(plugins_root.iterdir()):
        if item.is_dir() and (item / "plugin.yaml").is_file():
            out.append(item)
    return out


def _install_requires(plugin_dir: Path, requires: tuple[str, ...]) -> None:
    req_file = plugin_dir / "requirements.txt"
    if req_file.is_file():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            check=False,
            capture_output=True,
        )
    if requires:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *requires],
            check=False,
            capture_output=True,
        )


def load_plugin_dir(
    plugin_dir: Path,
    *,
    install_deps: bool = True,
) -> LoadedPlugin:
    manifest = PluginManifest.load(plugin_dir / "plugin.yaml")
    entry_path = plugin_dir / manifest.entry
    if not entry_path.is_file():
        raise FileNotFoundError(f"plugin entry not found: {entry_path}")

    if install_deps and (manifest.requires or (plugin_dir / "requirements.txt").is_file()):
        _install_requires(plugin_dir, manifest.requires)

    safe_id = manifest.id.replace("-", "_")
    module_name = f"harness_plugin_{safe_id}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        entry_path,
        submodule_search_locations=[str(plugin_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin entry: {entry_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    module.__package__ = module_name
    module.__path__ = [str(plugin_dir)]
    loaded = False
    try:
        spec.loader.exec_module(module)
        loaded = True
    finally:
        if not loaded:
            sys.modules.pop(module_name, None)

    ctx = PluginContext(manifest=manifest, source_path=plugin_dir)
    setup = getattr(module, "setup", None)
    if not callable(setup):
        raise AttributeError(f"plugin entry must define setup(ctx): {entry_path}")
    setup(ctx)
    return register_loaded(ctx)


def load_all(plugins_root: Path, *, install_deps: bool = True) -> list[LoadedPlugin]:
    registry = PluginRegistry()
    registry.clear()
    loaded: list[LoadedPlugin] = []
    for plugin_dir in discover_plugin_dirs(plugins_root):
        try:
            item = load_plugin_dir(plugin_dir, install_deps=install_deps)
            loaded.append(item)
            logger.info("loaded plugin %s v%s", item.manifest.id, item.manifest.version)
        except DEFENSIVE_OP_ERRORS as exc:
            logger.error("failed to load plugin from %s: %s", plugin_dir, exc, exc_info=True)
    return loaded


def unload_plugin(plugin_id: str) -> bool:
    registry = PluginRegistry()
    removed = registry.unregister(plugin_id)
    if removed is None:
        return False
    safe_id = plugin_id.replace("-", "_")
    module_name = f"harness_plugin_{safe_id}"
    sys.modules.pop(module_name, None)
    prefix = module_name + "."
    for key in list(sys.modules):
        if key.startswith(prefix):
            sys.modules.pop(key, None)
    return True
