"""Tests for ``octop models`` ollama subcommands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


def test_models_help_lists_ollama_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["models", "--help"])
    assert result.exit_code == 0
    for sub in ("ollama-list", "ollama-pull", "ollama-rm"):
        assert sub in result.output


def test_models_config_keeps_preset_input(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.cli.support import offline_ops, prompts

    preset = {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "protocol": "openai",
        "models": [{"id": "deepseek-v4-flash", "name": "Flash", "input": ["text", "image"]}],
    }
    created: list[dict[str, object]] = []

    def create_provider(**kwargs: object) -> dict[str, object]:
        created.append(kwargs)
        return {"id": 1, "name": "DeepSeek"}

    monkeypatch.setattr(offline_ops, "load_provider_presets_offline", lambda: [preset])
    monkeypatch.setattr(offline_ops, "create_provider_offline", create_provider)
    monkeypatch.setattr(prompts, "select", lambda *args, **kwargs: "DeepSeek (deepseek)")
    monkeypatch.setattr(prompts, "text", lambda *args, **kwargs: kwargs["default"])
    monkeypatch.setattr(prompts, "password", lambda *args, **kwargs: "sk-test")
    monkeypatch.setattr(prompts, "confirm", lambda *args, **kwargs: False)

    result = CliRunner().invoke(cli, ["models", "config"])
    assert result.exit_code == 0, result.output
    assert created[0]["models"] == [
        {"id": "deepseek-v4-flash", "name": "Flash", "enabled": True, "input": ["text", "image"]}
    ]
