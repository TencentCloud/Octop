"""WeChat Reading (WeRead) bookshelf gateway."""

from __future__ import annotations

import json
from typing import Any

import httpx

WEREAD_GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
WEREAD_SKILL_VERSION = "1.0.3"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_bookshelf",
        "description": "List books on WeRead shelf",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_book_notes",
        "description": "Get highlights/notes for a book by bookId",
        "inputSchema": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
            },
            "required": ["book_id"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "list_bookshelf":
        return shelf(creds)
    if name == "get_book_notes":
        return notes(creds, args)
    raise ValueError(f"unknown tool: {name}")


def shelf(creds: dict[str, Any]) -> str:
    return _api(creds, "/shelf/sync")


def notes(creds: dict[str, Any], args: dict[str, Any]) -> str:
    book_id = str(args.get("book_id") or "").strip()
    if not book_id:
        raise ValueError("book_id is required")
    return _api(creds, "/book/bookmarklist", bookId=book_id)


def probe_credentials(creds: dict[str, Any]) -> None:
    """Validate WeRead API key by syncing the bookshelf."""
    shelf(creds)


def _api_key(creds: dict[str, Any]) -> str:
    api_key = str(creds.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("missing wechat-reading API key")
    if not api_key.startswith("wrk-"):
        raise ValueError(
            "微信读书需使用 wrk- 开头的 API Key（非浏览器 Cookie）。"
            "请打开 https://weread.qq.com/r/weread-skills 登录后复制 API Key 并更新连接器配置"
        )
    return api_key


def _api(creds: dict[str, Any], api_name: str, **params: Any) -> str:
    body: dict[str, Any] = {"api_name": api_name, "skill_version": WEREAD_SKILL_VERSION}
    body.update({k: v for k, v in params.items() if v is not None})
    headers = {
        "Authorization": f"Bearer {_api_key(creds)}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (octop-connector/0.1)",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(WEREAD_GATEWAY_URL, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    if isinstance(data, dict):
        errcode = data.get("errcode", data.get("errCode"))
        if errcode not in (0, None):
            errmsg = str(data.get("errmsg") or data.get("errMsg") or "weread api error")
            raise ValueError(f"[{errcode}] {errmsg}")
    return json.dumps(data, ensure_ascii=False, indent=2)
