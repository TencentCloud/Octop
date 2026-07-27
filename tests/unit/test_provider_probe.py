"""Unit tests for provider connectivity probe helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from octop.infra.agents.providers.probe import build_probe_chat_model as _build_chat_model


def test_build_chat_model_includes_provider_id_and_model_name() -> None:
    row = SimpleNamespace(
        name="HAI",
        kind="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        get_models=lambda: [{"id": "MiniMax-M2.7", "name": "MiniMax-M2.7"}],
    )

    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        _build_chat_model(row, model_id="MiniMax-M2.7")

    provider, model = mock_build.call_args[0]
    assert provider.id == "HAI"
    assert provider.name == "HAI"
    assert model.id == "MiniMax-M2.7"
    assert model.name == "MiniMax-M2.7"


def test_build_chat_model_uses_codex_responses_compatibility_options() -> None:
    row = SimpleNamespace(
        name="Codex",
        kind="openai",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="codex-token",
        extra_json='{"headers": {"ChatGPT-Account-Id": "account-id"}}',
        get_models=lambda: [{"id": "gpt-5.4", "name": "GPT-5.4"}],
    )

    with patch("langchain_openai.ChatOpenAI") as mock_chat_openai:
        mock_chat_openai.return_value = object()
        _build_chat_model(row, model_id="gpt-5.4")

    assert mock_chat_openai.call_args.kwargs == {
        "model": "gpt-5.4",
        "base_url": "https://chatgpt.com/backend-api/codex",
        "api_key": "codex-token",
        "use_responses_api": True,
        "store": False,
        "streaming": True,
        "output_version": "v0",
        "default_headers": {"ChatGPT-Account-Id": "account-id"},
    }
