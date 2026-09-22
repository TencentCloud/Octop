"""Short links via is.gd."""

from __future__ import annotations

import json
from typing import Any

import httpx
from harness_agent.plugins import PluginContext


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "short_link_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


async def make_short_link(url: str) -> str:
    """Create a short URL with is.gd."""
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return _payload(
            {"error": "invalid url", "url": raw}, "请提供以 http:// 或 https:// 开头的 URL。"
        )
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(
                "https://is.gd/create.php",
                params={"format": "json", "url": raw},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        return _payload({"error": str(exc), "url": raw}, f"短链生成失败：{exc}")
    if body.get("errorcode"):
        msg = str(body.get("errormessage") or body.get("errorcode"))
        return _payload({"error": msg, "url": raw}, f"短链生成失败：{msg}")
    short = str(body.get("shorturl") or "")
    data = {"url": raw, "shorturl": short}
    return _payload(data, f"短链：{short}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "make_short_link",
        make_short_link,
        description="用 is.gd 生成短链接。参数 url 为原始长链接。",
    )
