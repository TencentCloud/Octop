"""Unit tests for OpenCode Go session-header wiring (preset-only)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from octop.infra.agents.providers.opencode_session import (
    OPENCODE_SESSION_HEADER,
    ensure_opencode_session_header,
    is_opencode_base_url,
    is_opencode_preset,
    session_header_for_provider,
)
from octop.infra.agents.providers.probe import build_probe_chat_model
from octop.infra.agents.providers.store import ProviderStore

GO_PRESET_ID = "opencode-go-openai"
GO_PRESET_NAME = "OpenCode Go (Compatible)"
GO_ANTHROPIC_ID = "opencode-go-anthropic"
GO_ANTHROPIC_NAME = "OpenCode Go (Anthropic)"
ZEN_PRESET_ID = "opencode-zen-openai"
ZEN_PRESET_NAME = "OpenCode Zen (Compatible)"
ZEN_ANTHROPIC_ID = "opencode-zen-anthropic"
ZEN_ANTHROPIC_NAME = "OpenCode Zen (Anthropic)"
GO_OPENAI_URL = "https://opencode.ai/zen/go/v1"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (GO_PRESET_ID, True),
        (GO_PRESET_NAME, True),
        (GO_ANTHROPIC_ID, True),
        (GO_ANTHROPIC_NAME, True),
        (ZEN_PRESET_ID, True),
        (ZEN_PRESET_NAME, True),
        (ZEN_ANTHROPIC_ID, True),
        (ZEN_ANTHROPIC_NAME, True),
        ("my-custom-go", False),
        ("", False),
        (None, False),
    ],
)
def test_is_opencode_preset(name: str | None, expected: bool) -> None:
    assert is_opencode_preset(name) is expected


def test_ensure_injects_throwaway_session_for_go_preset() -> None:
    headers = ensure_opencode_session_header(GO_PRESET_ID, None)
    assert headers[OPENCODE_SESSION_HEADER]
    assert len(headers[OPENCODE_SESSION_HEADER]) == 32


def test_ensure_preserves_existing_header() -> None:
    headers = ensure_opencode_session_header(GO_ANTHROPIC_ID, {OPENCODE_SESSION_HEADER: "custom"})
    assert headers[OPENCODE_SESSION_HEADER] == "custom"


def test_ensure_leaves_unrelated_provider_untouched() -> None:
    headers = ensure_opencode_session_header(
        "custom",
        {"Authorization": "Bearer x"},
        base_url="https://api.example.com/v1",
    )
    assert headers == {"Authorization": "Bearer x"}
    assert OPENCODE_SESSION_HEADER not in headers


def test_ensure_injects_for_custom_provider_on_opencode_host() -> None:
    headers = ensure_opencode_session_header(
        "my-relay",
        None,
        base_url="https://proxy.opencode.ai/v1",
    )
    assert headers[OPENCODE_SESSION_HEADER]


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://opencode.ai/zen/v1", True),
        ("https://opencode.ai/zen/go/v1", True),
        ("https://OPENCODE.AI/zen", True),
        ("https://proxy.opencode.ai/v1", True),
        ("https://go.opencode.ai", True),
        ("https://evil-opencode.ai/zen/go", False),
        ("https://opencode.ai.evil.example/v1", False),
        ("https://api.example.com/v1", False),
        ("", False),
        (None, False),
    ],
)
def test_is_opencode_base_url(base_url: str | None, expected: bool) -> None:
    assert is_opencode_base_url(base_url) is expected


def test_session_header_for_provider() -> None:
    assert session_header_for_provider(GO_PRESET_NAME) == OPENCODE_SESSION_HEADER
    assert session_header_for_provider("openai") is None
    assert session_header_for_provider("custom", GO_OPENAI_URL) == OPENCODE_SESSION_HEADER
    assert session_header_for_provider("custom", "https://api.example.com/v1") is None


def _probe_row(**overrides: Any) -> SimpleNamespace:
    data: dict[str, Any] = {
        "name": GO_PRESET_NAME,
        "kind": "openai",
        "base_url": GO_OPENAI_URL,
        "api_key": "sk-test",
        "extra_json": None,
        "get_models": lambda: [{"id": "glm-5.2", "name": "GLM-5.2"}],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_probe_chat_model_injects_throwaway_session_header() -> None:
    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        build_probe_chat_model(_probe_row(), model_id="glm-5.2")

    provider = mock_build.call_args[0][0]
    assert OPENCODE_SESSION_HEADER in provider.headers
    assert len(provider.headers[OPENCODE_SESSION_HEADER]) == 32


def test_probe_chat_model_keeps_user_session_header() -> None:
    row = _probe_row(extra_json=json.dumps({"headers": {OPENCODE_SESSION_HEADER: "mine"}}))
    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        build_probe_chat_model(row, model_id="glm-5.2")

    provider = mock_build.call_args[0][0]
    assert provider.headers[OPENCODE_SESSION_HEADER] == "mine"


def test_probe_injects_for_custom_provider_on_go_url() -> None:
    row = _probe_row(name="my-relay")
    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        build_probe_chat_model(row, model_id="glm-5.2")

    provider = mock_build.call_args[0][0]
    assert OPENCODE_SESSION_HEADER in provider.headers


class _FakeRepo:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows
        self.updates: list[dict[str, Any]] = []

    def list_all(self) -> list[SimpleNamespace]:
        return list(self._rows)

    def update(self, provider_id: int, **kwargs: Any) -> None:
        self.updates.append({"provider_id": provider_id, **kwargs})


def _row_with_extra(
    extra_json: str | None,
    *,
    name: str = GO_PRESET_NAME,
    base_url: str = GO_OPENAI_URL,
) -> SimpleNamespace:
    models_json = json.dumps([{"id": "glm-5.2", "name": "GLM-5.2", "enabled": True}])
    return SimpleNamespace(
        id=7,
        name=name,
        kind="openai",
        base_url=base_url,
        api_key="sk-test",
        extra_json=extra_json,
        models_json=models_json,
        enabled=True,
        get_models=lambda: json.loads(models_json),
    )


def test_store_sets_session_header_for_go_preset() -> None:
    store = ProviderStore(_FakeRepo([_row_with_extra(None)]))  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    assert len(configs) == 1
    assert configs[0].session_header == OPENCODE_SESSION_HEADER
    assert OPENCODE_SESSION_HEADER not in configs[0].headers


def test_store_matches_preset_id() -> None:
    row = _row_with_extra(None, name=GO_PRESET_ID)
    configs = ProviderStore(_FakeRepo([row])).build_harness_configs()  # type: ignore[arg-type]
    assert configs[0].session_header == OPENCODE_SESSION_HEADER


def test_store_sets_session_header_for_zen_preset() -> None:
    row = _row_with_extra(None, name=ZEN_PRESET_NAME, base_url="https://opencode.ai/zen/v1")
    configs = ProviderStore(_FakeRepo([row])).build_harness_configs()  # type: ignore[arg-type]
    assert configs[0].session_header == OPENCODE_SESSION_HEADER


def test_store_does_not_write_provider_row() -> None:
    repo = _FakeRepo([_row_with_extra(None)])
    store = ProviderStore(repo)  # type: ignore[arg-type]

    store.build_harness_configs()

    assert repo.updates == []


def test_store_sets_session_header_for_custom_provider_on_opencode_host() -> None:
    row = _row_with_extra(None, name="custom-go")
    configs = ProviderStore(_FakeRepo([row])).build_harness_configs()  # type: ignore[arg-type]

    assert configs and configs[0].session_header == OPENCODE_SESSION_HEADER


def test_store_skips_custom_provider_on_other_host() -> None:
    row = _row_with_extra(None, name="custom", base_url="https://api.example.com/v1")
    configs = ProviderStore(_FakeRepo([row])).build_harness_configs()  # type: ignore[arg-type]

    assert configs and configs[0].session_header is None


def test_knowledge_remote_embedding_sends_session_header() -> None:
    from octop.infra.knowledge import embed as embed_module

    provider = SimpleNamespace(
        name=GO_PRESET_NAME,
        base_url=GO_OPENAI_URL,
        api_key="sk-test",
        extra_json=None,
    )
    services = SimpleNamespace(
        settings_repo=SimpleNamespace(
            get=lambda key: {
                "knowledge_embedding_backend": "remote",
                "knowledge_embedding_model": "embed-1",
                "knowledge_embedding_provider_id": "3",
            }.get(key)
        ),
        provider_repo=SimpleNamespace(get=lambda _pid: provider),
    )
    seen: dict[str, str] = {}

    def fake_batched(
        _client: Any,
        _base: str,
        headers: dict[str, str],
        _model: str,
        _texts: list[str],
    ) -> list[list[float]]:
        seen.update(headers)
        return [[0.1]]

    with patch.object(embed_module, "_embed_remote_batched", fake_batched):
        embed_module.embed_knowledge_texts(services, ["hello"])

    assert seen[OPENCODE_SESSION_HEADER]
