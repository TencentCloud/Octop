"""Host-level harness factory used by one-shot text calls."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from octop_harness.config import ModelConfig, ProviderConfig
from octop_harness.llm.factory import ChatModelFactory

from octop.infra.agents.providers.host_factory import HostModelFactory
from octop.infra.errors import ErrorCode, OctopError


def _provider(provider_id: str, *model_ids: str, disabled: str = "") -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        name=provider_id,
        models=[ModelConfig(id=model_id, enabled=model_id != disabled) for model_id in model_ids],
    )


def test_auto_uses_first_enabled_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_chat_model(
        self: ChatModelFactory, model_ref: str, *, max_retries: int | None = None
    ) -> MagicMock:
        del self, max_retries
        captured["ref"] = model_ref
        return MagicMock()

    monkeypatch.setattr(ChatModelFactory, "get_chat_model", fake_get_chat_model)
    host = HostModelFactory()
    host.sync(
        [
            _provider("first", "off", "on", disabled="off"),
            _provider("second", "other"),
        ]
    )

    access = host.get(None)

    assert captured["ref"] == "first/on"
    assert access.model_ref == "first/on"
    host.close()


def test_explicit_ref_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_chat_model(
        self: ChatModelFactory, model_ref: str, *, max_retries: int | None = None
    ) -> MagicMock:
        del self, max_retries
        captured["ref"] = model_ref
        return MagicMock()

    monkeypatch.setattr(ChatModelFactory, "get_chat_model", fake_get_chat_model)
    host = HostModelFactory()
    host.sync([_provider("openai", "gpt-4o-mini", "gpt-4o")])

    access = host.get("openai/gpt-4o")

    assert captured["ref"] == "openai/gpt-4o"
    assert access.model_ref == "openai/gpt-4o"
    host.close()


def test_auto_alias_and_missing_factory() -> None:
    host = HostModelFactory()
    with pytest.raises(OctopError) as exc:
        host.get("auto")
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
    assert exc.value.message == "model factory unavailable"


def test_unknown_ref_is_rejected() -> None:
    host = HostModelFactory()
    host.sync([_provider("openai", "gpt-4o")])
    with pytest.raises(OctopError) as exc:
        host.get("other/model")
    assert exc.value.message == "model unavailable for text assist"
    host.close()


def test_sync_drop_closes_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ChatModelFactory, "get_chat_model", lambda *args, **kwargs: MagicMock())
    host = HostModelFactory()
    host.sync([_provider("openai", "gpt-4o")])
    host.sync([])
    with pytest.raises(OctopError) as exc:
        host.get("auto")
    assert exc.value.code == ErrorCode.INTERNAL_ERROR
