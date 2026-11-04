"""Plugins shared through the database, with a per-process import cache."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.agents.plugins.manager import PLUGINS_ENABLED, PLUGINS_REVISION, PluginManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.control_files import ControlFileRepo
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout


def _services(tmp_path: Path):
    from octop.config import OctopConfig

    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


def _plugin(root: Path, plugin_id: str, body: str) -> None:
    dest = root / plugin_id
    dest.mkdir(parents=True)
    (dest / "plugin.yaml").write_bytes(body.encode("utf-8"))


def test_plugin_cache_keeps_nested_directories(tmp_path: Path) -> None:
    services = _services(tmp_path)
    home_a = tmp_path / "a"
    home_b = tmp_path / "b"
    _plugin(home_a / "plugins", "demo", "id: demo\n")
    nested = home_a / "plugins" / "demo" / "skills" / "weather"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_bytes(b"# weather\n")
    manager_a = PluginManager(plugins_dir=home_a / "plugins", config_path=home_a / "config.json")
    manager_b = PluginManager(plugins_dir=home_b / "plugins", config_path=home_b / "config.json")
    manager_a.attach_control_plane(services.control_file_repo, services.settings_repo)
    manager_b.attach_control_plane(services.control_file_repo, services.settings_repo)

    copied = home_b / "plugins" / "demo" / "skills" / "weather" / "SKILL.md"
    assert copied.read_text(encoding="utf-8") == "# weather\n"


def test_attach_adopts_local_plugins_and_flags_once(tmp_path: Path) -> None:
    services = _services(tmp_path)
    home_a = tmp_path / "a"
    home_b = tmp_path / "b"
    _plugin(home_a / "plugins", "demo", "id: demo\n")
    (home_a / "config.json").write_text(
        json.dumps({"plugins": {"demo": {"enabled": False}}}),
        encoding="utf-8",
    )
    manager_a = PluginManager(plugins_dir=home_a / "plugins", config_path=home_a / "config.json")
    manager_a.attach_control_plane(services.control_file_repo, services.settings_repo)

    assert (
        services.control_file_repo.get(ControlFileRepo.PLUGIN, "demo", "plugin.yaml")
        == b"id: demo\n"
    )
    assert json.loads(services.settings_repo.get(PLUGINS_ENABLED) or "{}") == {"demo": False}
    assert services.settings_repo.get(PLUGINS_REVISION) == "1"

    _plugin(home_b / "plugins", "demo", "id: stale\n")
    _plugin(home_b / "plugins", "extra", "id: extra\n")
    (home_b / "config.json").write_text(
        json.dumps({"plugins": {"demo": {"enabled": True}, "extra": {"enabled": True}}}),
        encoding="utf-8",
    )
    manager_b = PluginManager(plugins_dir=home_b / "plugins", config_path=home_b / "config.json")
    manager_b.attach_control_plane(services.control_file_repo, services.settings_repo)

    stored = services.control_file_repo.get(ControlFileRepo.PLUGIN, "demo", "plugin.yaml")
    assert stored == b"id: demo\n"
    assert services.control_file_repo.has_owner(ControlFileRepo.PLUGIN, "extra") is False
    assert json.loads(services.settings_repo.get(PLUGINS_ENABLED) or "{}") == {"demo": False}
    copied = (home_b / "plugins" / "demo" / "plugin.yaml").read_text(encoding="utf-8")
    assert copied == "id: demo\n"
    assert not (home_b / "plugins" / "extra").exists()


def test_uninstall_drops_the_plugin_from_the_other_cache(tmp_path: Path) -> None:
    services = _services(tmp_path)
    home_a = tmp_path / "a"
    home_b = tmp_path / "b"
    _plugin(home_a / "plugins", "demo", "id: demo\n")
    manager_a = PluginManager(plugins_dir=home_a / "plugins", config_path=home_a / "config.json")
    manager_b = PluginManager(plugins_dir=home_b / "plugins", config_path=home_b / "config.json")
    manager_a.attach_control_plane(services.control_file_repo, services.settings_repo)
    manager_b.attach_control_plane(services.control_file_repo, services.settings_repo)
    assert (home_b / "plugins" / "demo" / "plugin.yaml").is_file()

    manager_a.uninstall("demo")

    manager_b.list_installed()
    assert services.control_file_repo.has_owner(ControlFileRepo.PLUGIN, "demo") is False
    assert not (home_b / "plugins" / "demo").exists()


def test_install_on_one_process_materializes_on_another(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "fixtures" / "plugins" / "echo-tool"
    services = _services(tmp_path)
    home_a = tmp_path / "a"
    home_b = tmp_path / "b"
    manager_a = PluginManager(plugins_dir=home_a / "plugins", config_path=home_a / "config.json")
    manager_b = PluginManager(plugins_dir=home_b / "plugins", config_path=home_b / "config.json")
    manager_a.attach_control_plane(services.control_file_repo, services.settings_repo)
    manager_b.attach_control_plane(services.control_file_repo, services.settings_repo)

    manager_a.install_path(source)

    manager_b.list_installed()
    copied = (home_b / "plugins" / "echo-tool" / "plugin.yaml").read_text(encoding="utf-8")
    assert "id: echo-tool" in copied
    assert services.settings_repo.get(PLUGINS_REVISION) not in {None, "0"}
