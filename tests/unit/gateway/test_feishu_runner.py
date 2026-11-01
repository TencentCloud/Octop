"""Unit tests for the Feishu bot-creator subprocess runner."""

from __future__ import annotations

import pytest

from octop.infra.gateway.bot_creators.feishu_runner import bot_creator_script


def test_bot_creator_script_resolves_a_bundled_script() -> None:
    script = bot_creator_script("feishu_bot_creator.py")
    assert script.name == "feishu_bot_creator.py"
    assert script.parent.name == "bot_creators"
    assert script.is_file()


@pytest.mark.parametrize(
    "name",
    [
        "../../../../../pyproject.toml",
        "../__init__.py",
    ],
)
def test_bot_creator_script_rejects_paths_outside_its_directory(name: str) -> None:
    with pytest.raises(RuntimeError):
        bot_creator_script(name)
