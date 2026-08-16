"""Unit tests for Ollama local service enablement defaults."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from octop.api.routers import ollama_models


def test_ollama_service_defaults_to_disabled_when_unset() -> None:
    server = SimpleNamespace(services=SimpleNamespace(settings_repo=MagicMock()))
    server.services.settings_repo.get.return_value = None
    assert ollama_models._ollama_service_enabled(server) is False


def test_ollama_service_respects_stored_true() -> None:
    server = SimpleNamespace(services=SimpleNamespace(settings_repo=MagicMock()))
    server.services.settings_repo.get.return_value = "true"
    assert ollama_models._ollama_service_enabled(server) is True
