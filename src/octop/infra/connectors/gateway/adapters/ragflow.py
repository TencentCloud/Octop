"""Read-only RAGFlow tools using the public datasets/retrieval HTTP API."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from octop.i18n import tr
from octop.infra.connectors.builder import (
    normalize_ragflow_base_url,
    normalize_ragflow_dataset_ids,
)

_MAX_RESULTS = 8
_SEARCH_CHARS = 1200
_DOCUMENT_CHARS = 4000
_PAGE_SIZE = {"type": "integer", "minimum": 1, "maximum": 50}
_PAGING = {
    "page": {"type": "integer", "minimum": 1, "description": "Page number; default 1"},
    "page_size": {**_PAGE_SIZE, "description": "Items per page; default 20"},
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_datasets",
        "description": "List RAGFlow knowledge bases (datasets) and their IDs, with pagination.",
        "inputSchema": {"type": "object", "properties": _PAGING},
    },
    {
        "name": "search",
        "description": (
            "Search existing RAGFlow datasets for ranked source passages. "
            "Use dataset_ids from list_datasets, or omit to use the connector defaults. "
            "Use the returned dataset_id and document_id with read_document for context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "Search question"},
                "dataset_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Datasets to search; defaults to connector configuration",
                },
                "max_results": {"type": "integer", "minimum": 1, "maximum": _MAX_RESULTS},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_document",
        "description": (
            "Read a RAGFlow document's parsed text chunks and metadata, with pagination. "
            "Requires dataset_id and document_id from search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "minLength": 1},
                "document_id": {"type": "string", "minLength": 1},
                **_PAGING,
            },
            "required": ["dataset_id", "document_id"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def _text(creds: dict[str, Any], key: str, **kwargs: object) -> str:
    return tr(f"ragflow.{key}", str(creds.get("_locale") or "en"), **kwargs)


def _request(
    creds: dict[str, Any],
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    base_url = normalize_ragflow_base_url(str(creds.get("base_url") or ""))
    api_key = str(creds.get("api_key") or "").strip()
    if not api_key or any(char in api_key for char in "\r\n\x00"):
        raise ValueError(_text(creds, "api_key_required"))
    try:
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            response = client.request(
                method,
                f"{base_url}{path}",
                headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
                params=params,
                json=body,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(_text(creds, "http_error", status=exc.response.status_code)) from exc
    except httpx.HTTPError as exc:
        raise ValueError(_text(creds, "network_error")) from exc
    # Redirects must never forward the credential to another host.
    if response.is_redirect:
        raise ValueError(_text(creds, "http_error", status=response.status_code))
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(_text(creds, "invalid_response")) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("code"), int):
        raise ValueError(_text(creds, "invalid_response"))
    if payload["code"] != 0:
        reason = str(payload.get("message") or payload["code"]).replace(api_key, "***")[:500]
        raise ValueError(_text(creds, "api_error", reason=reason))
    return payload.get("data")


def _rows(creds: dict[str, Any], data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError(_text(creds, "invalid_response"))
    return data


def _object(creds: dict[str, Any], data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(_text(creds, "invalid_response"))
    return data


def _page(args: dict[str, Any]) -> tuple[int, int]:
    return max(1, int(args.get("page") or 1)), max(1, min(int(args.get("page_size") or 20), 50))


def _passage(item: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    content = str(item.get("content") or item.get("content_with_weight") or "")
    return {
        "chunk_id": item.get("id") or item.get("chunk_id"),
        "dataset_id": item.get("dataset_id"),
        "document_id": item.get("document_id"),
        "document_name": item.get("document_keyword") or item.get("docnm_kwd"),
        "score": item.get("similarity"),
        "positions": item.get("positions"),
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


def _list_datasets(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    page, page_size = _page(args)
    data = _request(creds, "GET", "/datasets", params={"page": page, "page_size": page_size})
    rows = _rows(creds, data)
    return {
        "datasets": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "description": str(item.get("description") or "")[:_SEARCH_CHARS],
                "document_count": item.get("document_count"),
                "chunk_count": item.get("chunk_count"),
            }
            for item in rows[:page_size]
        ],
        "page": page,
        "page_size": page_size,
        "has_more": len(rows) >= page_size,
    }


def _search(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError(_text(creds, "query_required"))
    ids = normalize_ragflow_dataset_ids(args.get("dataset_ids") or creds.get("dataset_ids"))
    if not ids:
        raise ValueError(_text(creds, "datasets_required"))
    limit = max(1, min(int(args.get("max_results") or _MAX_RESULTS), _MAX_RESULTS))
    data = _object(
        creds,
        _request(
            creds,
            "POST",
            "/retrieval",
            body={"question": query, "dataset_ids": ids, "page": 1, "page_size": limit},
        ),
    )
    rows = _rows(creds, data.get("chunks"))
    return {
        "query": query,
        "dataset_ids": ids,
        "total": data.get("total"),
        "passages": [_passage(item, max_chars=_SEARCH_CHARS) for item in rows[:limit]],
    }


def _read_document(creds: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    ids: dict[str, str] = {}
    for key in ("dataset_id", "document_id"):
        value = str(args.get(key) or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError(_text(creds, "invalid_id", field=key))
        ids[key] = value
    page, page_size = _page(args)
    data = _object(
        creds,
        _request(
            creds,
            "GET",
            f"/datasets/{ids['dataset_id']}/documents/{ids['document_id']}/chunks",
            params={"page": page, "page_size": page_size},
        ),
    )
    rows = _rows(creds, data.get("chunks"))
    doc = _object(creds, data.get("doc"))
    return {
        **ids,
        "name": doc.get("name"),
        "page": page,
        "page_size": page_size,
        "total": data.get("total"),
        "chunks": [
            _passage({**item, **ids}, max_chars=_DOCUMENT_CHARS) for item in rows[:page_size]
        ],
    }


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "list_datasets":
        result = _list_datasets(creds, args)
    elif name == "search":
        result = _search(creds, args)
    elif name == "read_document":
        result = _read_document(creds, args)
    else:
        raise ValueError(_text(creds, "unknown_tool", name=name))
    return json.dumps(result, ensure_ascii=False)


def probe_credentials(creds: dict[str, Any]) -> None:
    _rows(creds, _request(creds, "GET", "/datasets", params={"page": 1, "page_size": 1}))
