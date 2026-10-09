"""Custom search settings and HTTP requests used by the actual agent tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from octop.infra.agents.settings.search import (
    CustomSearchProviderUpdate,
    CustomSearchSettingsStore,
    CustomSearchSettingsUpdate,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import OctopError


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CustomSearchSettingsStore:
    for key in (
        "TAVILY_API_KEY",
        "BRAVE_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CSE_ID",
        "MOONSHOT_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return CustomSearchSettingsStore(settings_repo=SettingsRepo(db), secret_repo=SecretRepo(db))


def provider(**overrides: Any) -> CustomSearchProviderUpdate:
    return CustomSearchProviderUpdate(
        **{
            "id": "custom-one",
            "name": "My Search",
            "url": "https://search.example/search",
            **overrides,
        }
    )


def save(store: CustomSearchSettingsStore, item: CustomSearchProviderUpdate) -> None:
    store.save(CustomSearchSettingsUpdate(providers=[item], active_provider_id=item.id))


def mock_http(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "octop.infra.agents.settings.search.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs),
    )


async def test_keys_are_encrypted_retained_cleared_and_removed(
    store: CustomSearchSettingsStore,
) -> None:
    save(store, provider(api_key="secret-example"))
    raw = store._settings.get("custom_search_providers")
    blob = store._secrets.get("custom_search_credentials")
    assert "secret-example" not in (raw or "")
    assert blob is not None and b"secret-example" not in blob
    assert store.load().providers[0].api_key_set
    save(store, provider(name="Renamed"))
    assert store._credentials() == {"custom-one": "secret-example"}
    save(store, provider(api_key=""))
    assert store._credentials() == {}
    assert not store.load().providers[0].api_key_set
    save(store, provider(api_key="new-secret"))
    store.save(CustomSearchSettingsUpdate(providers=[], active_provider_id=None))
    assert store.load().providers == []
    assert store._credentials() == {}
    assert store.build_tool() is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": "file:///search"},
        {"url": "https://user:password@search.example"},
        {"url": "https://search.example:invalid/search"},
        {"params": {"q": "static"}},
        {"method": "POST", "params": {}, "body": {"q": "static"}},
        {"headers": {"Authorization": "Bearer {api_key}"}},
    ],
)
def test_invalid_provider_does_not_replace_settings(
    store: CustomSearchSettingsStore, overrides: dict[str, Any]
) -> None:
    save(store, provider(api_key="retained-secret"))
    old = store.load()
    with pytest.raises(OctopError):
        save(store, provider(id="invalid", **overrides))
    assert store.load() == old
    assert store._credentials() == {"custom-one": "retained-secret"}


def test_duplicate_and_missing_active_ids_are_rejected(store: CustomSearchSettingsStore) -> None:
    for update in (
        CustomSearchSettingsUpdate(
            providers=[provider(), provider()], active_provider_id="custom-one"
        ),
        CustomSearchSettingsUpdate(providers=[provider()], active_provider_id="missing"),
    ):
        with pytest.raises(OctopError):
            store.save(update)
    assert store.load().providers == []


def test_get_ignores_unused_body_and_post_can_put_query_in_params(
    store: CustomSearchSettingsStore,
) -> None:
    save(store, provider(body={"key": "{api_key}"}))
    save(store, provider(method="POST", body={"static": True}))
    assert store.build_tool() is not None


async def test_runtime_get_maps_nested_results_and_preserves_literal_query_tokens(
    store: CustomSearchSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = '中文 & "quotes" {api_key}'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.params["q"] == query
        assert request.url.params["count"] == "1"
        assert request.headers["x-api-key"] == "private-secret"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "hits": [
                            {
                                "headline": "Title",
                                "link": "https://result.example",
                                "snippet": "Text",
                            },
                            {"headline": "Second", "link": "https://second.example"},
                        ]
                    }
                ]
            },
        )

    mock_http(monkeypatch, handler)
    save(
        store,
        provider(
            api_key="private-secret",
            headers={"X-API-Key": "{api_key}"},
            params={"q": "{query}", "count": "{max_results}"},
            results_path="data.0.hits",
            title_path="headline",
            url_path="link",
            content_path="snippet",
        ),
    )
    tool = store.build_tool()
    assert tool is not None
    result = json.loads(await tool.ainvoke({"query": query, "max_results": 1}))
    assert result == {
        "results": [{"title": "Title", "url": "https://result.example", "content": "Text"}]
    }


async def test_runtime_post_renders_nested_json_and_root_array(
    store: CustomSearchSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "request": {"query": "hello", "limit": 2},
            "options": ["prefix hello", True],
        }
        return httpx.Response(200, json=[{"link": "https://result.example"}])

    mock_http(monkeypatch, handler)
    save(
        store,
        provider(
            method="POST",
            params={},
            body={
                "request": {"query": "{query}", "limit": "{max_results}"},
                "options": ["prefix {query}", True],
            },
            results_path="",
            title_path="",
            url_path="link",
            content_path="",
        ),
    )
    tool = store.build_tool()
    assert tool is not None
    result = json.loads(await tool.ainvoke({"query": "hello", "max_results": 2}))
    assert result["results"][0] == {
        "title": "https://result.example",
        "url": "https://result.example",
        "content": "",
    }


@pytest.mark.parametrize(
    ("status", "payload", "error_type"),
    [
        (401, {"message": "secret-example"}, "auth_error"),
        (500, {"message": "secret-example"}, "network_error"),
        (200, {"wrong": []}, "invalid_config"),
        (200, {"results": [{"title": "No URL"}]}, "invalid_config"),
        (200, {"results": [{"url": "https://result.example", "content": {}}]}, "invalid_config"),
    ],
)
async def test_probe_errors_are_localized_without_echoing_credentials(
    store: CustomSearchSettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    payload: Any,
    error_type: str,
) -> None:
    mock_http(monkeypatch, lambda request: httpx.Response(status, json=payload))
    result = await store.probe(provider(api_key="secret-example"), locale="zh")
    assert not result["success"]
    assert result["error_type"] == error_type
    assert "secret-example" not in result["error"]
    assert any("\u4e00" <= character <= "\u9fff" for character in result["error"])
    assert store.load().providers == []


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_probe_network_errors_do_not_echo_request_url(
    store: CustomSearchSettingsStore,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[httpx.HTTPError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure("https://search.example?key=secret-example", request=request)

    mock_http(monkeypatch, handler)
    result = await store.probe(provider())
    assert not result["success"]
    assert result["error_type"] in {"timeout", "network_error"}
    assert "secret-example" not in result["error"]


async def test_probe_saved_key_and_empty_results_without_persisting_changes(
    store: CustomSearchSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    save(store, provider(api_key="stored-secret"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer stored-secret"
        return httpx.Response(200, json={"results": []})

    mock_http(monkeypatch, handler)
    result = await store.probe(
        provider(name="Unsaved", headers={"Authorization": "Bearer {api_key}"})
    )
    assert result["success"] and result["result_count"] == 0
    assert store.load().providers[0].name == "My Search"
    assert "api_key" not in store.load().providers[0].model_dump()


async def test_invalid_json_returns_failure(
    store: CustomSearchSettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_http(monkeypatch, lambda request: httpx.Response(200, text="<html>not JSON</html>"))
    result = await store.probe(provider())
    assert not result["success"] and result["error_type"] == "unknown"


async def test_invalid_unicode_header_is_a_config_error_for_probe_and_runtime(
    store: CustomSearchSettingsStore,
) -> None:
    item = provider(headers={"X-Token": "中文"})
    result = await store.probe(item, locale="zh")
    assert result["success"] is False and result["error_type"] == "invalid_config"
    assert "ASCII" in result["error"]
    save(store, item)
    tool = store.build_tool()
    assert tool is not None
    result = json.loads(await tool.ainvoke({"query": "hello"}))
    assert "ASCII" in result["error"]


def test_old_automatic_selection_is_preserved_until_switch_is_used(
    store: CustomSearchSettingsStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-saved")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-saved")
    assert store.load().active_provider_id == "preset:tavily"
    assert store.load().configured_preset_ids == ["tavily", "brave"]
    assert store.harness_search_policy() == ["tavily"]
    store._settings.set(
        "custom_search_providers", json.dumps({"providers": [], "active_provider_id": None})
    )
    assert store.load().active_provider_id == "preset:tavily"
    store.save(CustomSearchSettingsUpdate(providers=[], active_provider_id=None))
    assert store.load().active_provider_id is None
    assert store.harness_search_policy() == ["searchfree"]
    assert store.load().configured_preset_ids == ["tavily", "brave"]
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-new")
    assert store.load().active_provider_id is None


def test_selected_preset_survives_refresh_and_missing_key_falls_back_to_builtin(
    store: CustomSearchSettingsStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-saved")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-saved")
    store.save(CustomSearchSettingsUpdate(providers=[], active_provider_id="preset:brave"))
    assert store.load().active_provider_id == "preset:brave"
    assert store.harness_search_policy() == ["brave"]
    monkeypatch.delenv("BRAVE_API_KEY")
    assert store.load().active_provider_id is None
    assert store.harness_search_policy() == ["searchfree"]


@pytest.mark.parametrize("preset", ["tavily", "brave", "google", "kimi"])
def test_unconfigured_presets_cannot_be_enabled(
    store: CustomSearchSettingsStore,
    preset: str,
) -> None:
    with pytest.raises(OctopError) as error:
        store.save(
            CustomSearchSettingsUpdate(providers=[], active_provider_id=f"preset:{preset}"),
            locale="zh",
        )
    assert error.value.details["reason"] == "请先配置该搜索引擎的凭证，再启用。"
    assert store.load().active_provider_id is None


def test_custom_provider_can_share_display_id_with_preset(
    store: CustomSearchSettingsStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = provider(id="brave")
    save(store, item)
    assert store.build_tool() is not None
    monkeypatch.setenv("BRAVE_API_KEY", "brave-saved")
    store.save(CustomSearchSettingsUpdate(providers=[item], active_provider_id="preset:brave"))
    assert store.build_tool() is None
    assert store.harness_search_policy() == ["brave"]
