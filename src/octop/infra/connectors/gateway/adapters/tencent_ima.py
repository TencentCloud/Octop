"""Tencent IMA notes and knowledge base gateway."""

from __future__ import annotations

import json
from typing import Any

import httpx

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_notebooks",
        "description": 'List IMA notebooks (folders). First page uses cursor "0".',
        "inputSchema": {
            "type": "object",
            "properties": {
                "cursor": {
                    "type": "string",
                    "description": 'Pagination cursor; use "0" for the first page',
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results per page (1-20), default 20",
                },
            },
        },
    },
    {
        "name": "list_notes",
        "description": "List recent IMA notes (no search keyword required)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "Optional notebook ID; omit to list across all notebooks",
                },
                "cursor": {
                    "type": "string",
                    "description": 'Pagination cursor; use "" for the first page',
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results per page (1-20), default 20",
                },
            },
        },
    },
    {
        "name": "get_note",
        "description": "Read IMA note content as plaintext by note_id",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Note ID"},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "search_notes",
        "description": "Search notes by title (search_type=0) or body content (search_type=1)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"},
                "search_type": {
                    "type": "integer",
                    "description": "0=title (default), 1=content",
                },
                "start": {"type": "integer", "description": "Start offset, default 0"},
                "end": {"type": "integer", "description": "End offset, default 20"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_note",
        "description": "Create a new IMA note from Markdown content",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Markdown body (required, non-empty)",
                },
                "folder_id": {
                    "type": "string",
                    "description": "Optional notebook ID",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "append_note",
        "description": (
            "Append Markdown to an existing note. Requires an explicit note_id; "
            "do not guess the target note."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Target note ID"},
                "content": {
                    "type": "string",
                    "description": "Markdown to append (required, non-empty)",
                },
            },
            "required": ["note_id", "content"],
        },
    },
    {
        "name": "list_knowledge_bases",
        "description": ("List or search IMA knowledge bases. Empty query lists all bases."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": 'Name keyword; omit or "" to list all',
                },
                "cursor": {
                    "type": "string",
                    "description": 'Pagination cursor; use "" for the first page',
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-20), default 20",
                },
            },
        },
    },
    {
        "name": "list_addable_knowledge_bases",
        "description": (
            "List knowledge bases the user can add content to (when the target KB is unspecified)"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cursor": {
                    "type": "string",
                    "description": 'Pagination cursor; use "" for the first page',
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-50), default 20",
                },
            },
        },
    },
    {
        "name": "get_knowledge_base",
        "description": "Get knowledge base details by IDs (1-20)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Knowledge base IDs",
                },
            },
            "required": ["ids"],
        },
    },
    {
        "name": "list_knowledge",
        "description": "List contents (files/folders) inside a knowledge base",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_base_id": {"type": "string"},
                "folder_id": {
                    "type": "string",
                    "description": "Optional folder ID; omit for root",
                },
                "cursor": {
                    "type": "string",
                    "description": 'Pagination cursor; use "" for the first page',
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-50), default 20",
                },
            },
            "required": ["knowledge_base_id"],
        },
    },
    {
        "name": "search_knowledge",
        "description": "Search content inside a knowledge base (requires knowledge_base_id)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "knowledge_base_id": {"type": "string"},
                "cursor": {
                    "type": "string",
                    "description": 'Pagination cursor; use "" for the first page',
                },
            },
            "required": ["query", "knowledge_base_id"],
        },
    },
    {
        "name": "import_urls",
        "description": (
            "Import web or WeChat article URLs into a knowledge base "
            "(1-10 URLs). Root folder_id defaults to knowledge_base_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_base_id": {"type": "string"},
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-10 http(s) URLs",
                },
                "folder_id": {
                    "type": "string",
                    "description": "Optional folder; omit to use knowledge_base_id (root)",
                },
            },
            "required": ["knowledge_base_id", "urls"],
        },
    },
    {
        "name": "add_note_to_knowledge",
        "description": "Attach an existing IMA note to a knowledge base (media_type=11)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_base_id": {"type": "string"},
                "note_id": {"type": "string"},
                "title": {"type": "string"},
                "folder_id": {
                    "type": "string",
                    "description": "Optional folder ID",
                },
            },
            "required": ["knowledge_base_id", "note_id", "title"],
        },
    },
    {
        "name": "get_media",
        "description": "Get knowledge-base media info (file/web links) by media_id",
        "inputSchema": {
            "type": "object",
            "properties": {
                "media_id": {"type": "string"},
            },
            "required": ["media_id"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "list_notebooks":
        cursor = str(args.get("cursor") if args.get("cursor") is not None else "0")
        limit = _clamp_int(args.get("limit"), default=20, lo=1, hi=20)
        return _openapi(
            creds,
            "openapi/note/v1/list_notebook",
            {"cursor": cursor, "limit": limit},
        )
    if name == "list_notes":
        folder_id = str(args.get("folder_id") or "").strip()
        cursor = str(args.get("cursor") if args.get("cursor") is not None else "")
        limit = _clamp_int(args.get("limit"), default=20, lo=1, hi=20)
        body: dict[str, Any] = {"cursor": cursor, "limit": limit}
        if folder_id:
            body["folder_id"] = folder_id
        return _openapi(creds, "openapi/note/v1/list_note", body)
    if name == "get_note":
        note_id = str(args.get("note_id") or "").strip()
        if not note_id:
            raise ValueError("note_id is required")
        return _openapi(
            creds,
            "openapi/note/v1/get_doc_content",
            {"note_id": note_id, "target_content_format": 0},
        )
    if name == "search_notes":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        search_type = int(args.get("search_type") or 0)
        if search_type not in (0, 1):
            raise ValueError("search_type must be 0 (title) or 1 (content)")
        start = int(args.get("start") or 0)
        end = int(args.get("end") or 20)
        query_info = {"content": query} if search_type == 1 else {"title": query}
        return _openapi(
            creds,
            "openapi/note/v1/search_note",
            {
                "search_type": search_type,
                "query_info": query_info,
                "start": start,
                "end": end,
            },
        )
    if name == "create_note":
        content = str(args.get("content") or "")
        if not content.strip():
            raise ValueError("content is required")
        body = {"content_format": 1, "content": content}
        folder_id = str(args.get("folder_id") or "").strip()
        if folder_id:
            body["folder_id"] = folder_id
        return _openapi(creds, "openapi/note/v1/import_doc", body)
    if name == "append_note":
        note_id = str(args.get("note_id") or "").strip()
        if not note_id:
            raise ValueError("note_id is required")
        content = str(args.get("content") or "")
        if not content.strip():
            raise ValueError("content is required")
        return _openapi(
            creds,
            "openapi/note/v1/append_doc",
            {
                "note_id": note_id,
                "content_format": 1,
                "content": content,
            },
        )
    if name == "list_knowledge_bases":
        query = str(args.get("query") if args.get("query") is not None else "")
        cursor = str(args.get("cursor") if args.get("cursor") is not None else "")
        limit = _clamp_int(args.get("limit"), default=20, lo=1, hi=20)
        return _openapi(
            creds,
            "openapi/wiki/v1/search_knowledge_base",
            {"query": query, "cursor": cursor, "limit": limit},
        )
    if name == "list_addable_knowledge_bases":
        cursor = str(args.get("cursor") if args.get("cursor") is not None else "")
        limit = _clamp_int(args.get("limit"), default=20, lo=1, hi=50)
        return _openapi(
            creds,
            "openapi/wiki/v1/get_addable_knowledge_base_list",
            {"cursor": cursor, "limit": limit},
        )
    if name == "get_knowledge_base":
        ids = _string_list(args.get("ids"))
        if not ids:
            raise ValueError("ids is required")
        if len(ids) > 20:
            raise ValueError("ids must contain at most 20 entries")
        return _openapi(creds, "openapi/wiki/v1/get_knowledge_base", {"ids": ids})
    if name == "list_knowledge":
        kb_id = str(args.get("knowledge_base_id") or "").strip()
        if not kb_id:
            raise ValueError("knowledge_base_id is required")
        cursor = str(args.get("cursor") if args.get("cursor") is not None else "")
        limit = _clamp_int(args.get("limit"), default=20, lo=1, hi=50)
        body = {
            "knowledge_base_id": kb_id,
            "cursor": cursor,
            "limit": limit,
        }
        folder_id = str(args.get("folder_id") or "").strip()
        if folder_id:
            body["folder_id"] = folder_id
        return _openapi(creds, "openapi/wiki/v1/get_knowledge_list", body)
    if name == "search_knowledge":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        kb_id = str(args.get("knowledge_base_id") or "").strip()
        if not kb_id:
            raise ValueError("knowledge_base_id is required")
        cursor = str(args.get("cursor") if args.get("cursor") is not None else "")
        return _openapi(
            creds,
            "openapi/wiki/v1/search_knowledge",
            {
                "query": query,
                "knowledge_base_id": kb_id,
                "cursor": cursor,
            },
        )
    if name == "import_urls":
        kb_id = str(args.get("knowledge_base_id") or "").strip()
        if not kb_id:
            raise ValueError("knowledge_base_id is required")
        urls = _string_list(args.get("urls"))
        if not urls:
            raise ValueError("urls is required (1-10 non-empty URLs)")
        if len(urls) > 10:
            raise ValueError("urls must contain at most 10 entries")
        folder_id = str(args.get("folder_id") or "").strip() or kb_id
        return _openapi(
            creds,
            "openapi/wiki/v1/import_urls",
            {
                "knowledge_base_id": kb_id,
                "folder_id": folder_id,
                "urls": urls,
            },
        )
    if name == "add_note_to_knowledge":
        kb_id = str(args.get("knowledge_base_id") or "").strip()
        note_id = str(args.get("note_id") or "").strip()
        title = str(args.get("title") or "").strip()
        if not kb_id:
            raise ValueError("knowledge_base_id is required")
        if not note_id:
            raise ValueError("note_id is required")
        if not title:
            raise ValueError("title is required")
        body = {
            "media_type": 11,
            "title": title,
            "knowledge_base_id": kb_id,
            "note_info": {"content_id": note_id},
        }
        folder_id = str(args.get("folder_id") or "").strip()
        if folder_id:
            body["folder_id"] = folder_id
        return _openapi(creds, "openapi/wiki/v1/add_knowledge", body)
    if name == "get_media":
        media_id = str(args.get("media_id") or "").strip()
        if not media_id:
            raise ValueError("media_id is required")
        return _openapi(
            creds,
            "openapi/wiki/v1/get_media_info",
            {"media_id": media_id},
        )
    raise ValueError(f"unknown IMA tool: {name}")


def _clamp_int(value: object, *, default: int, lo: int, hi: int) -> int:
    n = default if value is None or value == "" else int(str(value))
    return max(lo, min(n, hi))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if s:
            out.append(s)
    return out


def _headers(creds: dict[str, Any]) -> dict[str, str]:
    client_id = str(creds.get("client_id") or "").strip()
    api_key = str(creds.get("api_key") or "").strip()
    if not client_id or not api_key:
        raise ValueError("IMA client_id and api_key are required")
    return {
        "ima-openapi-clientid": client_id,
        "ima-openapi-apikey": api_key,
        "Content-Type": "application/json",
        "User-Agent": "octop-connector/0.1",
    }


def _openapi(creds: dict[str, Any], path: str, body: dict[str, Any]) -> str:
    url = f"https://ima.qq.com/{path.lstrip('/')}"
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=_headers(creds), json=body)
        if r.status_code >= 400:
            raise ValueError(_http_error_message(r))
        data = r.json()
    if isinstance(data, dict):
        code = data.get("code")
        if code not in (0, None, "0"):
            msg = str(data.get("msg") or data.get("message") or "IMA API error")
            raise ValueError(f"[{code}] {msg}")
        return json.dumps(data, ensure_ascii=False, indent=2)
    return str(data)


def _http_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            msg = body.get("msg") or body.get("message")
            if msg:
                return str(msg).strip()
    except Exception:
        pass
    if response.status_code == 401:
        return "IMA 认证失败，请检查 Client ID 与 API Key"
    return f"HTTP {response.status_code}"


def probe_credentials(creds: dict[str, Any]) -> None:
    """Hit IMA with a lightweight list call to validate client_id / api_key."""
    _openapi(
        creds,
        "openapi/wiki/v1/search_knowledge_base",
        {"query": "", "cursor": "", "limit": 1},
    )
