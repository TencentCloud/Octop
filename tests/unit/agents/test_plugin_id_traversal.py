"""A plugin id must be a single directory name, not a path."""

from __future__ import annotations

import pytest

from octop.infra.agents.plugins import manager as pm
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.parametrize(
    "plugin_id",
    ["../evil-plugin", "..", "a/b", "a\\b", "", "   "],
)
def test_unsafe_ids_are_rejected(plugin_id, tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "plugin.yaml").write_text(
        f"id: {plugin_id!r}\nversion: '1'\nname: n\n", encoding="utf-8"
    )
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    mgr = pm.PluginManager(plugins_dir=plugins_dir, config_path=tmp_path / "config.json")

    with pytest.raises(OctopError) as excinfo:
        mgr.install_path(source, force=True)

    assert excinfo.value.code is ErrorCode.PLUGIN_INVALID_ARCHIVE
    # Nothing may be created next to (or above) the plugins directory.
    assert {p.name for p in tmp_path.iterdir()} == {"src", "plugins"}


def test_a_plain_id_is_still_accepted(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "plugin.yaml").write_text("id: demo\nversion: '1'\nname: n\n", encoding="utf-8")
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()

    assert pm.is_safe_plugin_id("demo")
    assert not pm.is_safe_plugin_id("../demo")
