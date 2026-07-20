"""Yuandian (元典) Legal AI gateway — laws, cases, enterprises via Open API."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

import httpx

BASE_URL = "https://open.chineselaw.com/open"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_laws",
        "description": "语义检索法律法规与法条",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然语言法律问题或检索词",
                },
                "return_num": {
                    "type": "integer",
                    "description": "返回条数，默认 10",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_cases",
        "description": "语义检索裁判案例与典型案例",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然语言案情或检索词",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_enterprises",
        "description": "按企业名称检索企业候选（获取企业 ID / 统一社会信用代码）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "企业名称关键词"},
                "top_k": {
                    "type": "integer",
                    "description": "返回候选数量，默认 10，最大 50",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_enterprise",
        "description": "按企业名称查询企业详情候选列表",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "企业名称、曾用名或股票简称",
                },
                "num": {
                    "type": "integer",
                    "description": "返回数量，默认 2",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "detect_hallucination",
        "description": "校验文本中的法律引用是否准确（约 15 秒，请耐心等待）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "待校验原文（含法规/案号引用）",
                },
            },
            "required": ["text"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "search_laws":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        return_num = int(args.get("return_num") or 10)
        return_num = max(1, min(return_num, 45))
        return _request(
            creds,
            "POST",
            "law_vector_search",
            json_body={"query": query, "return_num": return_num},
        )
    if name == "search_cases":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        return _request(
            creds,
            "POST",
            "case_vector_search",
            json_body={"query": query},
        )
    if name == "search_enterprises":
        name_q = str(args.get("name") or "").strip()
        if not name_q:
            raise ValueError("name is required")
        top_k = int(args.get("top_k") or 10)
        top_k = max(1, min(top_k, 50))
        return _request(
            creds,
            "GET",
            "rh_enterpriseSearch",
            params={"name": name_q, "top_k": str(top_k)},
        )
    if name == "get_enterprise":
        name_q = str(args.get("name") or "").strip()
        if not name_q:
            raise ValueError("name is required")
        num = int(args.get("num") or 2)
        num = max(1, min(num, 50))
        return _request(
            creds,
            "GET",
            "rh_company_info",
            params={"name": name_q, "num": str(num)},
        )
    if name == "detect_hallucination":
        text = str(args.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        return _request(
            creds,
            "POST",
            "hall_detect",
            json_body={"text": text},
            timeout=60.0,
        )
    raise ValueError(f"unknown tool: {name}")


def probe_credentials(creds: dict[str, Any]) -> None:
    _request(
        creds,
        "GET",
        "rh_enterpriseSearch",
        params={"name": "腾讯", "top_k": "1"},
    )


def _api_key(creds: dict[str, Any]) -> str:
    api_key = str(creds.get("api_key") or creds.get("token") or "").strip()
    if not api_key:
        raise ValueError("请填写元典 API Key")
    if not api_key.startswith("sk_"):
        raise ValueError("元典 API Key 应以 sk_ 开头，请从开放平台复制完整 Key")
    return api_key


def _request(
    creds: dict[str, Any],
    method: str,
    route: str,
    *,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 45.0,
) -> str:
    headers = {
        "X-API-Key": _api_key(creds),
        "Accept": "application/json",
        "User-Agent": "octop-connector/0.1",
    }
    url = f"{BASE_URL}/{route}"
    if params:
        url = f"{url}?{urlencode(params)}"
    with httpx.Client(timeout=timeout) as client:
        if method == "GET":
            r = client.get(url, headers=headers)
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"
            r = client.post(url, headers=headers, json=json_body or {})
        if r.status_code in (401, 403):
            raise ValueError(f"元典 API Key 无效: HTTP {r.status_code}")
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict):
        return str(payload)
    if payload.get("success") is False:
        msg = str(payload.get("message") or payload.get("error_code") or "error")
        if "api" in msg.lower() and "key" in msg.lower():
            raise ValueError(f"元典 API Key 无效: {msg}")
        raise ValueError(f"元典接口错误: {msg}")
    code = payload.get("code")
    # OpenAPI success codes include 200 / 201; some endpoints omit code.
    if code is not None and code not in (0, 200, 201, "0", "200", "201"):
        msg = str(payload.get("message") or payload.get("msg") or code)
        low = msg.lower()
        if "api" in low and "key" in low:
            raise ValueError(f"元典 API Key 无效: {msg}")
        raise ValueError(f"元典接口错误 [{code}]: {msg}")
    return json.dumps(payload, ensure_ascii=False, indent=2)
