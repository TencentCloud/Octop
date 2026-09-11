"""Unit tests for OpenCode Go session-header wiring."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from octop.infra.agents.providers.opencode_session import (
    OPENCODE_SESSION_HEADER,
    ensure_opencode_session_header,
    is_opencode_go_base_url,
)
from octop.infra.agents.providers.probe import build_probe_chat_model
from octop.infra.agents.providers.store import ProviderStore

GO_OPENAI_URL = "https://opencode.ai/zen/go/v1"
GO_ANTHROPIC_URL = "https://opencode.ai/zen/go"
ZEN_URL = "https://opencode.ai/zen"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (GO_OPENAI_URL, True),
        (GO_ANTHROPIC_URL, True),
        ("https://opencode.ai/zen/go/", True),
        ("https://OPENCODE.AI/zen/go/v1", True),
        (ZEN_URL, False),
        ("https://opencode.ai/zen/v1", False),
        ("https://api.example.com/v1", False),
        ("https://evil.example.com/zen/go", False),
        ("", False),
        (None, False),
    ],
)
def test_is_opencode_go_base_url(base_url: str | None, expected: bool) -> None:
    assert is_opencode_go_base_url(base_url) is expected


def test_ensure_injects_throwaway_session_for_go_url() -> None:
    headers = ensure_opencode_session_header(GO_OPENAI_URL, None)
    assert headers[OPENCODE_SESSION_HEADER]
    assert len(headers[OPENCODE_SESSION_HEADER]) == 32


def test_ensure_preserves_existing_header() -> None:
    headers = ensure_opencode_session_header(GO_ANTHROPIC_URL, {OPENCODE_SESSION_HEADER: "custom"})
    assert headers[OPENCODE_SESSION_HEADER] == "custom"


def test_ensure_leaves_other_urls_untouched() -> None:
    headers = ensure_opencode_session_header(ZEN_URL, {"Authorization": "Bearer x"})
    assert headers == {"Authorization": "Bearer x"}
    assert OPENCODE_SESSION_HEADER not in headers


def _probe_row(**overrides: Any) -> SimpleNamespace:
    data: dict[str, Any] = {
        "name": "OpenCode Go",
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


def test_probe_chat_model_skips_non_go_providers() -> None:
    row = _probe_row(base_url="https://api.example.com/v1")
    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        build_probe_chat_model(row, model_id="glm-5.2")

    provider = mock_build.call_args[0][0]
    assert OPENCODE_SESSION_HEADER not in provider.headers


class _FakeRepo:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows
        self.updates: list[dict[str, Any]] = []

    def list_all(self) -> list[SimpleNamespace]:
        return list(self._rows)

    def update(self, provider_id: int, **kwargs: Any) -> None:
        self.updates.append({"provider_id": provider_id, **kwargs})


def _row_with_extra(extra_json: str | None, base_url: str = GO_OPENAI_URL) -> SimpleNamespace:
    models_json = json.dumps([{"id": "glm-5.2", "name": "GLM-5.2", "enabled": True}])
    return SimpleNamespace(
        id=7,
        name="OpenCode Go",
        kind="openai",
        base_url=base_url,
        api_key="sk-test",
        extra_json=extra_json,
        models_json=models_json,
        enabled=True,
        get_models=lambda: json.loads(models_json),
    )


def test_store_sets_session_header_for_go_provider() -> None:
    row = _row_with_extra(None)
    store = ProviderStore(_FakeRepo([row]))  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    assert len(configs) == 1
    assert configs[0].session_header == OPENCODE_SESSION_HEADER
    assert OPENCODE_SESSION_HEADER not in configs[0].headers


def test_store_does_not_write_provider_row() -> None:
    row = _row_with_extra(None)
    repo = _FakeRepo([row])
    store = ProviderStore(repo)  # type: ignore[arg-type]

    store.build_harness_configs()

    assert repo.updates == []


def test_store_skips_session_header_for_non_go_provider() -> None:
    row = _row_with_extra(None, base_url=ZEN_URL)
    store = ProviderStore(_FakeRepo([row]))  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    assert configs and configs[0].session_header is None
