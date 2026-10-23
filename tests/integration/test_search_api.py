"""Integration tests for POST /api/search/{provider_id}/test."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch


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


async def test_search_test_deepseek_requires_key(env: Any) -> None:
    c, _srv, auth = env
    r = await c.post(
        "/api/search/deepseek/test",
        headers=auth,
        json={"env_vars": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["provider_id"] == "deepseek"
    assert body["error_type"] == "invalid_config"
    assert "DEEPSEEK_API_KEY" in body["error"]


async def test_search_test_deepseek_ok(env: Any) -> None:
    c, _srv, auth = env
    with patch(
        "octop.infra.utils.search_probe._deepseek",
        new=AsyncMock(
            return_value={
                "success": True,
                "result_count": 1,
                "message": "DeepSeek search test successful",
            }
        ),
    ):
        r = await c.post(
            "/api/search/deepseek/test",
            headers=auth,
            json={"env_vars": {"DEEPSEEK_API_KEY": "sk-ds"}},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["provider_id"] == "deepseek"
    assert body["result_count"] == 1


async def test_import_deepseek_model_key_requires_auth(env: Any) -> None:
    c, _srv, _auth = env
    r = await c.post("/api/search/deepseek/import-model-key")
    assert r.status_code == 401


async def test_import_deepseek_model_key_missing_provider(env: Any) -> None:
    c, _srv, auth = env
    r = await c.post("/api/search/deepseek/import-model-key", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


async def test_import_deepseek_model_key_copies_key(
    env: Any,
    monkeypatch: Any,
) -> None:
    from octop.infra.utils.env_file import env_file_path, load_env_file

    # The endpoint mirrors the key into the process env; let monkeypatch
    # restore it so other tests do not inherit the DeepSeek provider.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder")
    c, srv, auth = env
    srv.services.provider_repo.create(
        name="DeepSeek",
        kind="openai",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-deepseek-model",
    )

    r = await c.post("/api/search/deepseek/import-model-key", headers=auth)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["provider_name"] == "DeepSeek"
    assert body["env_key"] == "DEEPSEEK_API_KEY"
    saved = load_env_file(env_file_path(srv.paths.root))
    assert saved["DEEPSEEK_API_KEY"] == "sk-deepseek-model"


async def test_import_deepseek_model_key_copies_custom_base_url(
    env: Any,
    monkeypatch: Any,
) -> None:
    from octop.infra.utils.env_file import env_file_path, load_env_file

    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder")
    c, srv, auth = env
    srv.services.provider_repo.create(
        name="DeepSeek Relay",
        kind="openai",
        base_url="https://relay.example.test/v1",
        api_key="sk-relay",
    )

    r = await c.post("/api/search/deepseek/import-model-key", headers=auth)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["base_url"] == "https://relay.example.test/v1"
    saved = load_env_file(env_file_path(srv.paths.root))
    assert saved["DEEPSEEK_API_KEY"] == "sk-relay"
    assert saved["DEEPSEEK_SEARCH_BASE_URL"] == "https://relay.example.test/v1"
