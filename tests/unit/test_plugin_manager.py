"""Unit tests for Octop plugin manager."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from octop_harness.plugins import PluginRegistry

from octop.infra.agents.extensions.catalog import ExtensionCatalog
from octop.infra.agents.plugins.manager import (
    PluginManager,
    normalize_plugin_download_url,
    parse_plugin_group,
    parse_plugin_icon,
    parse_plugin_ui_meta,
)
from octop.infra.errors import ErrorCode, OctopError

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"


def _echo_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in _FIXTURE.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=f"echo-tool/{path.relative_to(_FIXTURE).as_posix()}")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def test_install_and_list(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    plugins_dir = tmp_path / "plugins"
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=config_path)
    loaded = mgr.install_path(_FIXTURE, force=True)
    assert loaded.manifest.id == "echo-tool"
    items = mgr.list_installed()
    assert any(i.get("id") == "echo-tool" for i in items)


def test_created_plugin_is_visible_only_to_owner_and_installable(tmp_path: Path) -> None:
    catalog_root = tmp_path / "extensions"
    ExtensionCatalog(catalog_root).publish(
        owner_user_id=7,
        project_id="01M51SZVMKP5XV917RJ24GQ7QX",
        artifact_type="plugin",
        slug="created-tool",
        goal="Return a supplied value.",
        created_at="2026-10-16T00:00:00+00:00",
        revision="a" * 64,
        sha256="b" * 64,
        files={
            "plugin.yaml": b"""id: created-tool
version: 0.1.0
name: Created Tool
description: Return a supplied value.
kind: tool
entry: main.py
requires: []
""",
            "main.py": b"""async def run(value: str) -> str:
    return value

