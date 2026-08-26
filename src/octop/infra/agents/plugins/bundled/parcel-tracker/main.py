"""Domestic parcel lookup via kuaidi100 public pages, with a link fallback."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
from harness_agent.plugins import PluginContext

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.kuaidi100.com/",
}


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "parcel_timeline", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _client() -> httpx.Client:
    return httpx.Client(timeout=15.0, headers=_HEADERS, follow_redirects=True)


def _detect_company(number: str) -> str:
    with _client() as client:
        resp = client.get(
            "https://www.kuaidi100.com/autonumber/autoComNum",
            params={"text": number},
        )
        resp.raise_for_status()
        payload = resp.json()
    autos = payload.get("auto") or []
    if autos and isinstance(autos[0], dict):
        return str(autos[0].get("comCode") or "").strip()
    return ""


def _query(company: str, number: str) -> list[dict[str, Any]]:
    with _client() as client:
        resp = client.get(
            "https://www.kuaidi100.com/query",
            params={"type": company, "postid": number},
        )
        resp.raise_for_status()
        payload = resp.json()
    traces: list[dict[str, Any]] = []
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        traces.append(
            {
                "time": str(row.get("time") or ""),
                "context": str(row.get("context") or ""),
                "status": str(row.get("status") or payload.get("status") or ""),
            },
        )
    return traces


async def track_parcel(number: str, company: str = "") -> str:
    """Look up a tracking number. company is a kuaidi100 comCode when known."""
    nu = (number or "").strip()
    if not nu:
        return _payload({"error": "number required"}, "请提供快递单号。")
    url = f"https://www.kuaidi100.com/chaxun?nu={quote(nu)}"
    com = (company or "").strip()
    try:
        if not com:
            com = _detect_company(nu)
        traces = _query(com, nu) if com else []
    except Exception as exc:
        data = {
            "number": nu,
            "company": com,
            "traces": [],
            "url": url,
            "error": str(exc),
        }
        return _payload(data, f"查询失败，请打开 {url} 。原因：{exc}")

    data = {"number": nu, "company": com, "traces": traces, "url": url}
    if not traces:
        data["error"] = "no traces"
        return _payload(data, f"暂无轨迹，可打开 {url} 查询。单号 {nu} 公司 {com or '未知'}。")
    latest = traces[0].get("context") or ""
    return _payload(data, f"{nu}（{com}）最新：{latest}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "track_parcel",
        track_parcel,
        description=(
            "查询国内快递。number 为单号；company 可选（快递100 comCode，如 yuantong）。"
            "查不到时返回快递100 网页链接。"
        ),
    )
