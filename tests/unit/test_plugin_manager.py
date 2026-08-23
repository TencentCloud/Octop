"""Unit tests for Octop plugin manager."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from harness_agent.plugins import PluginRegistry

from octop.infra.agents.plugins.manager import (
    PluginManager,
    normalize_plugin_download_url,
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
