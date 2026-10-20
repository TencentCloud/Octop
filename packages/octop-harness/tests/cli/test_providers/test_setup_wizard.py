"""Tests for the provider setup wizard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop_harness.cli.providers.setup_wizard import (
    SetupResult,
    _detect_env_provider,
    _write_provider_config,
)


def test_detect_env_provider_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
    result = _detect_env_provider()
    assert result == ("openai", "sk-test123")


def test_detect_env_provider_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-abc")
    result = _detect_env_provider()
    assert result == ("deepseek", "sk-abc")


def test_detect_env_provider_none(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "TENCENT_CODING_PLAN_API_KEY",
        "TENCENT_TOKEN_PLAN_API_KEY",
        "DASHSCOPE_API_KEY",
        "VOLCES_API_KEY",
        "ZHIPU_API_KEY",
        "MINIMAX_API_KEY",
        "MOONSHOT_API_KEY",
        "SILICON_API_KEY",
        "MIMO_API_KEY",
        "MODELSCOPE_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    result = _detect_env_provider()
    assert result is None


def test_write_provider_config_creates_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _write_provider_config(
        config_path=config_path,
        provider_key="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        protocol="openai",
        model_id="deepseek-chat",
    )
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert "providers" in data
    assert "deepseek" in data["providers"]
    assert data["providers"]["deepseek"]["api_key"] == "sk-test"
    assert data["providers"]["deepseek"]["models"][0]["id"] == "deepseek-chat"
    assert data["default_model"] == "deepseek/deepseek-chat"


def test_write_provider_config_merges_existing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"workspace_dir": "/ws", "cli": {"theme": "dark"}}))
    _write_provider_config(
        config_path=config_path,
        provider_key="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-key",
        protocol="openai",
        model_id="gpt-4o",
    )
    data = json.loads(config_path.read_text())
    assert data["workspace_dir"] == "/ws"
    assert data["cli"]["theme"] == "dark"
    assert "openai" in data["providers"]


def test_write_provider_config_creates_agents_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _write_provider_config(
        config_path=config_path,
        provider_key="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        protocol="openai",
        model_id="deepseek-chat",
    )
    data = json.loads(config_path.read_text())
    assert "agents" in data
    assert "main" in data["agents"]
    assert data["agents"]["main"]["provider"] == "deepseek"
    assert data["default_agent"] == "main"


def test_setup_result_dataclass() -> None:
    r = SetupResult(provider_key="openai", model_id="gpt-4o")
    assert r.provider_key == "openai"
    assert r.model_id == "gpt-4o"
    assert r.model_ref == "openai/gpt-4o"
