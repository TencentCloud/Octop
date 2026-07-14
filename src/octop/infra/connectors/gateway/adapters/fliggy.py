"""Fliggy (飞猪) AI — signed remote MCP, natural-language search only."""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MCP_URL = "https://flyai.open.fliggy.com/mcp"
# Public signing material from @fly-ai/flyai-cli (required by Fliggy MCP).
_SIGN_SECRET = "XSbdYnucPARDc9knhD8+X6hxdD1Nh6ZGI6Hadg25kBw="
_TTID = "ai2c(sk.clawhub)"
_USER_AGENT = "octop-connector/0.1"

# Keep the agent surface tiny: free-text search avoids structured-null misuse.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "fliggy_ai_search",
        "description": "飞猪 AI 搜索：用自然语言查酒店、景点、航班、火车等",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "完整自然语言需求，如「明天北京到上海机票」",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fliggy_fast_search",
        "description": "飞猪极速关键词搜索：景点、酒店、门票、线路等",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "关键词，如「杭州西湖附近酒店」",
                },
            },
            "required": ["query"],
        },
    },
]

_TOOL_NAMES = frozenset(t["name"] for t in TOOLS)


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name not in _TOOL_NAMES:
        raise ValueError(f"unknown tool: {name}")
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    result = _mcp_call(creds, "tools/call", {"name": name, "arguments": {"query": query}})
    return _format_tool_result(result)


def probe_credentials(creds: dict[str, Any]) -> None:
    _mcp_call(
        creds,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "octop", "version": "0.1"},
        },
    )


def _api_key(creds: dict[str, Any]) -> str:
    api_key = str(creds.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("请填写飞猪 API Key")
    return api_key


def _auth_header(api_key: str) -> str:
    return api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"


def _request_digest(material: str) -> str:
    """SHA-256 hex digest for Fliggy request-signing canonicalization.

    Digests go into the HMAC-SHA256 signing string (protocol), not password
    storage or key derivation — SHA-256 here matches Fliggy's public CLI.
    """
    # codeql[py/weak-sensitive-data-hashing]
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _x_ff_ctx() -> str:
    payload = {
        "machine": {
            "platform": os.name,
            "arch": "unknown",
            "cpus": 4,
            "memoryTierGB": 8,
            "osType": os.name,
            "nodeVersion": "octop",
            "osReleaseMajor": "0",
        },
        "fingerprint": {
            "language": "zh",
            "platform": "Octop",
            "userAgent": _USER_AGENT,
            "hardwareConcurrency": 4,
            "deviceMemory": 8,
            "clientSurface": "cli",
            "timezoneOffset": 480,
            "deviceId": hashlib.sha256(f"octop-fliggy-{uuid.getnode()}".encode()).hexdigest(),
        },
    }
    raw = gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    # Derive AES key from the published Fliggy client secret (protocol material).
    # codeql[py/weak-sensitive-data-hashing]
    key = hashlib.sha256(_SIGN_SECRET.encode("utf-8")).digest()
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, raw, None)
    return base64.b64encode(bytes([1]) + iv + ct).decode("ascii")


def _sign_headers(*, body: str, authorization: str, timestamp_ms: str) -> dict[str, str]:
    nonce = secrets.token_hex(16)
    # Fliggy canonical string includes digests of body + Authorization header.
    msg = (
        f"POST\n/mcp\n{timestamp_ms}\n{nonce}\n"
        f"{_request_digest(body)}\n{_request_digest(authorization)}"
    )
    sig = (
        base64.urlsafe_b64encode(
            hmac.new(_SIGN_SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    return {
        "x-flyai-sign-ver": "7",
        "x-flyai-sign-alg": "hmac-sha256",
        "x-flyai-ts": timestamp_ms,
        "x-flyai-nonce": nonce,
        "x-flyai-sign": sig,
    }


def _mcp_call(creds: dict[str, Any], method: str, params: dict[str, Any]) -> Any:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    auth = _auth_header(_api_key(creds))
    ts = str(int(time.time() * 1000))
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": auth,
        "x-ff-ctx": _x_ff_ctx(),
        "x-ttid": _TTID,
        "User-Agent": _USER_AGENT,
        **_sign_headers(body=body, authorization=auth, timestamp_ms=ts),
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(MCP_URL, headers=headers, content=body.encode("utf-8"))
    if r.status_code == 401:
        raise ValueError("飞猪 API Key 无效或鉴权失败")
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, dict):
        raise ValueError("飞猪 MCP 返回格式错误")
    if payload.get("error"):
        err = payload["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        text = str(msg or err)
        if "authorization" in text.lower() or "api key" in text.lower():
            raise ValueError(f"飞猪 API Key 无效: {text}")
        raise ValueError(f"飞猪 MCP 错误: {text}")
    return payload.get("result")


def _format_tool_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                raw_text = first.get("text")
                if isinstance(raw_text, str):
                    text = raw_text.strip()
                    if text:
                        try:
                            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
                        except json.JSONDecodeError:
                            return text
        return json.dumps(result, ensure_ascii=False, indent=2)
    return json.dumps(result, ensure_ascii=False, indent=2)
