"""Plugins that carry system configuration (the ``config`` capability)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from octop_harness.plugins import PluginRegistry

from octop.config import OctopConfig
from octop.infra.agents.plugins.manager import PluginManager, check_plugin_compatible
from octop.infra.agents.plugins.plugin_config import (
    apply_plugin_models,
    apply_plugin_settings,
    parse_plugin_config,
    replace_plugin_presets,
)
from octop.infra.agents.providers.presets import load_provider_presets
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.utils.paths import PathLayout
from tests.support.app import ensure_control_plane_bound

_ECHO = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"

_PRESET = {
    "id": "acme",
    "name": "Acme Cloud",
    "base_url": "https://api.acme.example/v1",
    "protocol": "openai",
    "models": [{"id": "acme-large", "name": "Acme Large", "enabled": True, "input": ["text"]}],
}


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    PluginRegistry.reset()
    replace_plugin_presets({})
    yield
    replace_plugin_presets({})
    PluginRegistry.reset()


def _write_plugin(root: Path, config: dict[str, Any] | None, *, version: str = "1.0.0") -> Path:
    plugin_dir = root / "acme-cloud"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"id": "acme-cloud", "version": version, "capabilities": ["config"]}
    if config is not None:
        manifest["config"] = config
    (plugin_dir / "plugin.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "main.py").write_text("def setup(ctx):\n    pass\n", encoding="utf-8")
    return plugin_dir


def _full_config() -> dict[str, Any]:
    return {
        "provider_presets": [_PRESET],
        "providers": [{"preset": "acme", "name": "acme"}],
        "default_model": "acme/acme-large",
        "settings": {"default_timezone": "Europe/Berlin", "max_upload_mb": 64},
    }


def _manager(tmp_path: Path) -> PluginManager:
    config_path = tmp_path / "config.json"
    if not config_path.exists():
        config_path.write_text("{}", encoding="utf-8")
    return PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)


# ── parsing ──────────────────────────────────────────────────────────────────


def test_plugins_without_the_capability_have_no_config(tmp_path: Path) -> None:
    assert parse_plugin_config(_ECHO) is None
    cfg = parse_plugin_config(_write_plugin(tmp_path, _full_config()))
    assert cfg is not None
    assert cfg.summary() == {
        "provider_presets": ["acme"],
        "providers": ["acme"],
        "default_model": "acme/acme-large",
        "settings": {"default_timezone": "Europe/Berlin", "max_upload_mb": 64},
    }


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (None, "non-empty mapping"),
        ({"themes": {}}, "unknown keys: themes"),
        ({"settings": {"port": 9000}}, "'port' cannot be set"),
        ({"settings": {"database": {"driver": "postgresql"}}}, "'database' cannot be set"),
        ({"settings": {"max_upload_mb": "64"}}, "must be int"),
        ({"settings": {"max_upload_mb": True}}, "must be int"),
        ({"default_model": "acme"}, "provider/model"),
        ({"providers": [{"name": "acme"}]}, "needs a preset"),
        ({"provider_presets": [{"name": "no id"}]}, "needs an id"),
    ],
)
def test_invalid_config_is_refused(tmp_path: Path, config: Any, message: str) -> None:
    with pytest.raises(OctopError, match=message) as ei:
        check_plugin_compatible(_write_plugin(tmp_path, config))
    assert ei.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE


def test_unknown_capability_and_octop_version(tmp_path: Path) -> None:
    plugin_dir = _write_plugin(tmp_path, _full_config())
    manifest = json.loads((plugin_dir / "plugin.yaml").read_text(encoding="utf-8"))
    for extra, message in (
        ({"capabilities": ["config", "theme"]}, "unsupported plugin capabilities: theme"),
        ({"octop": ">=999"}, "requires Octop"),
        ({"octop": "soon"}, "invalid octop version"),
    ):
        (plugin_dir / "plugin.yaml").write_text(json.dumps({**manifest, **extra}), encoding="utf-8")
        with pytest.raises(OctopError, match=message):
            check_plugin_compatible(plugin_dir)


# ── provider presets ─────────────────────────────────────────────────────────


def test_presets_follow_the_plugin_lifecycle(tmp_path: Path) -> None:
    ollama_shadow = {**_PRESET, "id": "ollama", "name": "Not Ollama"}
    config = {**_full_config(), "provider_presets": [_PRESET, ollama_shadow]}
    src = _write_plugin(tmp_path / "src", config)
    mgr = _manager(tmp_path)

    mgr.install_path(src)
    presets = load_provider_presets()
    assert presets[0]["id"] == "acme"
    assert [p["name"] for p in presets if p["id"] == "ollama"] != ["Not Ollama"]
    row = next(item for item in mgr.list_installed() if item["id"] == "acme-cloud")
    assert row["capabilities"] == ["config"]
    assert row["config"]["providers"] == ["acme"]

    mgr.set_enabled("acme-cloud", False)
    assert all(p["id"] != "acme" for p in load_provider_presets())
    mgr.set_enabled("acme-cloud", True)
    assert load_provider_presets()[0]["id"] == "acme"
    mgr.uninstall("acme-cloud")
    assert all(p["id"] != "acme" for p in load_provider_presets())


# ── settings ─────────────────────────────────────────────────────────────────


def _config_json(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))


def test_settings_fill_defaults_once_per_version(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"max_upload_mb": 10}), encoding="utf-8")
    cfg = parse_plugin_config(_write_plugin(tmp_path / "p", _full_config()))
    assert cfg is not None

    written = apply_plugin_settings(config_path, [cfg])
    # The admin already chose an upload limit; only the untouched timezone changes.
    assert written == ["acme-cloud.default_timezone"]
    data = _config_json(tmp_path)
    assert data["default_timezone"] == "Europe/Berlin"
    assert data["max_upload_mb"] == 10

    # The admin moves the timezone back to Octop's default: the plugin leaves it.
    data["default_timezone"] = OctopConfig().default_timezone
    config_path.write_text(json.dumps(data), encoding="utf-8")
    assert apply_plugin_settings(config_path, [cfg]) == []
    assert _config_json(tmp_path)["default_timezone"] == OctopConfig().default_timezone

    # A new plugin version applies again, still only over default values.
    newer = parse_plugin_config(_write_plugin(tmp_path / "p", _full_config(), version="1.1.0"))
    assert newer is not None
    assert apply_plugin_settings(config_path, [newer]) == ["acme-cloud.default_timezone"]


# ── providers and default model ──────────────────────────────────────────────


@pytest.fixture
def services(tmp_path: Path) -> Any:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    svc = build_shared_services(db=db, paths=paths, config=OctopConfig())
    yield svc
    db.close()


def test_providers_and_default_model_only_where_unset(tmp_path: Path, services: Any) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cfg = parse_plugin_config(_write_plugin(tmp_path / "p", _full_config()))
    assert cfg is not None

    def apply() -> list[str]:
        return apply_plugin_models(
            config_path,
            [cfg],
            provider_repo=services.provider_repo,
            settings_repo=services.settings_repo,
            presets_by_id=lambda: {"acme": _PRESET},
        )

    assert apply() == ["acme", "default_model"]
    row = services.provider_repo.get_by_name("acme")
    assert row.kind == "openai"
    assert row.base_url == _PRESET["base_url"]
    assert not row.api_key
    assert json.loads(row.models_json)[0]["id"] == "acme-large"
    assert services.settings_repo.get_active_model() == ("acme", "acme-large")
    # Applied once per version: deleting the provider does not bring it back.
    services.provider_repo.delete(row.id)
    assert apply() == []


def test_existing_provider_and_default_model_are_kept(tmp_path: Path, services: Any) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    services.provider_repo.create(name="acme", kind="anthropic", base_url="https://mine")
    services.settings_repo.set_active_model("mine", "m1")
    cfg = parse_plugin_config(_write_plugin(tmp_path / "p", _full_config()))
    assert cfg is not None

    done = apply_plugin_models(
        config_path,
        [cfg],
        provider_repo=services.provider_repo,
        settings_repo=services.settings_repo,
        presets_by_id=lambda: {"acme": _PRESET},
    )
    assert done == []
    assert services.provider_repo.get_by_name("acme").base_url == "https://mine"
    assert services.settings_repo.get_active_model() == ("mine", "m1")


# ── startup ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_preinstalled_plugin_configures_the_first_boot(tmp_path: Path) -> None:
    _write_plugin(tmp_path / "plugins", _full_config())
    server = OctopServer(home=tmp_path)
    await server.start()
    await ensure_control_plane_bound(server)
    try:
        # Settings land before the config is read, so they apply on this boot.
        assert server.config is not None
        assert server.config.default_timezone == "Europe/Berlin"
        assert server.config.max_upload_mb == 64
        assert server.services is not None
        assert server.services.provider_repo.get_by_name("acme") is not None
        assert server.services.settings_repo.get_active_model() == ("acme", "acme-large")
        assert load_provider_presets()[0]["id"] == "acme"
    finally:
        await server.stop()
    marks = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["plugins"]
    assert marks["acme-cloud"]["config_settings_applied"] == "1.0.0"
    assert marks["acme-cloud"]["config_models_applied"] == "1.0.0"


def test_copying_the_echo_fixture_still_installs(tmp_path: Path) -> None:
    src = tmp_path / "src" / "echo-tool"
    shutil.copytree(_ECHO, src)
    loaded = _manager(tmp_path).install_path(src)
    assert loaded.manifest.id == "echo-tool"
    row = next(item for item in _manager(tmp_path).list_installed() if item["id"] == "echo-tool")
    assert row["capabilities"] == ["tool"]
    assert row["config"] is None
