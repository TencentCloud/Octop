"""Codex discovery and credential application without live account credentials."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from octop.config import OctopConfig
from octop.infra.agents.providers import codex_apply, codex_catalog, probe
from octop.infra.agents.providers.codex_oauth import CODEX_BASE_URL
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.utils.paths import PathLayout

CATALOG = {
    "models": [
        {
            "slug": "model-first",
            "display_name": "First model",
            "visibility": "list",
            "input_modalities": ["text", "image"],
            "context_window": 500000,
        },
        {"slug": "model-second", "visibility": "list"},
        {"slug": "hidden", "visibility": "hide"},
        {"slug": "model-first", "display_name": "Duplicate"},
    ]
}
CREDENTIALS = {
    "access": "test-access",
    "refresh": "test-refresh",
    "expires": 1,
    "account_id": "test-account-one",
}


@pytest.fixture
def services(tmp_path: Path) -> Iterator[SharedServices]:
    paths = PathLayout(tmp_path)
    pool = SqlitePool(paths.db)
    run_migrations(pool)
    try:
        yield build_shared_services(db=pool, paths=paths, config=OctopConfig())
    finally:
        pool.close()


@pytest.fixture
def catalog_http(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Keep real HTTP clients/serialization; replace only their transport."""
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = CATALOG if request.url.host == "chatgpt.com" else {"data": [{"id": "plain"}]}
        return httpx.Response(200, json=payload)

    client, async_client = httpx.Client, httpx.AsyncClient
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(httpx, "Client", lambda **kw: client(transport=transport, **kw))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: async_client(transport=transport, **kw))
    return requests


def apply(services: SharedServices, **overrides: Any) -> int:
    return codex_apply.apply_codex_credentials(
        services, services.paths, {**CREDENTIALS, **overrides}
    )


def test_normalize_preserves_order_and_capabilities() -> None:
    models = codex_catalog.normalize_codex_catalog(CATALOG)
    assert [m["id"] for m in models] == ["model-first", "model-second"]
    assert models[0]["name"] == "First model"
    assert models[0]["input"] == ["text", "image"]
    assert models[0]["context_window"] == 500000
    assert models[0]["api_mode"] == "responses"
    assert models[1]["input"] == ["text"]


def test_chatgpt_catalog_does_not_require_platform_api_support() -> None:
    models = codex_catalog.normalize_codex_catalog(
        {"models": [{"slug": "chatgpt-model", "visibility": "list", "supported_in_api": False}]}
    )
    assert [m["id"] for m in models] == ["chatgpt-model"]


@pytest.mark.parametrize("payload", [{}, {"models": {}}, {"models": [{"slug": " "}]}])
@pytest.mark.parametrize("locale,fragment", [("en", "Invalid Codex"), ("zh", "格式无效")])
def test_malformed_catalog_is_localized(payload: Any, locale: str, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        codex_catalog.normalize_codex_catalog(payload, locale=locale)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://chatgpt.com.example.org/backend-api/codex",
        "https://example.org/chatgpt.com/backend-api/codex",
        "http://chatgpt.com/backend-api/codex",
        "https://chatgpt.com/backend-api/codex?redirect=1",
        "https://user@chatgpt.com/backend-api/codex",
        "https://chatgpt.com:invalid/backend-api/codex",
        "https://[invalid",
    ],
)
def test_unrelated_or_invalid_endpoint_is_not_codex(url: str) -> None:
    assert not codex_catalog.is_codex_endpoint(url)


async def test_catalog_wire_contract_and_openai_isolation(catalog_http, monkeypatch) -> None:
    monkeypatch.setattr(codex_catalog, "CODEX_ATTRIBUTION_VERSION", "test-catalog-version")
    sync_models = codex_catalog.fetch_codex_catalog("test-token", "test-account")
    result = await probe.fetch_openai_compatible_models(
        base_url=CODEX_BASE_URL + "/",
        api_key="test-token",
        extra_headers={"chatgpt-account-id": "test-account"},
    )
    ordinary = await probe.fetch_openai_compatible_models(
        base_url="https://api.openai.com/v1", api_key="test-token"
    )
    assert result == {"ok": True, "models": sync_models}
    assert ordinary == {"ok": True, "models": [{"id": "plain", "name": "plain"}]}
    for request in catalog_http[:2]:
        assert request.url.path == "/backend-api/codex/models"
        assert request.url.params["client_version"] == "test-catalog-version"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["chatgpt-account-id"] == "test-account"
    assert "client_version" not in catalog_http[2].url.params


def test_first_login_uses_catalog_not_fixed_models(services, catalog_http) -> None:
    pid = apply(services)
    row = services.provider_repo.get(pid)
    assert row.get_models() == codex_catalog.normalize_codex_catalog(CATALOG)
    assert services.settings_repo.get_active_model() == ("openai-codex", "model-first")
    assert (
        json.loads((services.paths.root / "codex_oauth.json").read_text(encoding="utf-8"))
        == CREDENTIALS
    )


