"""Unit tests for OpenCode Go ``x-opencode-session`` header injection."""

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


# ── URL detection ───────────────────────────────────────────────────────────


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


# ── Header injection helper ─────────────────────────────────────────────────


def test_ensure_injects_session_for_go_url() -> None:
    headers, injected = ensure_opencode_session_header(GO_OPENAI_URL, None)
    assert injected is not None
    assert headers[OPENCODE_SESSION_HEADER] == injected
    assert len(injected) == 32  # uuid4().hex


def test_ensure_preserves_existing_lowercase_header() -> None:
    headers, injected = ensure_opencode_session_header(
        GO_ANTHROPIC_URL, {OPENCODE_SESSION_HEADER: "custom"}
    )
    assert injected is None
    assert headers[OPENCODE_SESSION_HEADER] == "custom"


def test_ensure_preserves_case_variant_header() -> None:
    headers, injected = ensure_opencode_session_header(
        GO_ANTHROPIC_URL, {"X-Opencode-Session": "user-set"}
    )
    assert injected is None
    assert headers["X-Opencode-Session"] == "user-set"
    assert OPENCODE_SESSION_HEADER not in headers


def test_ensure_uses_provided_session_id() -> None:
    headers, injected = ensure_opencode_session_header(GO_OPENAI_URL, {}, session_id="fixed-id")
    assert injected == "fixed-id"
    assert headers[OPENCODE_SESSION_HEADER] == "fixed-id"


def test_ensure_leaves_other_urls_untouched() -> None:
    for url in (ZEN_URL, "https://api.example.com/v1", None):
        headers, injected = ensure_opencode_session_header(url, {"Authorization": "Bearer x"})
        assert injected is None
        assert headers == {"Authorization": "Bearer x"}
        assert OPENCODE_SESSION_HEADER not in headers


# ── Probe path ──────────────────────────────────────────────────────────────


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


def test_probe_chat_model_injects_session_header() -> None:
    with patch("harness_agent.llm.factory.build_chat_model") as mock_build:
        mock_build.return_value = object()
        build_probe_chat_model(_probe_row(), model_id="glm-5.2")

    provider = mock_build.call_args[0][0]
    assert OPENCODE_SESSION_HEADER in provider.headers


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


# ── Store / chat runtime path ───────────────────────────────────────────────


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


def test_store_persists_session_header_for_go_provider() -> None:
    row = _row_with_extra(None)
    repo = _FakeRepo([row])
    store = ProviderStore(repo)  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    assert len(configs) == 1
    session = configs[0].headers[OPENCODE_SESSION_HEADER]
    assert session
    assert len(repo.updates) == 1
    saved = json.loads(repo.updates[0]["extra_json"])
    assert saved["headers"][OPENCODE_SESSION_HEADER] == session


def test_store_persession_header_survives_other_extra_keys() -> None:
    row = _row_with_extra(json.dumps({"note_flag": True}))
    repo = _FakeRepo([row])
    store = ProviderStore(repo)  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    saved = json.loads(repo.updates[0]["extra_json"])
    assert saved["note_flag"] is True
    assert OPENCODE_SESSION_HEADER in saved["headers"]
    assert OPENCODE_SESSION_HEADER in configs[0].headers


def test_store_does_not_rewrite_existing_session() -> None:
    row = _row_with_extra(json.dumps({"headers": {OPENCODE_SESSION_HEADER: "stable-id"}}))
    repo = _FakeRepo([row])
    store = ProviderStore(repo)  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    assert repo.updates == []
    assert configs[0].headers[OPENCODE_SESSION_HEADER] == "stable-id"


def test_store_skips_injection_for_non_go_provider() -> None:
    row = _row_with_extra(None, base_url=ZEN_URL)
    repo = _FakeRepo([row])
    store = ProviderStore(repo)  # type: ignore[arg-type]

    configs = store.build_harness_configs()

    assert repo.updates == []
    assert configs and OPENCODE_SESSION_HEADER not in configs[0].headers
