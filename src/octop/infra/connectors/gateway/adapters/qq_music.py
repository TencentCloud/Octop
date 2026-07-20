"""QQ Music Skills gateway — Bearer API Key (qmk-…)."""

from __future__ import annotations

import json
from typing import Any

import httpx

BASE_URL = "https://a.y.qq.com"
SKILL_VERSION = "0.0.3"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_music",
        "description": "Search QQ Music for songs, albums, playlists, singers, MVs",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword"},
                "type": {
                    "type": "string",
                    "description": "Search type, default 0 (songs)",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "list_charts",
        "description": "List QQ Music charts / toplists",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_chart_detail",
        "description": "Get songs on a chart by topId",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_id": {"type": "integer", "description": "Chart topId"},
            },
            "required": ["top_id"],
        },
    },
    {
        "name": "get_playlist_detail",
        "description": "Get playlist songs by dissId",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diss_id": {"type": "integer", "description": "Playlist dissId"},
            },
            "required": ["diss_id"],
        },
    },
    {
        "name": "listening_report",
        "description": "Get the user's QQ Music listening report (day / week / month)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Report range hint, e.g. day / week / month",
                },
            },
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "search_music":
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            raise ValueError("keyword is required")
        return _post(
            creds,
            "/discover/search",
            {"keyword": keyword, "type": str(args.get("type") or "0")},
        )
    if name == "list_charts":
        return _post(creds, "/charts", {})
    if name == "get_chart_detail":
        top_id = args.get("top_id")
        if top_id is None:
            raise ValueError("top_id is required")
        return _post(creds, "/charts/detail", {"topId": int(top_id)})
    if name == "get_playlist_detail":
        diss_id = args.get("diss_id")
        if diss_id is None:
            raise ValueError("diss_id is required")
        return _post(creds, "/playlists/detail", {"dissId": int(diss_id)})
    if name == "listening_report":
        params: dict[str, Any] = {}
        report_type = str(args.get("type") or "").strip()
        if report_type:
            params["type"] = report_type
        return _post(creds, "/me/report", params)
    raise ValueError(f"unknown tool: {name}")


def probe_credentials(creds: dict[str, Any]) -> None:
    _post(creds, "/discover/search", {"keyword": "octop", "type": "0"})


def _api_key(creds: dict[str, Any]) -> str:
    api_key = str(creds.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("请填写 QQ 音乐 API Key")
    if not api_key.startswith("qmk-"):
        raise ValueError(
            "QQ 音乐需使用 qmk- 开头的 API Key，请登录 "
            "https://y.qq.com/n/ryqq_v2/qqmusic_skills 获取"
        )
    return api_key


def _post(creds: dict[str, Any], path: str, params: dict[str, Any]) -> str:
    body = {"params": params, "comm": {"skill_version": SKILL_VERSION}}
    headers = {
        "Authorization": f"Bearer {_api_key(creds)}",
        "Content-Type": "application/json",
        "User-Agent": "octop-connector/0.1",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{BASE_URL}{path}", headers=headers, json=body)
        if r.status_code == 401:
            raise ValueError("QQ 音乐 API Key 无效或已过期")
        r.raise_for_status()
        payload = r.json()
    if isinstance(payload, dict):
        ret = payload.get("ret")
        msg = str(payload.get("msg") or "")
        if ret not in (0, None, "0") and "route not found" not in msg:
            if ret in (11534343, "11534343") or "unauthorized" in msg.lower():
                raise ValueError(f"QQ 音乐 API Key 无效: {msg or ret}")
            # Some endpoints return ret!=0 with empty msg for empty personalized data.
            if msg:
                raise ValueError(f"QQ 音乐接口错误 [{ret}]: {msg}")
    return json.dumps(payload, ensure_ascii=False, indent=2)