def test_relogin_keeps_available_choice_and_user_options(services, catalog_http) -> None:
    pid = apply(services)
    row = services.provider_repo.get(pid)
    models = row.get_models()
    models[0]["enabled"] = False
    models[1].update(max_output_tokens=4096, context_window=123, input=["image"])
    models.append({"id": "retired", "name": "Retired"})
    extra = json.loads(row.extra_json)
    extra["stream_usage"] = True
    services.provider_repo.update(pid, models_json=json.dumps(models), extra_json=json.dumps(extra))
    services.settings_repo.set_active_model("openai-codex", "model-second")
    assert apply(services, access="renewed-test-access") == pid
    updated = services.provider_repo.get(pid)
    assert updated.api_key == "renewed-test-access"
    assert [m["id"] for m in updated.get_models()] == ["model-first", "model-second"]
    assert updated.get_models()[0]["enabled"] is False
    assert updated.get_models()[1]["max_output_tokens"] == 4096
    assert updated.get_models()[1]["input"] == ["text"]
    assert json.loads(updated.extra_json)["stream_usage"] is True
    assert services.settings_repo.get_active_model() == ("openai-codex", "model-second")


def test_changed_account_revalidates_choice_and_options(services, catalog_http) -> None:
    pid = apply(services)
    services.settings_repo.set_active_model("openai-codex", "model-second")
    services.provider_repo.update(
        pid, models_json=json.dumps([{"id": "model-first", "enabled": False}])
    )
    apply(services, account_id="test-account-two")
    row = services.provider_repo.get(pid)
    assert row.get_models()[0]["enabled"] is True
    assert json.loads(row.extra_json)["headers"]["chatgpt-account-id"] == "test-account-two"
    assert services.settings_repo.get_active_model() == ("openai-codex", "model-first")


def test_invalid_selection_falls_back_and_set_active_false_is_respected(
    services, catalog_http
) -> None:
    apply(services)
    services.settings_repo.set_active_model("openai-codex", "retired")
    apply(services)
    assert services.settings_repo.get_active_model() == ("openai-codex", "model-first")
    services.settings_repo.set_active_model("another-provider", "another-model")
    codex_apply.apply_codex_credentials(services, services.paths, CREDENTIALS, set_active=False)
    assert services.settings_repo.get_active_model() == ("another-provider", "another-model")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"models": []}),
        httpx.Response(200, json={"wrong": []}),
    ],
)
def test_discovery_failure_preserves_provider_token_and_selection(
    services, catalog_http, response
) -> None:
    pid = apply(services)
    before = services.provider_repo.get(pid)
    token = (services.paths.root / "codex_oauth.json").read_bytes()
    active = services.settings_repo.get_active_model()
    response.request = httpx.Request("GET", CODEX_BASE_URL + "/models")
    with (
        httpx.Client() as client,
        patch.object(type(client), "get", return_value=response),
        pytest.raises((ValueError, httpx.HTTPStatusError)),
    ):
        apply(services, access="must-not-be-saved")
    assert services.provider_repo.get(pid) == before
    assert (services.paths.root / "codex_oauth.json").read_bytes() == token
    assert services.settings_repo.get_active_model() == active


def test_probe_uses_harness_codex_responses_adapter() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    row = probe.make_probe_provider_row(
        name="openai-codex",
        kind="openai",
        api_key="test-token",
        base_url=CODEX_BASE_URL,
        model_id="model-first",
    )
    model = probe.build_probe_chat_model(row)
    assert model.use_responses_api and model.streaming
    assert model.store is False
    payload = model._get_request_payload(
        [SystemMessage(content="Test instruction."), HumanMessage(content="ping")]
    )
    assert "Test instruction." in payload["instructions"]
    assert not any(m.get("role") == "system" for m in payload["input"])


async def test_device_poll_discovers_off_event_loop_and_reports_failure(
    services, monkeypatch
) -> None:
    from octop.api.routers import providers

    event_loop_thread = threading.get_ident()

    def discover(*args):
        assert threading.get_ident() != event_loop_thread
        raise ValueError("catalog unavailable")

    monkeypatch.setattr(
        providers, "poll_device_token", lambda *args: ("test-code", "test-verifier")
    )
    monkeypatch.setattr(providers, "exchange_device_code", lambda *args: CREDENTIALS)
    monkeypatch.setattr(codex_apply, "fetch_codex_catalog", discover)
    await providers._run_codex_device_poll(
        SimpleNamespace(services=services, app_runtime=None),
        state_id="test-state",
        device_auth_id="test-device",
        user_code="test-code",
        interval_s=0,
        user_id=1,
    )
    pending = json.loads(services.settings_repo.get("codex_oauth.pending.test-state"))
    assert pending["status"] == "error"
    assert pending["error"] == "catalog unavailable"
    assert services.provider_repo.get_by_name("openai-codex") is None
    assert not (services.paths.root / "codex_oauth.json").exists()
