from __future__ import annotations

import json
from pathlib import Path

import pytest

import octop.infra.market.http as market_http
from octop.infra.agents.plugins.bundled import default_bundled_plugins_root
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.agents.plugins.seed import seed_bundled_plugins
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.market import PortalMarketError, clear_market_cache


def _catalog_ids() -> set[str]:
    root = default_bundled_plugins_root()
    found: set[str] = set()
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if (child / "plugin.yaml").is_file():
            found.add(child.name)
    return found


def test_bundled_plugin_dirs_have_manifest_and_ui() -> None:
    root = default_bundled_plugins_root()
    found = _catalog_ids()
    assert found, "expected at least one catalog plugin"
    for name in found:
        child = root / name
        assert (child / "main.py").is_file(), child
        assert (child / "ui" / "index.js").is_file(), child
        assert (child / "ui" / "manifest.json").is_file(), child


def test_seed_does_not_auto_install_real_catalog(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    config_path = tmp_path / "config.json"
    copied = seed_bundled_plugins(
        bundled_root=default_bundled_plugins_root(),
        plugins_dir=plugins_dir,
        config_path=config_path,
    )
    assert copied == []
    assert list(plugins_dir.iterdir()) == [] if plugins_dir.exists() else True


def test_install_path_copies_bundled_plugin(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    config_path = tmp_path / "config.json"
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=config_path)
    sample = next(
        path
        for path in default_bundled_plugins_root().iterdir()
        if (path / "plugin.yaml").is_file()
    )
    loaded = mgr.install_path(sample)
    assert loaded.manifest.id == sample.name
    assert (plugins_dir / sample.name / "plugin.yaml").is_file()


def test_list_market_does_not_fall_back_to_bundled_plugins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "")
    clear_market_cache()
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=tmp_path / "config.json")
    with pytest.raises(OctopError) as raised:
        mgr.list_market()
    assert raised.value.code is ErrorCode.PLUGIN_MARKET_FAILED


def test_list_market_network_failure_is_not_a_market_outage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "https://octop.cloud")
    clear_market_cache()

    def fake_fetch(url: str, *, limit: int) -> bytes:
        del url, limit
        raise PortalMarketError("unreachable: down", network=True)

    monkeypatch.setattr(market_http, "fetch_bytes", fake_fetch)
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=tmp_path / "config.json")
    with pytest.raises(OctopError) as raised:
        mgr.list_market()
    assert raised.value.code is ErrorCode.NETWORK_ERROR


def test_install_from_market_does_not_copy_bundled_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_PORTAL_URL", "https://octop.cloud")
    clear_market_cache()

    def fake_fetch(url: str, *, limit: int) -> bytes:
        del url, limit
        return json.dumps({"success": True, "data": {"items": []}}).encode()

    monkeypatch.setattr(market_http, "fetch_bytes", fake_fetch)
    plugins_dir = tmp_path / "plugins"
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=tmp_path / "config.json")
    with pytest.raises(OctopError) as raised:
        mgr.install_from_market("fortune")
    assert raised.value.code is ErrorCode.NOT_FOUND
    assert not (plugins_dir / "fortune").exists()


def test_offline_bundled_plugins_load() -> None:
    from octop_harness.plugins import PluginRegistry, load_plugin_dir

    PluginRegistry.reset()
    root = default_bundled_plugins_root()
    try:
        for name in ("fortune", "pomodoro", "mini-games", "qrcode", "tetris"):
            loaded = load_plugin_dir(root / name, install_deps=False)
            assert loaded.manifest.id == name
            assert loaded.tools
    finally:
        PluginRegistry.reset()
