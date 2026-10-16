"""Integration tests for custom search settings and built-in provider probes."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from octop.infra.utils.env_file import SEARCH_ENV_KEYS
from tests.support.app import octop_client, write_octop_config
from tests.support.auth import create_user


@pytest.fixture(autouse=True)
def isolate_search_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in SEARCH_ENV_KEYS:
        monkeypatch.setenv(key, "")


def _custom_provider(**changes: Any) -> dict[str, Any]:
    return {
        "id": "local-search",
        "name": "Local Search",
        "url": "https://search.example.com/search",
        "method": "GET",
        "headers": {"Authorization": "Bearer {api_key}"},
        "params": {"q": "{query}", "limit": "{max_results}"},
        "body": {},
        "results_path": "results",
        "title_path": "title",
        "url_path": "url",
        "content_path": "content",
        **changes,
    }


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/search/custom", None),
        ("PUT", "/api/search/custom", {"providers": [], "active_provider_id": None}),
        ("POST", "/api/search/custom/test", {"provider": _custom_provider()}),
    ],
)
async def test_custom_search_requires_auth_and_search_permission(
    env: Any, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    client, _srv, admin_auth = env
    response = await client.request(method, path, json=payload)
    assert response.status_code == 401

    user_auth = await create_user(client, admin_auth, username="no-search", permissions=[])
    response = await client.request(method, path, headers=user_auth, json=payload)
    assert response.status_code == 403


async def test_custom_search_replaces_engines_and_preserves_write_only_keys(env: Any) -> None:
    client, srv, auth = env
    registry = srv.app_runtime.agent_registry
    initial = await client.get("/api/search/custom", headers=auth)
    assert initial.status_code == 200
    assert initial.json() == {
        "providers": [],
        "active_provider_id": None,
        "configured_preset_ids": [],
    }

    provider = _custom_provider(api_key="custom-write-only-key")
    secondary = _custom_provider(id="second", name="Second", api_key="second-secret")
    with patch.object(registry, "reload_all", new=AsyncMock()) as reload_all:
        saved = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [provider, secondary], "active_provider_id": "local-search"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["active_provider_id"] == "local-search"
        assert all(item["api_key_set"] for item in saved.json()["providers"])
        assert all("api_key" not in item for item in saved.json()["providers"])
        assert "custom-write-only-key" not in saved.text
        assert "second-secret" not in saved.text

        provider.pop("api_key")
        provider["name"] = "Renamed Search"
        updated = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [provider], "active_provider_id": "local-search"},
        )
        assert updated.status_code == 200, updated.text
        assert len(updated.json()["providers"]) == 1
        assert updated.json()["providers"][0]["name"] == "Renamed Search"
        assert updated.json()["providers"][0]["api_key_set"] is True

        provider["api_key"] = None
        kept = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [provider], "active_provider_id": None},
        )
        assert kept.status_code == 200, kept.text
        assert kept.json()["providers"][0]["api_key_set"] is True
        assert kept.json()["active_provider_id"] is None

        provider["api_key"] = ""
        provider["headers"] = {}
        cleared = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [provider], "active_provider_id": None},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["providers"][0]["api_key_set"] is False

        deleted = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [], "active_provider_id": None},
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {
            "providers": [],
            "active_provider_id": None,
            "configured_preset_ids": [],
        }
        assert reload_all.await_count == 5

    loaded = await client.get("/api/search/custom", headers=auth)
    assert loaded.json() == deleted.json()


async def test_custom_search_permission_allows_regular_user(env: Any) -> None:
    client, _srv, auth = env
    user_auth = await create_user(client, auth, username="search-user", permissions=["search"])
    response = await client.get("/api/search/custom", headers=user_auth)
    assert response.status_code == 200


async def test_search_source_switching_preserves_credentials_and_custom_engines(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, srv, auth = env
    for key in SEARCH_ENV_KEYS:
        monkeypatch.setenv(key, "")
    preset_keys = {
        "TAVILY_API_KEY": "tavily-switch-test",
        "BRAVE_API_KEY": "brave-switch-test",
        "GOOGLE_API_KEY": "google-switch-test",
        "GOOGLE_CSE_ID": "google-cse-switch-test",
        "MOONSHOT_API_KEY": "kimi-switch-test",
    }
    with patch.object(srv.app_runtime.agent_registry, "reload_all", new=AsyncMock()):
        response = await client.put("/api/envs", headers=auth, json=preset_keys)
        assert response.status_code == 200, response.text
        initial = await client.get("/api/search/custom", headers=auth)
        assert initial.json()["active_provider_id"] == "preset:tavily"
        configured_presets = ["tavily", "brave", "google", "kimi"]
        assert initial.json()["configured_preset_ids"] == configured_presets

        brave = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [], "active_provider_id": "preset:brave"},
        )
        assert brave.status_code == 200, brave.text
        assert brave.json() == {
            "providers": [],
            "active_provider_id": "preset:brave",
            "configured_preset_ids": configured_presets,
        }
        refreshed = await client.get("/api/search/custom", headers=auth)
        assert refreshed.json() == brave.json()

        builtin = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [], "active_provider_id": None},
        )
        assert builtin.status_code == 200, builtin.text
        assert builtin.json() == {
            "providers": [],
            "active_provider_id": None,
            "configured_preset_ids": configured_presets,
        }
        refreshed = await client.get("/api/search/custom", headers=auth)
        assert refreshed.json() == builtin.json()

        custom = await client.put(
            "/api/search/custom",
            headers=auth,
            json={
                "providers": [_custom_provider(api_key="custom-switch-test")],
                "active_provider_id": "local-search",
            },
        )
        assert custom.status_code == 200, custom.text
        assert custom.json()["active_provider_id"] == "local-search"
        assert custom.json()["providers"][0]["api_key_set"] is True
        refreshed = await client.get("/api/search/custom", headers=auth)
        assert refreshed.json() == custom.json()

        provider = custom.json()["providers"][0]
        preset = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [provider], "active_provider_id": "preset:tavily"},
        )
        assert preset.status_code == 200, preset.text
        assert preset.json()["active_provider_id"] == "preset:tavily"
        assert preset.json()["providers"] == custom.json()["providers"]
        refreshed = await client.get("/api/search/custom", headers=auth)
        assert refreshed.json() == preset.json()

        envs = await client.get("/api/envs", headers=auth)
        assert {item["key"]: item["value"] for item in envs.json()} == preset_keys
        assert all(value not in preset.text for value in preset_keys.values())
        assert "custom-switch-test" not in preset.text


async def test_process_environment_credentials_remain_available_after_switching_off(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, srv, auth = env
    monkeypatch.setenv("TAVILY_API_KEY", "system-only-secret")
    envs = await client.get("/api/envs", headers=auth)
    assert envs.json() == []
    initial = await client.get("/api/search/custom", headers=auth)
    assert initial.json()["configured_preset_ids"] == ["tavily"]
    assert initial.json()["active_provider_id"] == "preset:tavily"
    with patch.object(srv.app_runtime.agent_registry, "reload_all", new=AsyncMock()):
        for selected in (None, "preset:tavily", None, "preset:tavily"):
            saved = await client.put(
                "/api/search/custom",
                headers=auth,
                json={"providers": [], "active_provider_id": selected},
            )
            assert saved.status_code == 200, saved.text
            assert saved.json()["active_provider_id"] == selected
            assert saved.json()["configured_preset_ids"] == ["tavily"]
            assert "system-only-secret" not in saved.text
            refreshed = await client.get("/api/search/custom", headers=auth)
            assert refreshed.json() == saved.json()
    assert (await client.get("/api/envs", headers=auth)).json() == []


@pytest.mark.parametrize("preset", ["tavily", "brave", "google", "kimi"])
async def test_search_source_rejects_unconfigured_preset(
    env: Any, monkeypatch: pytest.MonkeyPatch, preset: str
) -> None:
    client, srv, auth = env
    for key in SEARCH_ENV_KEYS:
        monkeypatch.setenv(key, "")
    with patch.object(srv.app_runtime.agent_registry, "reload_all", new=AsyncMock()) as reload_all:
        response = await client.put(
            "/api/search/custom",
            headers={**auth, "Accept-Language": "zh"},
            json={"providers": [], "active_provider_id": f"preset:{preset}"},
        )
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "SLASH_BAD_ARGS"
    assert error["details"]["reason"] == "请先配置该搜索引擎的凭证，再启用。"
    reload_all.assert_not_awaited()
    refreshed = await client.get("/api/search/custom", headers=auth)
    assert refreshed.json() == {
        "providers": [],
        "active_provider_id": None,
        "configured_preset_ids": [],
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"providers": [_custom_provider(), _custom_provider()], "active_provider_id": None},
        {"providers": [_custom_provider()], "active_provider_id": "missing"},
    ],
)
async def test_custom_search_rejects_invalid_selection_without_saving(
    env: Any, payload: dict[str, Any]
) -> None:
    client, srv, auth = env
    with patch.object(srv.app_runtime.agent_registry, "reload_all", new=AsyncMock()) as reload_all:
        response = await client.put("/api/search/custom", headers=auth, json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "SLASH_BAD_ARGS"
    reload_all.assert_not_awaited()
    loaded = await client.get("/api/search/custom", headers=auth)
    assert loaded.json() == {
        "providers": [],
        "active_provider_id": None,
        "configured_preset_ids": [],
    }


@pytest.mark.parametrize(
    ("changes", "status"),
    [
        ({"method": "DELETE"}, 422),
        ({"url": "file:///tmp/search"}, 400),
        ({"params": {"q": 123}}, 422),
    ],
)
async def test_custom_search_rejects_invalid_provider(
    env: Any, changes: dict[str, Any], status: int
) -> None:
    client, _srv, auth = env
    response = await client.put(
        "/api/search/custom",
        headers=auth,
        json={"providers": [_custom_provider(**changes)], "active_provider_id": None},
    )
    assert response.status_code == status, response.text


async def test_custom_search_validation_reason_is_localized_without_leaking_key(env: Any) -> None:
    client, srv, auth = env
    provider = _custom_provider(params={"q": "static"}, api_key="invalid-config-secret")
    with patch.object(srv.app_runtime.agent_registry, "reload_all", new=AsyncMock()) as reload_all:
        response = await client.put(
            "/api/search/custom",
            headers={**auth, "Accept-Language": "zh"},
            json={"providers": [provider], "active_provider_id": "local-search"},
        )
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "SLASH_BAD_ARGS"
    assert (
        error["details"]["reason"] == "请在 GET 查询参数或 POST JSON 请求体中包含 {query} 占位符。"
    )
    assert "invalid-config-secret" not in response.text
    reload_all.assert_not_awaited()


async def test_custom_search_api_docs_have_readable_schemas(tmp_octop_home: Path) -> None:
    write_octop_config(tmp_octop_home, enable_api_docs=True)
    async with octop_client(tmp_octop_home) as (client, _srv):
        page = await client.get("/api/docs")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "scalar" in page.text.lower()
        assert "/api/openapi.json" in page.text
        response = await client.get("/api/openapi.json")
        assert response.status_code == 200
        schema = response.json()
    for path, method in [
        ("/api/search/custom", "get"),
        ("/api/search/custom", "put"),
        ("/api/search/custom/test", "post"),
    ]:
        operation = schema["paths"][path][method]
        assert operation["summary"]
        assert operation["description"]
        assert "$ref" in operation["responses"]["200"]["content"]["application/json"]["schema"]
        if method != "get":
            assert "$ref" in operation["requestBody"]["content"]["application/json"]["schema"]


async def test_custom_search_probe_uses_draft_without_saving(env: Any) -> None:
    client, _srv, auth = env
    provider = _custom_provider(api_key="draft-search-key", method="POST", body={"q": "{query}"})
    with patch(
        "octop.infra.agents.settings.search.CustomSearchSettingsStore.probe",
        new=AsyncMock(
            return_value={
                "success": True,
                "provider_id": "local-search",
                "response_time_ms": 5,
                "result_count": 2,
            }
        ),
    ) as probe:
        response = await client.post(
            "/api/search/custom/test",
            headers={**auth, "Accept-Language": "zh"},
            json={"provider": provider},
        )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert response.json()["result_count"] == 2
    assert "draft-search-key" not in response.text
    assert probe.await_args.args[0].api_key == "draft-search-key"
    assert probe.await_args.args[0].method == "POST"
    assert probe.await_args.kwargs == {"locale": "zh"}
    loaded = await client.get("/api/search/custom", headers=auth)
    assert loaded.json() == {
        "providers": [],
        "active_provider_id": None,
        "configured_preset_ids": [],
    }


async def test_custom_search_probe_reuses_saved_key_without_overwriting_settings(env: Any) -> None:
    client, srv, auth = env
    provider = _custom_provider(api_key="stored-probe-key")
    with patch.object(srv.app_runtime.agent_registry, "reload_all", new=AsyncMock()):
        saved = await client.put(
            "/api/search/custom",
            headers=auth,
            json={"providers": [provider], "active_provider_id": "local-search"},
        )
    assert saved.status_code == 200, saved.text
    provider.update(name="Unsaved Name", method="POST", body={"query": "{query}"}, api_key=None)
    with patch(
        "octop.infra.agents.settings.search._search",
        new=AsyncMock(
            return_value=[{"title": "Result", "url": "https://example.com", "content": ""}]
        ),
    ) as search:
        response = await client.post(
            "/api/search/custom/test", headers=auth, json={"provider": provider}
        )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert response.json()["result_count"] == 1
    assert "stored-probe-key" not in response.text
    assert search.await_args.args[0].name == "Unsaved Name"
    assert search.await_args.args[0].method == "POST"
    assert search.await_args.args[1] == "stored-probe-key"
    loaded = await client.get("/api/search/custom", headers=auth)
    assert loaded.json() == saved.json()


async def test_search_test_requires_auth(env: Any) -> None:
    c, _srv, _auth = env
    r = await c.post("/api/search/tavily/test", json={"env_vars": {}})
    assert r.status_code == 401


async def test_search_test_unknown_provider(env: Any) -> None:
    c, _srv, auth = env
    r = await c.post(
        "/api/search/nope/test",
        headers=auth,
        json={"env_vars": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["provider_id"] == "nope"
    assert body["error_type"] == "invalid_config"


async def test_search_test_tavily_ok(env: Any) -> None:
    c, _srv, auth = env
    with patch(
        "octop.infra.utils.search_probe._tavily",
        new=AsyncMock(
            return_value={
                "success": True,
                "result_count": 1,
                "message": "ok",
            }
        ),
    ):
        r = await c.post(
            "/api/search/tavily/test",
            headers=auth,
            json={"env_vars": {"TAVILY_API_KEY": "tvly-x"}},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["provider_id"] == "tavily"
    assert body["result_count"] == 1
    assert isinstance(body["response_time_ms"], int)


async def test_preset_card_probe_uses_saved_credentials(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _srv, auth = env
    monkeypatch.setenv("BRAVE_API_KEY", "system-card-secret")
    with patch(
        "octop.infra.utils.search_probe._brave",
        new=AsyncMock(return_value={"success": True, "result_count": 1}),
    ) as probe:
        response = await client.post(
            "/api/search/brave/test",
            headers=auth,
            json={"env_vars": {}, "use_saved_credentials": True},
        )
    assert response.status_code == 200 and response.json()["success"] is True
    assert probe.await_args.args[1] == "system-card-secret"
    assert "system-card-secret" not in response.text
    assert (await client.get("/api/envs", headers=auth)).json() == []
