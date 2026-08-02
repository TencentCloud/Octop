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
)
from octop.infra.errors import ErrorCode, OctopError

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"


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
