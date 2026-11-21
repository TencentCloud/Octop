"""RAGFlow REST contract, credential validation, and gateway tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from octop.config import OctopConfig
from octop.infra.connectors.builder import validate_create_credentials
from octop.infra.connectors.catalog import catalog_entry_to_dict, get_catalog_entry
from octop.infra.connectors.gateway.adapters import ragflow
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.connectors.probe import probe_connector
from octop.infra.errors import OctopError

CREDS = {"base_url": "http://127.0.0.1:9380/api/v1", "api_key": "ragflow-test-key"}


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[httpx.Request]]:
    original_client = httpx.Client

    def install(
        payload: Any = None, *, status: int = 200, text: str | None = None
    ) -> list[httpx.Request]:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if text is not None:
                return httpx.Response(status, text=text)
            return httpx.Response(status, json=payload)

        def client(**kwargs: Any) -> httpx.Client:
            assert kwargs["follow_redirects"] is False
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(ragflow.httpx, "Client", client)
        return calls

    return install


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:9380/", "http://127.0.0.1:9380/api/v1"),
        ("http://10.0.0.5:9380/api/v1/", "http://10.0.0.5:9380/api/v1"),
        ("https://ragflow.example.com/ragflow/", "https://ragflow.example.com/ragflow/api/v1"),
    ],
)
def test_credentials_normalize_url_and_dataset_ids(url: str, expected: str) -> None:
    creds = validate_create_credentials(
        "ragflow", {**CREDS, "base_url": url, "dataset_ids": " ds-1, ds-2, ds-1 "}
    )
    assert creds["base_url"] == expected
    assert creds["dataset_ids"] == ["ds-1", "ds-2"]
    assert creds["internal_token"]


@pytest.mark.parametrize("ids", [None, [], "", ["ds-1", " ds-1 "]])
def test_credentials_accept_optional_dataset_ids(ids: Any) -> None:
    creds = validate_create_credentials("ragflow", {**CREDS, "dataset_ids": ids})
    assert creds["dataset_ids"] == (["ds-1"] if ids else [])


@pytest.mark.parametrize("ids", [123, {}, [None], [1], "../secret", "a/b"])
def test_credentials_reject_invalid_dataset_ids(ids: Any) -> None:
    with pytest.raises(ValueError, match="dataset IDs"):
        validate_create_credentials("ragflow", {**CREDS, "dataset_ids": ids})


@pytest.mark.parametrize("key", ["", "  ", "secret\nheader"])
def test_credentials_require_api_key(key: str) -> None:
    with pytest.raises(ValueError, match="API Key"):
        validate_create_credentials("ragflow", {**CREDS, "api_key": key})


@pytest.mark.parametrize(
    "url",
    [
        "http://ragflow.example.com",
        "https://ragflow.example.com?key=secret",
        "http://127.0.0.1:9380/#/datasets",
        "http://user:secret@127.0.0.1:9380",
    ],
)
def test_credentials_reject_unsafe_or_non_api_urls(url: str) -> None:
    with pytest.raises((ValueError, OctopError)):
        validate_create_credentials("ragflow", {**CREDS, "base_url": url})


def test_catalog_localizes_fields_and_marks_key_secret() -> None:
    entry = get_catalog_entry("ragflow")
    assert entry is not None
    assert (entry.auth_kind, entry.category, entry.mcp_mode) == (
        "custom_fields",
        "knowledge",
        "gateway",
    )
    zh = catalog_entry_to_dict(entry, locale="zh")
    en = catalog_entry_to_dict(entry, locale="en")
    fields = {field["key"]: field for field in zh["credential_fields"]}
    assert fields["base_url"]["label"] == "服务地址"
    assert fields["api_key"]["secret"] is True
    assert fields["api_key"]["required"] is True
    assert fields["dataset_ids"]["required"] is False
    assert en["description"].startswith("Search and read")


def test_list_datasets_is_paginated_and_sends_bearer_key(mock_http: Callable[..., Any]) -> None:
    calls = mock_http({"code": 0, "data": [{"id": "ds-2", "name": "制度"}]})
    result = json.loads(ragflow.call_tool(CREDS, "list_datasets", {"page": 2, "page_size": 1}))
    assert result["datasets"][0]["name"] == "制度"
    assert result["has_more"] is True
    assert result["page"] == 2
    assert calls[0].url.path == "/api/v1/datasets"
    assert dict(calls[0].url.params) == {"page": "2", "page_size": "1"}
    assert calls[0].headers["authorization"] == "Bearer ragflow-test-key"


def test_search_uses_defaults_and_preserves_source_ids(mock_http: Callable[..., Any]) -> None:
    calls = mock_http(
        {
            "code": 0,
            "data": {
                "total": 1,
                "chunks": [
                    {
                        "id": "chunk-1",
                        "dataset_id": "ds-1",
                        "document_id": "doc-1",
                        "document_keyword": "员工手册.pdf",
                        "similarity": 0.92,
                        "content": "请假规定" * 400,
                    }
                ],
            },
        }
    )
    result = json.loads(
        ragflow.call_tool(
            {**CREDS, "dataset_ids": ["ds-1"]}, "search", {"query": "请假", "max_results": 2}
        )
    )
    assert calls[0].url.path == "/api/v1/retrieval"
    assert json.loads(calls[0].content) == {
        "question": "请假",
        "dataset_ids": ["ds-1"],
        "page": 1,
        "page_size": 2,
    }
    passage = result["passages"][0]
    assert passage["dataset_id"] == "ds-1"
    assert passage["document_id"] == "doc-1"
    assert passage["document_name"] == "员工手册.pdf"
    assert passage["score"] == 0.92
    assert passage["truncated"] is True
    assert len(passage["content"]) == 1200
    assert "ragflow-test-key" not in json.dumps(result)


def test_search_explicit_datasets_override_defaults_and_limits_results(
    mock_http: Callable[..., Any],
) -> None:
    calls = mock_http({"code": 0, "data": {"total": 20, "chunks": [{"content": "x"}] * 20}})
    result = json.loads(
        ragflow.call_tool(
            {**CREDS, "dataset_ids": ["default"]},
            "search",
            {"query": "q", "dataset_ids": ["chosen"], "max_results": 100},
        )
    )
    assert json.loads(calls[0].content)["dataset_ids"] == ["chosen"]
    assert json.loads(calls[0].content)["page_size"] == 8
    assert len(result["passages"]) == 8


@pytest.mark.parametrize("args", [{"query": ""}, {"query": "q"}])
def test_search_requires_question_and_selected_datasets(
    args: dict[str, Any], mock_http: Callable[..., Any]
) -> None:
    calls = mock_http({"code": 0, "data": []})
    with pytest.raises(ValueError):
        ragflow.call_tool(CREDS, "search", args)
    assert calls == []


def test_search_empty_matches_is_success(mock_http: Callable[..., Any]) -> None:
    mock_http({"code": 0, "data": {"total": 0, "chunks": []}})
    result = json.loads(ragflow.call_tool(CREDS, "search", {"query": "q", "dataset_ids": ["ds"]}))
    assert result["passages"] == []


def test_read_document_uses_dataset_document_ids_and_caps_chunks(
    mock_http: Callable[..., Any],
) -> None:
    calls = mock_http(
        {
            "code": 0,
            "data": {
                "doc": {"name": "制度.pdf"},
                "total": 2,
                "chunks": [{"id": "c1", "content": "x" * 5000}, {"id": "c2", "content": "other"}],
            },
        }
    )
    result = json.loads(
        ragflow.call_tool(
            CREDS,
            "read_document",
            {
                "dataset_id": "ds",
                "document_id": "doc",
                "page": 2,
                "page_size": 1,
            },
        )
    )
    assert calls[0].url.path == "/api/v1/datasets/ds/documents/doc/chunks"
    assert dict(calls[0].url.params) == {"page": "2", "page_size": "1"}
    assert result["name"] == "制度.pdf"
    assert result["total"] == 2
    assert result["chunks"][0]["dataset_id"] == "ds"
    assert len(result["chunks"]) == 1
    assert len(result["chunks"][0]["content"]) == 4000
    assert result["chunks"][0]["truncated"] is True


@pytest.mark.parametrize("value", ["", "..", "a/b", "x?token=secret"])
def test_read_document_rejects_path_injection(value: str, mock_http: Callable[..., Any]) -> None:
    calls = mock_http()
    with pytest.raises(ValueError, match="dataset_id"):
        ragflow.call_tool(CREDS, "read_document", {"dataset_id": value, "document_id": "doc"})
    assert not calls


def test_read_document_accepts_go_chunk_response(mock_http: Callable[..., Any]) -> None:
    mock_http(
        {
            "code": 0,
            "data": {
                "doc": {"name": "联调说明.txt"},
                "total": 1,
                "chunks": [
                    {
                        "chunk_id": "chunk-go-1",
                        "content_with_weight": "来自真实 RAGFlow Go 接口的文档片段",
                        "docnm_kwd": "联调说明.txt",
                    }
                ],
            },
        }
    )
    result = json.loads(
        ragflow.call_tool(
            CREDS,
            "read_document",
            {"dataset_id": "ds", "document_id": "doc"},
        )
    )
    assert result["chunks"][0]["chunk_id"] == "chunk-go-1"
    assert result["chunks"][0]["content"] == "来自真实 RAGFlow Go 接口的文档片段"
    assert result["chunks"][0]["document_name"] == "联调说明.txt"


@pytest.mark.parametrize("status", [301, 401, 403, 500])
def test_probe_fails_on_http_errors(status: int, mock_http: Callable[..., Any]) -> None:
    calls = mock_http({"code": 0, "data": []}, status=status)
    with pytest.raises(ValueError, match=f"HTTP {status}"):
        ragflow.probe_credentials(CREDS)
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [[], {}, {"code": 0}, {"code": 0, "data": {}}])
def test_probe_rejects_malformed_responses(payload: Any, mock_http: Callable[..., Any]) -> None:
    mock_http(payload)
    with pytest.raises(ValueError, match="invalid API response"):
        ragflow.probe_credentials(CREDS)


def test_probe_rejects_non_json_and_business_error_with_http_200(
    mock_http: Callable[..., Any],
) -> None:
    mock_http(text="<html>sign in</html>")
    with pytest.raises(ValueError, match="invalid API response"):
        ragflow.probe_credentials(CREDS)
    mock_http({"code": 109, "message": "invalid key: ragflow-test-key"})
    with pytest.raises(ValueError, match="invalid key") as exc:
        ragflow.probe_credentials(CREDS)
    assert "ragflow-test-key" not in str(exc.value)


async def test_gateway_probe_validates_auth_before_listing_tools(
    mock_http: Callable[..., Any],
) -> None:
    entry = get_catalog_entry("ragflow")
    assert entry is not None
    mock_http({"code": 109, "message": "invalid key"})
    failed = await probe_connector(entry, CREDS, instance_id="probe", config=OctopConfig())
    assert failed["ok"] is False
    mock_http({"code": 0, "data": []})
    success = await probe_connector(entry, CREDS, instance_id="probe", config=OctopConfig())
    assert success["ok"] is True
    assert {tool["name"] for tool in success["tools"]} == {
        "list_datasets",
        "search",
        "read_document",
    }


def test_gateway_mcp_routes_calls_and_errors(mock_http: Callable[..., Any]) -> None:
    mock_http({"code": 0, "data": []})
    result = handle_mcp_request(
        kind="ragflow",
        creds=CREDS,
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_datasets", "arguments": {}},
        },
    )
    assert result["result"]["isError"] is False
    assert json.loads(result["result"]["content"][0]["text"])["datasets"] == []
    error = handle_mcp_request(
        kind="ragflow",
        creds={**CREDS, "_locale": "zh"},
        body={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "delete_dataset", "arguments": {}},
        },
    )
    assert error["result"]["isError"] is True
    assert "未知的 RAGFlow 工具" in error["result"]["content"][0]["text"]