def setup(ctx):
    ctx.tool(\"created_tool\", run, description=\"Return the value.\")
""",
        },
    )
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    manager = PluginManager(
        plugins_dir=tmp_path / "plugins",
        config_path=config_path,
        created_catalog_root=catalog_root,
    )

    owner_market = manager.list_market(owner_user_id=7)

    assert any(
        row.get("id") == "created-tool" and row.get("source") == "created" for row in owner_market
    )
    assert not any(row.get("id") == "created-tool" for row in manager.list_market(owner_user_id=8))
    loaded = manager.install_from_market("created-tool", owner_user_id=7)
    assert loaded.manifest.id == "created-tool"


def test_tool_plugin_can_declare_companion_skills(tmp_path: Path) -> None:
    source = tmp_path / "hybrid-tool"
    skill_dir = source / "skills" / "hybrid-tool"
    skill_dir.mkdir(parents=True)
    (source / "plugin.yaml").write_text(
        """id: hybrid-tool
version: 0.1.0
name: Hybrid Tool
kind: tool
entry: main.py
requires: []
skills: skills
""",
        encoding="utf-8",
    )
    (source / "main.py").write_text(
        """async def run(value: str) -> str:
    return value

def setup(ctx):
    ctx.tool("hybrid_tool", run, description="Return the value.")
""",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hybrid-tool\ndescription: Use the hybrid tool.\n---\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    manager = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)

    loaded = manager.install_path(source, force=True)

    assert loaded.skills_dir == tmp_path / "plugins" / "hybrid-tool" / "skills"
    assert manager.plugin_skill_names("hybrid-tool") == {"hybrid-tool"}


def test_plugin_companion_skills_path_cannot_escape_plugin(tmp_path: Path) -> None:
    source = tmp_path / "unsafe-hybrid"
    source.mkdir()
    (source / "plugin.yaml").write_text(
        """id: unsafe-hybrid
version: 0.1.0
name: Unsafe Hybrid
kind: tool
entry: main.py
skills: ../skills
""",
        encoding="utf-8",
    )
    (source / "main.py").write_text("def setup(ctx):\n    pass\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    manager = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)

    with pytest.raises(OctopError) as excinfo:
        manager.install_path(source, force=True)

    assert excinfo.value.code is ErrorCode.PLUGIN_INSTALL_FAILED
    assert "safe relative directory" in str(excinfo.value)


def test_global_disable(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"plugins": {"echo-tool": {"enabled": False}}}),
        encoding="utf-8",
    )
    plugins_dir = tmp_path / "plugins"
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=config_path)
    mgr.install_path(_FIXTURE, force=True)
    loaded = mgr.load_installed(install_deps=False)
    assert loaded == []


def test_set_enabled_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    mgr.install_path(_FIXTURE, force=True)
    assert any(i.get("id") == "echo-tool" and i.get("enabled") for i in mgr.list_installed())

    disabled = mgr.set_enabled("echo-tool", False)
    assert disabled.get("enabled") is False
    assert disabled.get("loaded") is False
    assert PluginRegistry().get("echo-tool") is None
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["plugins"]["echo-tool"]["enabled"] is False

    enabled = mgr.set_enabled("echo-tool", True)
    assert enabled.get("enabled") is True
    assert enabled.get("loaded") is True
    assert PluginRegistry().get("echo-tool") is not None


def test_normalize_github_blob_url() -> None:
    blob = "https://github.com/veenyi/octop-plugins/blob/main/octop-toolkit.zip"
    assert (
        normalize_plugin_download_url(blob)
        == "https://raw.githubusercontent.com/veenyi/octop-plugins/main/octop-toolkit.zip"
    )
    raw_page = "https://github.com/veenyi/octop-plugins/raw/main/octop-toolkit.zip"
    assert (
        normalize_plugin_download_url(raw_page)
        == "https://raw.githubusercontent.com/veenyi/octop-plugins/main/octop-toolkit.zip"
    )
    already_raw = "https://raw.githubusercontent.com/veenyi/octop-plugins/main/octop-toolkit.zip"
    assert normalize_plugin_download_url(already_raw) == already_raw


def test_install_url_rejects_non_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)

    def fake_retrieve(
        url: str, filename: str | Path, *args: Any, **kwargs: Any
    ) -> tuple[str, None]:
        Path(filename).write_text("<!DOCTYPE html><html>blob page</html>", encoding="utf-8")
        return (str(filename), None)

    monkeypatch.setattr(
        "octop.infra.agents.plugins.manager.urllib.request.urlretrieve",
        fake_retrieve,
    )
    with pytest.raises(OctopError) as excinfo:
        mgr.install_url("https://example.com/not-a-plugin.zip")
    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    assert excinfo.value.status == 400


def test_install_url_accepts_valid_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in _FIXTURE.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=f"echo-tool/{path.relative_to(_FIXTURE).as_posix()}")

    def fake_retrieve(
        url: str, filename: str | Path, *args: Any, **kwargs: Any
    ) -> tuple[str, None]:
        Path(filename).write_bytes(buf.getvalue())
        return (str(filename), None)

    monkeypatch.setattr(
        "octop.infra.agents.plugins.manager.urllib.request.urlretrieve",
        fake_retrieve,
    )
    loaded = mgr.install_url("https://example.com/echo-tool.zip", force=True)
    assert loaded.manifest.id == "echo-tool"


def test_install_archive_accepts_local_zip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    archive = tmp_path / "echo-tool.zip"
    archive.write_bytes(_echo_zip_bytes())
    loaded = mgr.install_archive(archive, force=True)
    assert loaded.manifest.id == "echo-tool"
    items = mgr.list_installed()
    assert any(i.get("id") == "echo-tool" for i in items)


def test_install_archive_rejects_non_zip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    archive = tmp_path / "not-a-zip.zip"
    archive.write_text("not a zip", encoding="utf-8")
    with pytest.raises(OctopError) as excinfo:
        mgr.install_archive(archive)
    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    assert excinfo.value.status == 400


def test_install_path_already_exists(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    mgr.install_path(_FIXTURE, force=True)
    with pytest.raises(OctopError) as excinfo:
        mgr.install_path(_FIXTURE, force=False)
    assert excinfo.value.code is ErrorCode.PLUGIN_ALREADY_EXISTS
    assert excinfo.value.status == 409
    assert excinfo.value.details.get("id") == "echo-tool"


def test_parse_plugin_ui_meta_and_list(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "with-ui"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "id: with-ui",
                "version: 0.1.0",
                "name: With UI",
                "kind: tool",
                "entry: main.py",
                "ui:",
                "  entry: ui/dist/index.js",
                "  manifest: ui/dist/manifest.json",
            ],
        ),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "def setup(ctx):\n    pass\n",
        encoding="utf-8",
    )
    dist = plugin_dir / "ui" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.js").write_text("export function setup() {}", encoding="utf-8")
    (dist / "manifest.json").write_text("{}", encoding="utf-8")

    assert parse_plugin_ui_meta(plugin_dir) == {
        "entry": "ui/dist/index.js",
        "manifest": "ui/dist/manifest.json",
    }

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    mgr.install_path(plugin_dir, force=True)
    items = mgr.list_installed()
    row = next(i for i in items if i.get("id") == "with-ui")
    assert row.get("ui") == {
        "entry": "ui/dist/index.js",
        "manifest": "ui/dist/manifest.json",
    }
    resolved = mgr.resolve_ui_file("with-ui", "dist/index.js")
    assert resolved.name == "index.js"
    with pytest.raises(OctopError) as excinfo:
        mgr.resolve_ui_file("with-ui", "../plugin.yaml")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_load_missing_picks_up_cli_install(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    plugins_dir = tmp_path / "plugins"
    mgr = PluginManager(plugins_dir=plugins_dir, config_path=config_path)
    # Simulate CLI install: copy to disk without going through this process registry
    dest = plugins_dir / "echo-tool"
    dest.mkdir(parents=True)
    for path in _FIXTURE.rglob("*"):
        if path.is_file():
            target = dest / path.relative_to(_FIXTURE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())

    assert PluginRegistry().get("echo-tool") is None
    newly = mgr.load_missing(install_deps=False)
    assert len(newly) == 1
    assert newly[0].manifest.id == "echo-tool"
    assert PluginRegistry().get("echo-tool") is not None
    # Second call is a no-op
    assert mgr.load_missing(install_deps=False) == []


def test_parse_plugin_ui_meta_missing_entry(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-ui-file"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "id: no-ui-file",
                "version: 0.1.0",
                "name: No UI File",
                "kind: tool",
                "entry: main.py",
                "ui:",
                "  entry: ui/dist/index.js",
            ],
        ),
        encoding="utf-8",
    )
    assert parse_plugin_ui_meta(plugin_dir) is None


def test_parse_plugin_icon(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "with-icon"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "id: with-icon",
                "version: 0.1.0",
                "name: With Icon",
                "kind: tool",
                "entry: main.py",
                'icon: "🧩"',
            ],
        ),
        encoding="utf-8",
    )
    assert parse_plugin_icon(plugin_dir) == "🧩"
    assert parse_plugin_icon(tmp_path / "missing") is None

    file_icon_dir = tmp_path / "file-icon"
    file_icon_dir.mkdir()
    (file_icon_dir / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>',
        encoding="utf-8",
    )
    (file_icon_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "id: file-icon",
                "version: 0.1.0",
                "name: File Icon",
                "kind: tool",
                "entry: main.py",
                "icon: icon.svg",
            ],
        ),
        encoding="utf-8",
    )
    assert parse_plugin_icon(file_icon_dir) == "/api/plugins/file-icon/ui/icon.svg"


def test_parse_plugin_group(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "grouped"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "id: grouped",
                "version: 0.1.0",
                "name: Grouped",
                "kind: tool",
                "entry: main.py",
                "group: games",
            ],
        ),
        encoding="utf-8",
    )
    assert parse_plugin_group(plugin_dir) == "games"
    assert parse_plugin_group(tmp_path / "missing") is None


def test_set_enabled_refuses_corrupt_config_and_preserves_bytes(tmp_path: Path) -> None:
    """issue #730: the dashboard toggle must not wipe an unparseable config.json."""
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    mgr.install_path(_FIXTURE, force=True)

    corrupt = '{"bind_host": "0.0.0.0", "database": {"driver": "postgresql"},}'
    config_path.write_text(corrupt, encoding="utf-8")
    with pytest.raises(OctopError) as excinfo:
        mgr.set_enabled("echo-tool", False)
    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT
    assert config_path.read_text(encoding="utf-8") == corrupt


def test_install_plugin_importing_legacy_harness_agent(tmp_path: Path) -> None:
    """Plugins published before the octop_harness rename still import harness_agent."""
    src = tmp_path / "legacy-plugin"
    src.mkdir()
    (src / "plugin.yaml").write_text(
        "id: legacy-plugin\nversion: 0.1.0\nname: Legacy\nkind: tool\nentry: main.py\n",
        encoding="utf-8",
    )
    (src / "main.py").write_text(
        "from harness_agent.plugins import PluginContext\n"
        "from harness_agent.plugins.context import PluginContext as Ctx\n"
        "\n"
        "def ping() -> str:\n"
        "    return 'pong'\n"
        "\n"
        "def setup(ctx: PluginContext) -> None:\n"
        "    if Ctx is not PluginContext:\n"
        "        raise RuntimeError('legacy PluginContext is not the installed class')\n"
        "    ctx.tool('ping', ping, description='ping')\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    loaded = mgr.install_path(src, force=True)
    assert loaded.manifest.id == "legacy-plugin"
    assert [tool.name for tool in loaded.tools] == ["ping"]

    import octop_harness
    from harness_agent.plugins import PluginContext
    from octop_harness.plugins import PluginContext as RealContext

    assert PluginContext is RealContext
    assert octop_harness.__name__ == "octop_harness"
    assert sys.modules["harness_agent"] is octop_harness


def test_set_enabled_preserves_unrelated_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "bind_host": "0.0.0.0",
                "database": {"driver": "postgresql", "host": "db.internal"},
            }
        ),
        encoding="utf-8",
    )
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=config_path)
    mgr.install_path(_FIXTURE, force=True)
    mgr.set_enabled("echo-tool", False)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["bind_host"] == "0.0.0.0"
    assert data["database"] == {"driver": "postgresql", "host": "db.internal"}
    assert data["plugins"]["echo-tool"]["enabled"] is False


def test_channel_reload_preserves_class_until_source_changes(tmp_path: Path) -> None:
    from octop_harness.plugins.context import PluginContext

    if not hasattr(PluginContext, "channel"):
        pytest.skip("released harness lacks channel registration; exercised with companion source")
    config = tmp_path / "config.json"
    config.write_text("{}")
    directory = tmp_path / "plugins" / "test-channel"
    directory.mkdir(parents=True)
    (directory / "plugin.yaml").write_text(
        "id: test-channel\nversion: 1\nkind: channel\nentry: main.py\n"
    )
    source = directory / "main.py"
    source.write_text('class Channel: pass\ndef setup(ctx): ctx.channel("acme", Channel)\n')
    manager = PluginManager(plugins_dir=directory.parent, config_path=config)
    first = manager.load_installed(install_deps=False)[0].channels[0].channel_cls
    second = manager.load_installed(install_deps=False)[0].channels[0].channel_cls
    assert first is second
    source.write_text(source.read_text() + "\n# updated implementation\n")
    third = manager.load_installed(install_deps=False)[0].channels[0].channel_cls
    assert third is not first
