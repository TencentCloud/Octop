"""Tests for octop_harness.cli.config.schema."""

from octop_harness.cli.config.schema import CliConfig


def test_default_values() -> None:
    cfg = CliConfig()
    assert cfg.theme == "dark"
    assert cfg.stream is True
    assert cfg.show_token_usage is True
    assert cfg.max_history_display == 50
    assert cfg.keybindings == "emacs"
    assert cfg.default_command == "chat"


def test_from_dict_partial() -> None:
    cfg = CliConfig.from_dict({"theme": "light", "stream": False})
    assert cfg.theme == "light"
    assert cfg.stream is False
    assert cfg.show_token_usage is True


def test_to_dict_roundtrip() -> None:
    cfg = CliConfig(theme="light", max_history_display=100)
    data = cfg.to_dict()
    restored = CliConfig.from_dict(data)
    assert restored.theme == "light"
    assert restored.max_history_display == 100


def test_from_dict_ignores_unknown_keys() -> None:
    cfg = CliConfig.from_dict({"theme": "dark", "unknown_key": 42})
    assert cfg.theme == "dark"
