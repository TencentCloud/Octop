#!/usr/bin/env python3
"""
Stock news aggregator for Chinese A-shares.
Fetches news from EastMoney and Xueqiu (free, no API key required).

Usage:
    python stock_news.py 600519 贵州茅台
    python stock_news.py --market
"""

import argparse
import json
import logging
import re
import time
import concurrent.futures as _cf

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EastMoney news
# ---------------------------------------------------------------------------

def get_news_eastmoney(symbol):
    """Fetch stock news from EastMoney via AkShare."""
    import akshare as ak

    symbol = str(symbol).zfill(6)
    for attempt in range(2):
        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                df = ex.submit(ak.stock_news_em, symbol=symbol).result(timeout=15)
            if df is None or df.empty:
                return []
            results = []
            for _, row in df.head(5).iterrows():
                results.append({
                    "title": str(row.get("\u65b0\u95fb\u6807\u9898", "")),
                    "content": str(row.get("\u65b0\u95fb\u5185\u5bb9", ""))[:300],
                    "time": str(row.get("\u53d1\u5e03\u65f6\u95f4", "")),
                    "source": f"EastMoney {row.get('\u6587\u7ae0\u6765\u6e90', '')}",
                })
            return results
        except _cf.TimeoutError:
            logger.debug("EastMoney news timed out for %s (attempt %d)", symbol, attempt + 1)
        except Exception as e:
            logger.debug("EastMoney news failed for %s (attempt %d): %s", symbol, attempt + 1, e)
        if attempt < 1:
            time.sleep(2)
    return []


# ---------------------------------------------------------------------------
# Xueqiu (Snowball) news
# ---------------------------------------------------------------------------

def get_news_xueqiu(symbol):
    """Fetch stock news from Xueqiu (Snowball Finance)."""
    import urllib.request
    import http.cookiejar

    symbol = str(symbol).zfill(6)
    try:
        prefix = "SH" if symbol.startswith("6") else "SZ"
        xq_symbol = f"{prefix}{symbol}"
        url = f"https://stock.xueqiu.com/v5/stock/news.json?symbol={xq_symbol}&count=5&source=all"

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        # Get cookies first
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        cookie_req = urllib.request.Request("https://xueqiu.com/", headers={"User-Agent": ua})
        opener.open(cookie_req, timeout=10)

        req = urllib.request.Request(url, headers={"User-Agent": ua, "Referer": "https://xueqiu.com/"})
        resp = opener.open(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in (data.get("data", {}).get("items", []) or [])[:5]:
            title = item.get("title", "") or ""
            text = item.get("text", "") or ""
            text = re.sub(r"<[^>]+>", "", text)[:300]
            if title or text:
                results.append({
                    "title": title,
                    "content": text,
                    "time": "",
                    "source": "Xueqiu",
                })
        return results
    except Exception as e:
        logger.debug("Xueqiu news failed for %s: %s", symbol, e)
        return []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_news(news_list):
    """Deduplicate news by title prefix."""
    seen = set()
    result = []
    for n in news_list:
        title = n.get("title", "").strip()
        if not title:
            continue
        key = title[:20]
        if key not in seen:
            seen.add(key)
            result.append(n)
    return result


# ---------------------------------------------------------------------------
# Aggregated search
# ---------------------------------------------------------------------------

def search_stock_news(stock_code, stock_name=None):
    """Aggregate news from all free sources for a stock."""
    all_news = []

    # EastMoney
    try:
        all_news.extend(get_news_eastmoney(stock_code))
    except Exception as e:
        logger.debug("EastMoney aggregation failed: %s", e)

    # Xueqiu
    try:
        all_news.extend(get_news_xueqiu(stock_code))
    except Exception as e:
        logger.debug("Xueqiu aggregation failed: %s", e)

    return _dedup_news(all_news)


def search_market_news():
    """Search for general A-share market news using AkShare."""
    import akshare as ak

    results = []
    try:
        # Use AkShare's news interface for market-wide news
        df = ak.stock_news_em(symbol="000001")
        if df is not None and not df.empty:
            for _, row in df.head(8).iterrows():
                results.append({
                    "title": str(row.get("\u65b0\u95fb\u6807\u9898", "")),
                    "content": str(row.get("\u65b0\u95fb\u5185\u5bb9", ""))[:300],
                    "time": str(row.get("\u53d1\u5e03\u65f6\u95f4", "")),
                    "source": f"EastMoney {row.get('\u6587\u7ae0\u6765\u6e90', '')}",
                })
    except Exception as e:
        logger.debug("Market news fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch Chinese A-share stock news from free sources"
    )
    parser.add_argument("code", nargs="?", help="Stock code (e.g., 600519)")
    parser.add_argument("name", nargs="?", help="Stock name (e.g., \u8d35\u5dde\u8305\u53f0)")
    parser.add_argument("--market", action="store_true", help="Fetch market-wide news")
    args = parser.parse_args()

    if args.market:
        news = search_market_news()
        output = {"type": "market_news", "count": len(news), "news": news}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if not args.code:
        parser.error("Stock code is required (or use --market)")

    code = str(args.code).zfill(6)
    news = search_stock_news(code, args.name)
    output = {
        "type": "stock_news",
        "stock_code": code,
        "stock_name": args.name or code,
        "count": len(news),
        "news": news,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
