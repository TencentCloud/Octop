"""Forex, crypto, and A-share quotes from public endpoints."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_SINA_LINE = re.compile(r'hq_str_([a-z0-9]+)\s*=\s*"(.*)"', re.I)


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "market_quotes_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _client(**kwargs: Any) -> httpx.Client:
    headers = {"User-Agent": _UA, **(kwargs.pop("headers", {}) or {})}
    return httpx.Client(timeout=15.0, headers=headers, follow_redirects=True, **kwargs)


async def get_forex(base: str = "USD", quote: str = "CNY") -> str:
    """ECB rates via frankfurter.app."""
    b = (base or "USD").strip().upper() or "USD"
    q = (quote or "CNY").strip().upper() or "CNY"
    try:
        with _client() as client:
            resp = client.get(
                "https://api.frankfurter.app/latest",
                params={"from": b, "to": q},
            )
            resp.raise_for_status()
            payload = resp.json()
        rate = (payload.get("rates") or {}).get(q)
        if rate is None:
            raise RuntimeError("no rate")
        rows = [{"symbol": f"{b}/{q}", "price": rate, "change": None, "pct": None}]
        return _payload(
            {"kind": "forex", "rows": rows, "as_of": payload.get("date")},
            f"{b}/{q} = {rate}（{payload.get('date')}）",
        )
    except Exception as exc:
        return _payload({"kind": "forex", "rows": [], "error": str(exc)}, f"汇率查询失败：{exc}")


async def get_crypto(ids: str = "bitcoin,ethereum") -> str:
    """CoinGecko simple price in USD and CNY."""
    raw_ids = (ids or "bitcoin,ethereum").strip() or "bitcoin,ethereum"
    try:
        with _client() as client:
            resp = client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": raw_ids,
                    "vs_currencies": "usd,cny",
                    "include_24hr_change": "true",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        if not isinstance(payload, dict):
            raise RuntimeError("unexpected payload")
        rows: list[dict[str, Any]] = []
        lines: list[str] = []
        for cid, info in payload.items():
            if not isinstance(info, dict):
                continue
            usd = info.get("usd")
            cny = info.get("cny")
            pct = info.get("usd_24h_change")
            rows.append(
                {
                    "symbol": cid,
                    "price": usd,
                    "price_cny": cny,
                    "pct": pct,
                    "change": None,
                },
            )
            extra = f" {pct:+.2f}%" if isinstance(pct, int | float) else ""
            lines.append(f"{cid} ${usd}{extra}")
        return _payload({"kind": "crypto", "rows": rows}, "加密货币：" + "；".join(lines))
    except Exception as exc:
        return _payload(
            {"kind": "crypto", "rows": [], "error": str(exc)}, f"加密货币查询失败：{exc}"
        )


def _parse_sina(body: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in _SINA_LINE.finditer(body):
        code = match.group(1)
        parts = match.group(2).split(",")
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            prev = float(parts[2])
            last = float(parts[3])
        except ValueError:
            continue
        change = last - prev
        pct = (change / prev * 100.0) if prev else 0.0
        rows.append(
            {
                "symbol": code,
                "name": name,
                "price": last,
                "change": round(change, 3),
                "pct": round(pct, 2),
            },
        )
    return rows


async def get_cn_stock(codes: str) -> str:
    """A-share quotes from Sina (codes like sh600519,sz399001)."""
    raw = (codes or "").strip()
    if not raw:
        return _payload(
            {"kind": "cn_stock", "rows": [], "error": "codes required"},
            "请提供 codes，例如 sh000001,sz399001,sh600519。",
        )
    cleaned = ",".join(part.strip().lower() for part in raw.split(",") if part.strip())
    try:
        with _client(headers={"Referer": "https://finance.sina.com.cn"}) as client:
            resp = client.get(f"https://hq.sinajs.cn/list={cleaned}")
            resp.raise_for_status()
            body = resp.content.decode("gbk", errors="replace")
        rows = _parse_sina(body)
        if not rows:
            raise RuntimeError("empty quote")
        lines = [f"{r.get('name', r['symbol'])} {r['price']} ({r['pct']:+.2f}%)" for r in rows]
        return _payload({"kind": "cn_stock", "rows": rows}, "A股：" + "；".join(lines))
    except Exception as exc:
        return _payload({"kind": "cn_stock", "rows": [], "error": str(exc)}, f"A股查询失败：{exc}")


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "get_forex",
        get_forex,
        description="查询汇率。base/quote 为货币代码，默认 USD 兑 CNY。",
    )
    ctx.tool(
        "get_crypto",
        get_crypto,
        description="查询加密货币兑美元/人民币。ids 为 CoinGecko id，逗号分隔，默认 bitcoin,ethereum。",
    )
    ctx.tool(
        "get_cn_stock",
        get_cn_stock,
        description="查询 A 股/指数。codes 如 sh000001,sz399001,sh600519（新浪代码）。",
    )
