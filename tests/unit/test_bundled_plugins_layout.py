"""Bundled plugin tree must be complete enough to seed and render UI."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root
from octop.infra.agents.plugins.seed import seed_bundled_plugins

_EXPECTED = frozenset(
    {
        "bilibili-anime",
        "server-status",
        "weather",
        "hot-topics",
        "fortune",
        "pomodoro",
        "market-quotes",
        "mini-games",
        "tetris",
        "parcel-tracker",
        "qrcode",
    },
)


def test_bundled_plugin_dirs_have_manifest_and_ui() -> None:
    root = default_bundled_plugins_root()
    found: set[str] = set()
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "plugin.yaml").is_file():
            continue
        found.add(child.name)
        assert (child / "main.py").is_file(), child
        assert (child / "ui" / "index.js").is_file(), child
        assert (child / "ui" / "manifest.json").is_file(), child
    assert found == _EXPECTED


def test_seed_real_bundled_plugins_are_disabled(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    config_path = tmp_path / "config.json"
    copied = seed_bundled_plugins(
        bundled_root=default_bundled_plugins_root(),
        plugins_dir=plugins_dir,
        config_path=config_path,
    )
    assert set(copied) == _EXPECTED
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    for plugin_id in _EXPECTED:
        assert raw["plugins"][plugin_id]["enabled"] is False
        assert (plugins_dir / plugin_id / "plugin.yaml").is_file()
        assert (plugins_dir / plugin_id / "ui" / "index.js").is_file()


def test_offline_bundled_plugins_load() -> None:
    from harness_agent.plugins import PluginRegistry, load_plugin_dir

    PluginRegistry.reset()
    root = default_bundled_plugins_root()
    try:
        for name in ("fortune", "pomodoro", "mini-games", "qrcode", "tetris"):
            loaded = load_plugin_dir(root / name, install_deps=False)
            assert loaded.manifest.id == name
            assert loaded.tools
    finally:
        PluginRegistry.reset()
