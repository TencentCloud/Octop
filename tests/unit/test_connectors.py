"""Unit tests for connector builder and repo."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.builder import (
    build_http_mcp_spec,
    mcp_server_name,
    normalize_weiyun_mcp_token,
    validate_create_credentials,
)
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.utils.ulid import new_ulid


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def test_mcp_server_name_format():
    iid = new_ulid()
    assert mcp_server_name("tencent-docs", iid) == f"tencent-docs__{iid}"


def test_validate_tencent_token():
    payload = validate_create_credentials("tencent-docs", {"token": "abc"})
    assert payload["token"] == "abc"


def test_build_tencent_remote_spec():
    entry = get_catalog_entry("tencent-docs")
    assert entry is not None
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"token": "tok"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "http"
    assert spec["headers"]["Authorization"] == "tok"
    assert spec["tool_arg_aliases"]["manage.search_file"]["query"] == "search_key"


def test_build_weiyun_remote_spec():
    entry = get_catalog_entry("tencent-weiyun")
    assert entry is not None
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"token": "wy-token"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "http"
    assert spec["url"] == "https://www.weiyun.com/api/v3/mcpserver"
    assert spec["headers"]["WyHeader"] == "mcp_token=wy-token"
    assert spec["headers"]["Accept"] == "application/json, text/event-stream"
    assert "weiyun.list" in spec["allowed_tools"]


def test_normalize_weiyun_mcp_token():
    assert normalize_weiyun_mcp_token("abc123") == "abc123"
    assert normalize_weiyun_mcp_token("mcp_token=abc123") == "abc123"
    assert normalize_weiyun_mcp_token('export WEIYUN_MCP_TOKEN="abc123"') == "abc123"
    assert normalize_weiyun_mcp_token("WyHeader: mcp_token=abc123") == "abc123"


@pytest.mark.asyncio
async def test_prepare_probe_credentials_allows_empty_weiyun_token():
    from octop.infra.connectors.probe import prepare_probe_credentials

    creds = await prepare_probe_credentials("tencent-weiyun", {})
    assert creds == {}

    creds = await prepare_probe_credentials(
        "tencent-weiyun",
        {"token": "mcp_token=real-token"},
    )
    assert creds == {"token": "real-token"}


def test_validate_weiyun_token_normalizes_prefix():
    payload = validate_create_credentials(
        "tencent-weiyun",
        {"token": "mcp_token=wy-token"},
    )
    assert payload == {"token": "wy-token"}


def test_build_notion_remote_spec():
    entry = get_catalog_entry("notion")
    assert entry is not None
    assert entry.oauth_issuer == "https://mcp.notion.com"
    assert entry.mcp_url == "https://mcp.notion.com/mcp"
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"access_token": "ntn_xxx"},
        config=OctopConfig(),
    )
    assert spec["url"] == "https://mcp.notion.com/mcp"
    assert spec["headers"]["Authorization"] == "Bearer ntn_xxx"
    assert spec["headers"]["Accept"] == "application/json, text/event-stream"
    assert spec["headers"]["User-Agent"] == "octop-connector/0.1"


def test_mcp_oauth_remote_catalog_helpers():
    from octop.infra.connectors.catalog import (
        get_mcp_oauth_remote,
        is_mcp_oauth_remote,
        mcp_oauth_remote_kinds,
    )
    from octop.infra.connectors.oauth.mcp import resource_for_kind

    notion = get_catalog_entry("notion")
    ardot = get_catalog_entry("tencent-ardot")
    dida = get_catalog_entry("dida365")
    assert notion is not None and ardot is not None and dida is not None
    assert is_mcp_oauth_remote(notion)
    assert is_mcp_oauth_remote(ardot)
    assert is_mcp_oauth_remote(dida)
    assert mcp_oauth_remote_kinds() >= {"notion", "tencent-ardot", "dida365"}
    assert get_mcp_oauth_remote("notion") is notion
    assert get_mcp_oauth_remote("tencent-docs") is None
    assert resource_for_kind("tencent-ardot") == "https://ardot.tencent.com/mcp"
    assert resource_for_kind("dida365") == "https://mcp.dida365.com/"
    assert resource_for_kind("notion") is None
    assert dida.mcp_url == "https://mcp.dida365.com"
    assert dida.oauth_scopes == "tasks:read tasks:write"


def test_mcp_oauth_scopes_prefer_metadata_then_catalog():
    from octop.infra.connectors.oauth.registry import _scopes_for_kind

    assert _scopes_for_kind("dida365", {"scopes_supported": ["a", "b"]}) == "a b"
    assert _scopes_for_kind("dida365", {}) == "tasks:read tasks:write"
    assert _scopes_for_kind("notion", {}) is None


def test_oauth2_accepts_token_alias_for_access_token():
    payload = validate_create_credentials("dida365", {"token": "paste-tok"})
    assert payload == {"access_token": "paste-tok"}


def test_build_dida365_remote_spec():
    entry = get_catalog_entry("dida365")
    assert entry is not None
    assert entry.name == "滴答清单"
    assert entry.auth_kind == "oauth2"
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"access_token": "dida-tok"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "http"
    assert spec["url"] == "https://mcp.dida365.com"
    assert spec["headers"]["Authorization"] == "Bearer dida-tok"
    assert spec["headers"]["Accept"] == "application/json, text/event-stream"


def test_weknora_catalog_and_credentials():
    from octop.infra.connectors.catalog import catalog_entry_to_dict

    entry = get_catalog_entry("weknora")
    assert entry is not None
    assert entry.mcp_mode == "gateway"
    data = catalog_entry_to_dict(entry)
    fields = {item["key"]: item for item in data["credential_fields"]}
    assert fields["base_url"]["field_type"] == "url"
    assert fields["api_key"]["secret"] is True

    payload = validate_create_credentials(
        "weknora",
        {
            "base_url": "http://127.0.0.1:8080/",
            "api_key": "sk-secret",
            "tenant_id": "tenant-1",
            "knowledge_base_ids": "kb-1, kb-2, kb-1",
        },
    )
    assert payload["base_url"] == "http://127.0.0.1:8080/api/v1"
    assert payload["api_key"] == "sk-secret"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["knowledge_base_ids"] == ["kb-1", "kb-2"]
    assert payload["internal_token"]


def test_weknora_rejects_non_https_remote_url():
    with pytest.raises(ValueError, match="non-local url must use https"):
        validate_create_credentials(
            "weknora",
            {"base_url": "http://weknora.example.com", "api_key": "sk-secret"},
        )
    with pytest.raises(ValueError, match="query string or fragment"):
        validate_create_credentials(
            "weknora",
            {"base_url": "https://weknora.example.com?token=secret"},
        )


def test_dify_builds_streamable_http_spec():
    entry = get_catalog_entry("dify")
    assert entry is not None
    assert entry.remote_transport == "streamable_http"
    creds = validate_create_credentials(
        "dify",
        {"mcp_url": "https://dify.example.com/mcp/server/server-code/mcp"},
    )
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds=creds,
        config=OctopConfig(),
    )
    assert spec == {
        "transport": "http",
        "url": "https://dify.example.com/mcp/server/server-code/mcp",
        "headers": {"Accept": "application/json, text/event-stream"},
    }


def test_dify_rejects_non_server_url():
    with pytest.raises(ValueError, match="Dify MCP Server URL"):
        validate_create_credentials("dify", {"mcp_url": "https://dify.example.com/v1/chat"})


def test_dify_server_code_is_redacted_from_logs():
    from octop.infra.connectors.builder import _redact_mcp_configs_for_log

    redacted = _redact_mcp_configs_for_log(
        {
            "dify__x": {
                "transport": "http",
                "url": "https://dify.example.com/mcp/server/secret-code/mcp",
            }
        }
    )
    assert redacted["dify__x"]["url"] == "https://dify.example.com/mcp/server/***/mcp"


def test_custom_field_preview_redacts_secrets():
    from octop.api.routers.connectors import _credentials_preview

    weknora = _credentials_preview(
        "weknora",
        {
            "base_url": "https://weknora.example.com/api/v1",
            "api_key": "sk-secret",
            "tenant_id": "tenant-1",
            "knowledge_base_ids": ["kb-1"],
        },
    )
    assert weknora == {
        "base_url": "https://weknora.example.com/api/v1",
        "api_key_configured": True,
        "tenant_id": "tenant-1",
        "knowledge_base_ids": ["kb-1"],
    }
    dify = _credentials_preview(
        "dify",
        {"mcp_url": "https://dify.example.com/mcp/server/secret-code/mcp"},
    )
    assert dify == {"mcp_url_configured": True}


def test_gateway_weknora_tools_and_search(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.gateway.adapters import weknora

    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def _fake_request(
        _creds: dict[str, object],
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        calls.append((method, path, body))
        if path == "/knowledge-bases":
            return {"success": True, "data": [{"id": "kb-1", "name": "Docs"}]}
        assert params == {"resource_urls": "handle"}
        return {
            "success": True,
            "data": [
                {
                    "knowledge_id": "doc-1",
                    "knowledge_title": "Guide",
                    "chunk_index": 2,
                    "score": 0.9,
                    "content": "x" * 1300,
                }
            ],
        }

    monkeypatch.setattr(weknora, "_request", _fake_request)
    listed = handle_mcp_request(
        kind="weknora",
        creds={"base_url": "http://127.0.0.1:8080/api/v1"},
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert [tool["name"] for tool in listed["result"]["tools"]] == [
        "list_knowledge_bases",
        "search",
        "read_document",
    ]
    result = json.loads(
        weknora.call_tool(
            {"base_url": "http://127.0.0.1:8080/api/v1"},
            "search",
            {"query": "install"},
        )
    )
    assert result["knowledge_base_ids"] == ["kb-1"]
    assert len(result["passages"][0]["content"]) == 1200
    assert result["passages"][0]["truncated"] is True
    assert calls[-1][2] == {"query": "install", "knowledge_base_ids": ["kb-1"]}


@pytest.mark.asyncio
async def test_dify_probe_uses_streamable_http(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    seen: dict[str, object] = {}

    async def _probe(url: str, headers: dict[str, str], *, kind: str) -> dict[str, object]:
        seen.update(url=url, headers=headers, kind=kind)
        return {"ok": True, "tool_count": 1, "tools": [{"name": "run", "description": ""}]}

    monkeypatch.setattr("octop.infra.connectors.probe.probe_streamable_http_mcp", _probe)
    entry = get_catalog_entry("dify")
    assert entry is not None
    result = await probe_connector(
        entry,
        {"mcp_url": "https://dify.example.com/mcp/server/code/mcp"},
        instance_id="probe",
        config=OctopConfig(),
    )
    assert result["ok"] is True
    assert seen == {
        "url": "https://dify.example.com/mcp/server/code/mcp",
        "headers": {"Accept": "application/json, text/event-stream"},
        "kind": "dify",
    }


@pytest.mark.asyncio
async def test_detect_local_weknora_uses_fixed_loopback(monkeypatch: pytest.MonkeyPatch):
    import httpx

    from octop.infra.connectors import probe

    seen: list[str] = []
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("trust_env", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(probe.httpx, "AsyncClient", client_factory)
    result = await probe.detect_local_weknora()

    assert result == {
        "found": True,
        "base_url": "http://127.0.0.1:8080/api/v1",
        "console_url": "http://127.0.0.1",
    }
    assert seen == ["http://127.0.0.1:8080/health"]


@pytest.mark.asyncio
async def test_detect_local_weknora_returns_not_found_on_unhealthy_host(
    monkeypatch: pytest.MonkeyPatch,
):
    import httpx

    from octop.infra.connectors import probe

    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("trust_env", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(probe.httpx, "AsyncClient", client_factory)
    assert await probe.detect_local_weknora() == {"found": False}


def test_gateway_tools_list():
    resp = handle_mcp_request(
        kind="qq-mail",
        creds={"email": "a@qq.com", "password": "p"},
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert len(resp["result"]["tools"]) == 3


def test_gateway_ima_tools():
    tools = handle_mcp_request(
        kind="tencent-ima",
        creds={"api_key": "k", "client_id": "c"},
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert len(tools["result"]["tools"]) == 14


def test_gateway_ima_tool_call_dispatch():
    resp = handle_mcp_request(
        kind="tencent-ima",
        creds={"api_key": "k", "client_id": "c"},
        body={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {"start": 0, "end": 5}},
        },
    )
    assert "error" not in resp
    assert resp["result"]["isError"] is True
    assert "arguments" not in str(resp["result"]["content"][0]["text"])


def test_gateway_probe_rejects_bad_ima_credentials(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    def _boom(_creds: dict[str, object]) -> None:
        raise ValueError("skill auth failed")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.tencent_ima.probe_credentials",
        _boom,
    )
    entry = get_catalog_entry("tencent-ima")
    assert entry is not None
    out = asyncio.run(
        probe_connector(
            entry,
            {"api_key": "bad", "client_id": "bad"},
            instance_id="probe",
            config=OctopConfig(),
        )
    )
    assert out["ok"] is False
    assert "auth" in out["error"].lower() or "skill" in out["error"].lower()


def test_gateway_probe_accepts_valid_ima_credentials(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.tencent_ima.probe_credentials",
        lambda _creds: None,
    )
    entry = get_catalog_entry("tencent-ima")
    assert entry is not None
    out = asyncio.run(
        probe_connector(
            entry,
            {"api_key": "k", "client_id": "c"},
            instance_id="probe",
            config=OctopConfig(),
        )
    )
    assert out["ok"] is True
    assert out["tool_count"] == 14


def test_gateway_wechat_reading_tools():
    tools = handle_mcp_request(
        kind="wechat-reading",
        creds={"api_key": "x=1"},
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert len(tools["result"]["tools"]) == 2


def test_ima_api_key_credentials():
    payload = validate_create_credentials(
        "tencent-ima",
        {"api_key": "ima_key", "client_id": "ima_client"},
    )
    assert payload["api_key"] == "ima_key"
    assert payload["client_id"] == "ima_client"
    assert "internal_token" in payload


def test_ima_list_notes_uses_list_note_api(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"note_book_list": [], "is_end": True}

    class _Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _Resp:
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.tencent_ima.httpx.Client",
        _Client,
    )
    from octop.infra.connectors.gateway.adapters.tencent_ima import (
        call_tool as _ima_call_tool,
    )

    out = _ima_call_tool(
        {"api_key": "wrk-x", "client_id": "cid"},
        "list_notes",
        {"limit": 8},
    )
    assert '"note_book_list"' in out
    assert captured["url"] == "https://ima.qq.com/openapi/note/v1/list_note"
    assert captured["json"] == {"cursor": "", "limit": 8}


def test_ima_requires_client_id():
    with pytest.raises(ValueError, match="client_id"):
        validate_create_credentials("tencent-ima", {"api_key": "k"})


def test_api_key_weread():
    payload = validate_create_credentials("wechat-reading", {"api_key": "wrk-testkey"})
    assert payload["api_key"] == "wrk-testkey"
    assert "internal_token" in payload


def test_api_key_weread_rejects_cookie():
    with pytest.raises(ValueError, match="wrk-"):
        validate_create_credentials("wechat-reading", {"api_key": "wr_skey=abc; wr_vid=1"})


def test_weread_shelf_uses_agent_gateway(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"books": [], "albums": []}

    class _Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _Resp:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wechat_reading.httpx.Client",
        _Client,
    )
    from octop.infra.connectors.gateway.adapters.wechat_reading import shelf as _weread_shelf

    out = _weread_shelf({"api_key": "wrk-abc"})
    assert '"books"' in out
    assert captured["url"] == "https://i.weread.qq.com/api/agent/gateway"
    assert captured["headers"]["Authorization"] == "Bearer wrk-abc"
    assert captured["json"] == {
        "api_name": "/shelf/sync",
        "skill_version": "1.0.3",
    }


def test_youdao_personal_token_credentials():
    payload = validate_create_credentials(
        "youdao-note",
        {"token": "ynote-api-key"},
    )
    assert payload["token"] == "ynote-api-key"
    assert "internal_token" not in payload


def test_tencent_news_api_key_credentials():
    payload = validate_create_credentials("tencent-news", {"api_key": "news-key-1"})
    assert payload["api_key"] == "news-key-1"
    assert "internal_token" in payload


def test_tencent_news_rejects_empty_api_key():
    with pytest.raises(ValueError, match="api_key"):
        validate_create_credentials("tencent-news", {})


def test_http_error_message_baidu_auth_fail():
    import httpx

    from octop.infra.connectors.probe import http_error_message

    r = httpx.Response(400, json={"errno": 2003, "show_msg": "auth fail:token fail"})
    assert http_error_message(r) == "auth fail:token fail"


def test_static_probe_tools_weiyun():
    from octop.infra.connectors.probe import static_probe_tools

    tools = static_probe_tools("tencent-weiyun")
    assert len(tools) >= 1
    assert static_probe_tools("notion") == []


def test_build_gateway_mcp_spec():
    entry = get_catalog_entry("tencent-ima")
    assert entry is not None
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="inst1",
        creds={"api_key": "k", "client_id": "c", "internal_token": "tok"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "http"
    assert "/api/internal/mcp/tencent-ima/inst1" in spec["url"]
    assert "token=" in spec["url"]


def test_build_gateway_langchain_tools():
    from octop.infra.connectors.gateway.langchain import build_gateway_langchain_tools

    entry = get_catalog_entry("tencent-ima")
    assert entry is not None
    tools = build_gateway_langchain_tools(
        entry=entry,
        instance_id="inst1",
        mcp_server_name="tencent-ima__inst1",
        creds={"api_key": "k", "client_id": "c"},
    )
    names = {t.name for t in tools}
    assert "tencent-ima__inst1_list_notes" in names


def test_gateway_search_news_passes_query(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.gateway.langchain import build_gateway_langchain_tools

    captured: dict[str, object] = {}

    def _fake_news(_creds: dict[str, object], args: dict[str, object]) -> str:
        captured.update(args)
        return "[]"

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.tencent_news.search_news",
        _fake_news,
    )
    entry = get_catalog_entry("tencent-news")
    assert entry is not None
    tools = build_gateway_langchain_tools(
        entry=entry,
        instance_id="inst1",
        mcp_server_name="tencent-news__inst1",
        creds={"api_key": "x"},
    )
    search = next(t for t in tools if t.name.endswith("search_news"))
    assert "query" in search.args_schema.model_json_schema()["properties"]
    search.invoke({"query": "热点", "max_results": 5})
    assert captured["query"] == "热点"
    assert captured["max_results"] == 5


def test_tencent_news_search_body_matches_official_cli(monkeypatch: pytest.MonkeyPatch):
    import uuid

    import httpx

    from octop.infra.connectors.gateway.adapters import tencent_news

    captured: dict[str, object] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"base_rsp": {"code": 0, "msg": "success"}, "news_list": []}

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> _Resp:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    tencent_news.search_news({"api_key": "news-key"}, {"query": "热点", "limit": 3})
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["page"] == 1
    assert body["page_size"] == 3
    assert body["is_show_content"] == 0
    assert body["article_types"] == [0]
    assert isinstance(body["query"], dict)
    assert body["query"]["search"] == "热点"
    assert uuid.UUID(str(body["query"]["query_id"]))
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer news-key"
    assert headers["Caller-Skill"] == tencent_news._CALLER_SKILL
    assert uuid.UUID(str(headers["Skill-Request-Id"]))
    assert headers["Skill-Request-Id"] == body["query"]["query_id"]


def test_tencent_news_probe_rejects_bad_api_key(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    def _boom(_creds: dict[str, object]) -> None:
        raise ValueError("腾讯新闻 API Key 无效: verifyAPIKey failed")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.tencent_news.probe_credentials",
        _boom,
    )
    entry = get_catalog_entry("tencent-news")
    assert entry is not None
    out = asyncio.run(
        probe_connector(
            entry,
            {"api_key": "bad"},
            instance_id="probe",
            config=OctopConfig(),
        )
    )
    assert out["ok"] is False
    assert "api key" in out["error"].lower()


def test_mail_provider_netease():
    payload = validate_create_credentials(
        "qq-mail",
        {
            "email": "a@163.com",
            "password": "code",
            "mail_provider": "netease",
        },
    )
    assert payload["imap_host"] == "imap.163.com"
    assert payload["smtp_host"] == "smtp.163.com"


def test_mail_provider_netease_126_uses_126_hosts():
    payload = validate_create_credentials(
        "qq-mail",
        {
            "email": "a@126.com",
            "password": "code",
            "mail_provider": "netease",
        },
    )
    assert payload["imap_host"] == "imap.126.com"
    assert payload["smtp_host"] == "smtp.126.com"


def test_mail_provider_netease_yeah_uses_yeah_hosts():
    payload = validate_create_credentials(
        "qq-mail",
        {
            "email": "a@yeah.net",
            "password": "code",
            "mail_provider": "netease",
        },
    )
    assert payload["imap_host"] == "imap.yeah.net"
    assert payload["smtp_host"] == "smtp.yeah.net"


def test_catalog_entry_dict_has_no_tools():
    from octop.infra.connectors.catalog import catalog_entry_to_dict, get_catalog_entry

    entry = get_catalog_entry("tencent-ima")
    assert entry is not None
    data = catalog_entry_to_dict(entry)
    assert "tools" not in data


def test_oauth_ready_notion():
    from octop.infra.connectors.oauth import oauth_ready_for_kind

    class _Settings:
        def get(self, _key: str) -> str:
            return ""

    assert oauth_ready_for_kind("notion", _Settings()) is True
    assert oauth_ready_for_kind("youdao-note", _Settings()) is False


def test_new_gateway_connectors_in_catalog():
    for kind in (
        "qq-music",
        "fliggy",
        "baidu-map",
        "ctrip-wendao",
        "meituan-travel",
        "yuandian",
    ):
        entry = get_catalog_entry(kind)
        assert entry is not None
        assert entry.mcp_mode == "gateway"
        assert entry.auth_kind == "api_key"
        assert entry.phase == "available"


def test_yuandian_api_key_prefix():
    with pytest.raises(ValueError, match="sk_"):
        validate_create_credentials("yuandian", {"api_key": "bad-key"})
    payload = validate_create_credentials("yuandian", {"api_key": "sk_test"})
    assert payload["api_key"] == "sk_test"
    assert "internal_token" in payload


def test_meituan_travel_requires_query():
    from octop.infra.connectors.gateway.adapters import meituan_travel

    with pytest.raises(ValueError, match="query"):
        meituan_travel.call_tool({"api_key": "a" * 32}, "travel_query", {"city": "北京"})


def test_meituan_travel_probe_is_format_only():
    from octop.infra.connectors.gateway.adapters import meituan_travel

    with pytest.raises(ValueError, match="格式"):
        meituan_travel.probe_credentials({"api_key": "short"})
    with pytest.raises(ValueError, match="格式"):
        meituan_travel.probe_credentials({"api_key": "not-hex!!!!!!!!!!!"})
    meituan_travel.probe_credentials({"api_key": "a" * 32})


def test_yuandian_tools_and_required_args():
    from octop.infra.connectors.gateway.adapters import yuandian

    names = {t["name"] for t in yuandian.list_tools()}
    assert names == {
        "search_laws",
        "search_cases",
        "search_enterprises",
        "get_enterprise",
        "detect_hallucination",
    }
    with pytest.raises(ValueError, match="sk_"):
        yuandian.probe_credentials({"api_key": "bad"})
    with pytest.raises(ValueError, match="name"):
        yuandian.call_tool({"api_key": "sk_x"}, "search_enterprises", {})


def test_qq_music_api_key_prefix():
    with pytest.raises(ValueError, match="qmk-"):
        validate_create_credentials("qq-music", {"api_key": "bad-key"})
    payload = validate_create_credentials(
        "qq-music", {"api_key": "qmk-00000000-0000-0000-0000-000000000000"}
    )
    assert payload["api_key"].startswith("qmk-")
    assert "internal_token" in payload


def test_ctrip_wendao_token_format():
    from octop.infra.connectors.gateway.adapters import ctrip_wendao

    with pytest.raises(ValueError, match="Token"):
        ctrip_wendao.probe_credentials({"api_key": "short"})
    ctrip_wendao.probe_credentials({"api_key": "0123456789abcdef0123456789abcdef"})


def test_baidu_map_search_place_requires_region():
    from octop.infra.connectors.gateway.adapters import baidu_map

    tools = {t["name"]: t for t in baidu_map.list_tools()}
    assert "region" in tools["search_place"]["inputSchema"]["required"]
    with pytest.raises(ValueError, match="region"):
        baidu_map.call_tool(
            {"api_key": "sk-ap-x"},
            "search_place",
            {"query": "天安门附近停车场"},
        )


def test_fliggy_exposes_only_nl_search_tools():
    from octop.infra.connectors.gateway.adapters import fliggy

    names = {t["name"] for t in fliggy.list_tools()}
    assert names == {"fliggy_ai_search", "fliggy_fast_search"}
    with pytest.raises(ValueError, match="query"):
        fliggy.call_tool({"api_key": "sk-x"}, "fliggy_fast_search", {"query": None})
    with pytest.raises(ValueError, match="unknown tool"):
        fliggy.call_tool({"api_key": "sk-x"}, "search_flight", {"origin": "北京"})


def test_mcp_args_model_drops_nulls_before_validation():
    from harness_agent.mcp import mcp_args_model

    model = mcp_args_model(
        "search_place",
        {
            "type": "object",
            "required": ["query", "region"],
            "properties": {
                "query": {"type": "string"},
                "region": {"type": "string"},
            },
        },
    )
    # Null region is omitted, then required validation fires clearly.
    with pytest.raises(Exception, match="region"):
        model.model_validate({"query": "天安门附近停车场", "region": None})
    ok = model.model_validate({"query": "天安门附近停车场", "region": "北京"})
    assert ok.model_dump() == {"query": "天安门附近停车场", "region": "北京"}


def test_new_gateway_probe_rejects_bad_credentials(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    cases = (
        ("qq-music", "QQ 音乐 API Key 无效"),
        ("fliggy", "飞猪 API Key 无效"),
        ("baidu-map", "百度地图 Token 无效"),
    )
    for kind, err in cases:

        def _boom(_creds: dict[str, object], message: str = err) -> None:
            raise ValueError(message)

        monkeypatch.setattr(
            f"octop.infra.connectors.gateway.adapters.{kind.replace('-', '_')}.probe_credentials",
            _boom,
        )
        entry = get_catalog_entry(kind)
        assert entry is not None
        out = asyncio.run(
            probe_connector(
                entry,
                {"api_key": "bad"},
                instance_id="probe",
                config=OctopConfig(),
            )
        )
        assert out["ok"] is False, kind
        assert "无效" in out["error"]


def test_probe_notion_routes_to_streamable(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    captured: dict[str, object] = {}

    async def _fake(url: str, headers: dict[str, str], *, kind: str) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        captured["kind"] = kind
        return {
            "ok": True,
            "tool_count": 1,
            "tools": [{"name": "notion-search", "description": "Search"}],
        }

    monkeypatch.setattr("octop.infra.connectors.probe.probe_streamable_http_mcp", _fake)
    entry = get_catalog_entry("notion")
    assert entry is not None

    out = asyncio.run(
        probe_connector(
            entry,
            {"access_token": "ntn_tok"},
            instance_id="probe",
            config=OctopConfig(),
        )
    )
    assert captured["kind"] == "notion"
    assert captured["url"] == "https://mcp.notion.com/mcp"
    assert out["ok"] is True
    assert out["tools"][0]["name"] == "notion-search"


def test_personal_token_meeting():
    payload = validate_create_credentials(
        "tencent-meeting",
        {"token": "meeting-token"},
    )
    assert payload["token"] == "meeting-token"


def test_build_tencent_meeting_remote_spec():
    entry = get_catalog_entry("tencent-meeting")
    assert entry is not None
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"token": "tok"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "http"
    assert spec["url"] == "https://mcp.meeting.tencent.com/mcp/wemeet-open/v1"
    assert spec["headers"]["X-Tencent-Meeting-Token"] == "tok"
    assert spec["headers"]["X-Skill-Version"] == "v1.0.1"


def test_build_tencent_ardot_remote_spec():
    entry = get_catalog_entry("tencent-ardot")
    assert entry is not None
    assert entry.name == "腾讯设计 Ardot"
    assert entry.auth_kind == "oauth2"
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"access_token": "ardot-tok"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "http"
    assert spec["url"] == "https://ardot.tencent.com/mcp"
    assert spec["headers"]["Authorization"] == "Bearer ardot-tok"
    assert spec["headers"]["Accept"] == "application/json, text/event-stream"


def test_tencent_ardot_oauth_credentials():
    payload = validate_create_credentials(
        "tencent-ardot",
        {"access_token": "ardot-tok"},
    )
    assert payload["access_token"] == "ardot-tok"


def test_probe_tencent_ardot_routes_to_streamable(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    captured: dict[str, object] = {}

    async def _fake(url: str, headers: dict[str, str], *, kind: str) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        captured["kind"] = kind
        return {
            "ok": True,
            "tool_count": 1,
            "tools": [{"name": "fetch_editor_state", "description": "Editor state"}],
        }

    monkeypatch.setattr("octop.infra.connectors.probe.probe_streamable_http_mcp", _fake)
    entry = get_catalog_entry("tencent-ardot")
    assert entry is not None

    out = asyncio.run(
        probe_connector(
            entry,
            {"access_token": "ardot-tok"},
            instance_id="probe",
            config=OctopConfig(),
        )
    )
    assert captured["kind"] == "tencent-ardot"
    assert captured["url"] == "https://ardot.tencent.com/mcp"
    assert captured["headers"]["Authorization"] == "Bearer ardot-tok"
    assert out["ok"] is True
    assert out["tools"][0]["name"] == "fetch_editor_state"


def test_oauth_ready_tencent_ardot():
    from octop.infra.connectors.oauth import oauth_ready_for_kind

    class _Settings:
        def get(self, _key: str) -> str:
            return ""

    assert oauth_ready_for_kind("tencent-ardot", _Settings()) is True


def test_ardot_token_exchange_includes_resource(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.oauth import mcp as oauth_mcp

    captured: dict[str, object] = {}

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "access_token": "tok",
                "refresh_token": "ref",
                "expires_in": 3600,
            }

    async def _fake_request(
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        **_kwargs: object,
    ) -> _Resp:
        del method, url
        captured["data"] = dict(data or {})
        return _Resp()

    async def _fake_ensure(url: str, **_kwargs: object) -> str:
        return url

    monkeypatch.setattr(oauth_mcp, "safe_request", _fake_request)
    monkeypatch.setattr(oauth_mcp, "_ensure_mcp_oauth_url", _fake_ensure)

    out = asyncio.run(
        oauth_mcp.exchange_authorization_code(
            {
                "token_endpoint": "https://ardot.tencent.com/oauth/token",
            },
            issuer="https://ardot.tencent.com",
            client_id="cid",
            client_secret=None,
            code="code",
            redirect_uri="http://127.0.0.1:9000/api/connectors/oauth/callback",
            code_verifier="verifier",
            resource="https://ardot.tencent.com/mcp",
        )
    )
    assert out["access_token"] == "tok"
    assert captured["data"]["resource"] == "https://ardot.tencent.com/mcp"
    assert captured["data"]["code_verifier"] == "verifier"


def test_build_youdao_remote_spec():
    entry = get_catalog_entry("youdao-note")
    assert entry is not None
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"token": "api-key"},
        config=OctopConfig(),
    )
    assert spec["transport"] == "sse"
    assert spec["url"] == "https://open.mail.163.com/api/ynote/mcp/sse"
    assert spec["headers"]["x-api-key"] == "api-key"


def test_youdao_probe_invalid_api_key(monkeypatch: pytest.MonkeyPatch):
    from contextlib import asynccontextmanager

    import httpx

    from octop.infra.connectors.probe import probe_youdao_note

    class _FakeResponse(httpx.Response):
        def __init__(self) -> None:
            super().__init__(
                401,
                json={"error": 10002, "desc": "get api key info error"},
                request=httpx.Request("GET", "https://open.mail.163.com/api/ynote/mcp/sse"),
            )

    @asynccontextmanager
    async def _failing_sse_client(*_args: object, **_kwargs: object):
        req = httpx.Request("GET", "https://open.mail.163.com/api/ynote/mcp/sse")
        raise httpx.HTTPStatusError("401", request=req, response=_FakeResponse())
        yield  # pragma: no cover

    monkeypatch.setattr("mcp.client.sse.sse_client", _failing_sse_client)

    out = asyncio.run(probe_youdao_note("bad"))
    assert out["ok"] is False
    assert "api key" in out["error"].lower()


def test_probe_youdao_routes_to_sse_probe(monkeypatch: pytest.MonkeyPatch):
    from octop.infra.connectors.probe import probe_connector

    captured: dict[str, str] = {}

    async def _fake(api_key: str) -> dict[str, object]:
        captured["api_key"] = api_key
        return {"ok": True, "tool_count": 1, "tools": [{"name": "list", "description": ""}]}

    monkeypatch.setattr("octop.infra.connectors.probe.probe_youdao_note", _fake)
    entry = get_catalog_entry("youdao-note")
    assert entry is not None

    out = asyncio.run(
        probe_connector(
            entry,
            {"token": "yn-key"},
            instance_id="probe",
            config=OctopConfig(),
        )
    )
    assert captured["api_key"] == "yn-key"
    assert out["ok"] is True


def test_build_tencent_lexiang_remote_spec():
    entry = get_catalog_entry("tencent-lexiang")
    assert entry is not None
    spec = build_http_mcp_spec(
        entry=entry,
        instance_id="x",
        creds={"api_key": "lx-tok", "company_from": "csig"},
        config=OctopConfig(),
    )
    assert spec["url"] == "https://mcp.lexiang-app.com/mcp?company_from=csig&preset=meta"
    assert spec["headers"]["Authorization"] == "Bearer lx-tok"


def test_tencent_lexiang_credentials():
    payload = validate_create_credentials(
        "tencent-lexiang",
        {"api_key": "lx-tok", "client_id": "csig"},
    )
    assert payload == {"api_key": "lx-tok", "company_from": "csig"}


def test_connector_repo_user_kind_unique(db: SqlitePool):
    repo = ConnectorRepo(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("u", "h", "user"),
        )
        uid = conn.execute("SELECT id FROM users").fetchone()["id"]
    iid = new_ulid()
    repo.create(
        instance_id=iid,
        user_id=uid,
        kind="tencent-docs",
        display_name="doc",
        mcp_server_name=mcp_server_name("tencent-docs", iid),
    )
    repo.upsert_credentials(instance_id=iid, blob=b"enc", expires_at=None)
    mcp_name = mcp_server_name("tencent-docs", iid)
    assert repo.validate_mcp_servers_for_user(uid, [mcp_name]) == [mcp_name]
    with pytest.raises(ValueError):
        repo.validate_mcp_servers_for_user(uid, ["other"])


def test_validate_mcp_servers_for_user(db: SqlitePool):
    repo = ConnectorRepo(db)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("u2", "h", "user"),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = 'u2'").fetchone()["id"]
    iid = new_ulid()
    mcp_name = mcp_server_name("tencent-docs", iid)
    repo.create(
        instance_id=iid,
        user_id=uid,
        kind="tencent-docs",
        display_name="doc",
        mcp_server_name=mcp_name,
    )
    repo.upsert_credentials(instance_id=iid, blob=b"enc", expires_at=None)
    assert repo.validate_mcp_servers_for_user(uid, [mcp_name]) == [mcp_name]
    with pytest.raises(ValueError):
        repo.validate_mcp_servers_for_user(uid, ["other"])
