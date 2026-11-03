#!/usr/bin/env python3
"""
Stock market data fetcher for Chinese A-shares.
Uses AkShare (free, no API key required) with Sina Finance as fallback.

Usage:
    python stock_data.py 600519 [--days 30]
    python stock_data.py --market-overview
    python stock_data.py --sectors [--top 5]
    python stock_data.py --valuation 600519,000001,000858
"""

import argparse
import json
import logging
import sys
import time
import concurrent.futures as _cf
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global caches
# ---------------------------------------------------------------------------
_spot_em_cache = None


def _fetch_spot_em(max_retries=3):
    """Fetch all A-share realtime data from EastMoney via AkShare (cached)."""
    global _spot_em_cache
    if _spot_em_cache is not None:
        return _spot_em_cache

    import akshare as ak

    for attempt in range(max_retries):
        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                df = ex.submit(ak.stock_zh_a_spot_em).result(timeout=30)
            if df is not None and not df.empty:
                _spot_em_cache = df
                return df
        except _cf.TimeoutError:
            logger.warning("Fetching all A-share data timed out (attempt %d)", attempt + 1)
        except Exception as e:
            logger.warning("Fetching all A-share data failed (attempt %d): %s", attempt + 1, e)
        if attempt < max_retries - 1:
            time.sleep(3 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Stock name resolution
# ---------------------------------------------------------------------------

def resolve_stock_name(code):
    """Resolve a stock code to its name."""
    code = str(code).zfill(6)
    df = _fetch_spot_em()
    if df is not None and not df.empty:
        code_col = next((c for c in df.columns if "\u4ee3\u7801" in str(c)), df.columns[0])
        name_col = next((c for c in df.columns if "\u540d\u79f0" in str(c)), df.columns[1])
        for _, row in df.iterrows():
            if str(row[code_col]).zfill(6) == code:
                return str(row[name_col])

    # Fallback: Sina Finance
    snapshot = get_realtime_snapshot([code])
    info = snapshot.get(code, {})
    return info.get("name", code)


# ---------------------------------------------------------------------------
# Historical data
# ---------------------------------------------------------------------------

def get_stock_history(symbol, days_back=30):
    """Fetch stock OHLCV history with dual-source fallback."""
    import akshare as ak

    symbol = str(symbol).zfill(6)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days_back + 15)).strftime("%Y%m%d")

    # Source 1: Sina via AkShare
    try:
        prefix = "sh" if symbol.startswith("6") else "sz"
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            df = ex.submit(
                ak.stock_zh_a_daily, symbol=f"{prefix}{symbol}", adjust="qfq"
            ).result(timeout=30)
        if df is not None and not df.empty:
            if "date" not in df.columns:
                df["date"] = df.index.astype(str)
            df["pct_change"] = df["close"].pct_change() * 100
            return df.tail(days_back)
    except Exception as e:
        logger.warning("Sina history failed for %s: %s", symbol, e)

    # Source 2: EastMoney via AkShare
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            df = ex.submit(
                ak.stock_zh_a_hist,
                symbol=symbol, period="daily",
                start_date=start_date, end_date=end_date,
                adjust="qfq",
            ).result(timeout=30)
        if df is None or df.empty:
            return None
        col_map = {
            "\u65e5\u671f": "date", "\u5f00\u76d8": "open",
            "\u6536\u76d8": "close", "\u6700\u9ad8": "high",
            "\u6700\u4f4e": "low", "\u6210\u4ea4\u91cf": "volume",
            "\u6da8\u8dcc\u5e45": "pct_change",
        }
        df = df.rename(columns=col_map)
        return df.tail(days_back)
    except Exception as e:
        logger.error("All history sources failed for %s: %s", symbol, e)
        return None


# ---------------------------------------------------------------------------
# Realtime snapshot (Sina Finance)
# ---------------------------------------------------------------------------

def get_realtime_snapshot(symbols):
    """Batch fetch realtime quotes from Sina Finance."""
    import urllib.request
    import re

    if not symbols:
        return {}
    try:
        sina_codes = []
        for s in symbols:
            s = str(s).zfill(6)
            prefix = "sh" if s.startswith("6") else "sz"
            sina_codes.append(f"{prefix}{s}")
        url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode("gbk")

        result = {}
        for line in data.strip().split("\n"):
            m = re.match(r'var hq_str_(\w{2})(\d{6})="(.*)";', line)
            if not m or not m.group(3):
                continue
            symbol = m.group(2)
            fields = m.group(3).split(",")
            if len(fields) < 32:
                continue
            prev_close = float(fields[2]) if fields[2] else 0
            price = float(fields[3]) if fields[3] else 0
            if price <= 0:
                continue
            pct = ((price / prev_close) - 1) * 100 if prev_close > 0 else 0
            result[symbol] = {
                "name": fields[0],
                "price": price,
                "prev_close": prev_close,
                "pct_change": round(pct, 2),
            }
        return result
    except Exception as e:
        logger.warning("Realtime snapshot failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

def calculate_technical_indicators(df):
    """Calculate MA, RSI-14, and volume trend from OHLCV data."""
    if df is None or df.empty or len(df) < 5:
        return {}

    try:
        closes = [float(v) for v in df["close"].tolist()
                  if v is not None and str(v) not in ("nan", "None", "")]
    except Exception:
        return {}
    if len(closes) < 5:
        return {}

    result = {}
    latest = closes[-1]

    # Moving averages
    for n, key in [(5, "ma5"), (10, "ma10"), (20, "ma20")]:
        if len(closes) >= n:
            result[key] = round(sum(closes[-n:]) / n, 2)

    # Price deviation from MA
    parts = []
    for key, label in [("ma5", "MA5"), ("ma10", "MA10"), ("ma20", "MA20")]:
        if key in result and result[key] > 0:
            pct = (latest / result[key] - 1) * 100
            sign = "+" if pct >= 0 else ""
            parts.append(f"{label}{sign}{pct:.1f}%")
    result["ma_status"] = " | ".join(parts) if parts else ""

    # RSI-14
    if len(closes) >= 15:
        changes = [closes[i] - closes[i - 1] for i in range(len(closes) - 14, len(closes))]
        gains = sum(c for c in changes if c > 0)
        losses = sum(-c for c in changes if c < 0)
        avg_gain = gains / 14
        avg_loss = losses / 14
        if avg_loss == 0:
            result["rsi14"] = 100.0
        else:
            rs = avg_gain / avg_loss
            result["rsi14"] = round(100 - 100 / (1 + rs), 1)

    # Volume trend
    if "volume" in df.columns:
        try:
            vols = [float(v) for v in df["volume"].tolist()
                    if v is not None and str(v) not in ("nan", "None") and float(v) > 0]
            if len(vols) >= 10:
                vol5 = sum(vols[-5:]) / 5
                n = min(20, len(vols))
                vol_n = sum(vols[-n:]) / n
                if vol_n > 0:
                    ratio = vol5 / vol_n
                    if ratio > 1.3:
                        result["vol_trend"] = f"increased({ratio:.2f}x)"
                    elif ratio < 0.7:
                        result["vol_trend"] = f"decreased({ratio:.2f}x)"
                    else:
                        result["vol_trend"] = f"stable({ratio:.2f}x)"
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Market overview
# ---------------------------------------------------------------------------

def get_market_overview():
    """Fetch major index performance."""
    import akshare as ak

    indices = {
        "sh000001": "\u4e0a\u8bc1\u6307\u6570",
        "sz399001": "\u6df1\u8bc1\u6210\u6307",
        "sz399006": "\u521b\u4e1a\u677f\u6307",
    }
    result = {}
    for symbol, name in indices.items():
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and not df.empty:
                recent = df.tail(5)
                closes = recent["close"].tolist()
                pct_1d = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 else 0
                pct_5d = ((closes[-1] / closes[0]) - 1) * 100 if len(closes) >= 2 else 0
                result[name] = {
                    "latest": closes[-1],
                    "pct_1d": round(pct_1d, 2),
                    "pct_5d": round(pct_5d, 2),
                }
        except Exception as e:
            logger.debug("Index fetch failed for %s: %s", name, e)
    return result


def get_northbound_flow():
    """Fetch northbound capital flow summary."""
    import akshare as ak

    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return None
        result = {}
        for _, row in df.iterrows():
            type_name = str(row.get("\u7c7b\u578b", ""))
            if any(k in type_name for k in ("\u6caa\u80a1\u901a", "\u6df1\u80a1\u901a", "\u5317\u5411")):
                result[type_name] = {"net_buy": row.get("\u6210\u4ea4\u51c0\u4e70\u989d", 0)}
        return result
    except Exception as e:
        logger.debug("Northbound flow fetch failed: %s", e)
        return None


def get_sector_movers(n=5):
    """Fetch top/bottom industry sectors by change percentage."""
    import akshare as ak

    try:
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return None
        df = df.sort_values("\u6da8\u8dcc\u5e45", ascending=False)
        top = []
        for _, row in df.head(n).iterrows():
            top.append({"name": row.get("\u677f\u5757\u540d\u79f0", ""),
                         "pct_change": float(row.get("\u6da8\u8dcc\u5e45", 0))})
        bottom = []
        for _, row in df.tail(n).iterrows():
            bottom.append({"name": row.get("\u677f\u5757\u540d\u79f0", ""),
                            "pct_change": float(row.get("\u6da8\u8dcc\u5e45", 0))})
        return {"top": top, "bottom": bottom}
    except Exception as e:
        logger.debug("Sector data fetch failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

def get_valuation_batch(codes):
    """Batch fetch PE/PB from cached EastMoney data."""
    if not codes:
        return {}
    code_set = set(str(c).zfill(6) for c in codes)
    df = _fetch_spot_em()
    if df is None or df.empty:
        return {}

    code_col = next((c for c in df.columns if "\u4ee3\u7801" in str(c)), df.columns[0])
    pe_col = next((c for c in df.columns if "\u5e02\u76c8\u7387" in str(c)), None)
    pb_col = next((c for c in df.columns if "\u5e02\u51c0\u7387" in str(c)), None)

    result = {}
    for _, row in df.iterrows():
        code = str(row[code_col]).zfill(6)
        if code not in code_set:
            continue
        item = {}
        if pe_col:
            try:
                pe = float(row[pe_col] or 0)
                if 0 < pe < 10000:
                    item["pe"] = round(pe, 1)
            except (ValueError, TypeError):
                pass
        if pb_col:
            try:
                pb = float(row[pb_col] or 0)
                if 0 < pb < 100:
                    item["pb"] = round(pb, 1)
            except (ValueError, TypeError):
                pass
        if item:
            result[code] = item
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _format_history_json(df):
    """Convert DataFrame to list of dicts for JSON output."""
    records = []
    for _, row in df.iterrows():
        rec = {}
        for col in ("date", "open", "high", "low", "close", "volume", "pct_change"):
            if col in row.index:
                val = row[col]
                if hasattr(val, "item"):
                    val = val.item()
                rec[col] = str(val) if col == "date" else val
        records.append(rec)
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Chinese A-share market data via AkShare"
    )
    parser.add_argument("code", nargs="?", help="Stock code (e.g., 600519)")
    parser.add_argument("--days", type=int, default=30, help="Days of history (default: 30)")
    parser.add_argument("--market-overview", action="store_true", help="Show major indices overview")
    parser.add_argument("--sectors", action="store_true", help="Show sector rankings")
    parser.add_argument("--top", type=int, default=5, help="Number of top/bottom sectors (default: 5)")
    parser.add_argument("--valuation", type=str, help="Comma-separated codes for PE/PB lookup")
    args = parser.parse_args()

    output = {}

    if args.market_overview:
        output["indices"] = get_market_overview()
        output["northbound_flow"] = get_northbound_flow()
        output["sectors"] = get_sector_movers()
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.sectors:
        output["sectors"] = get_sector_movers(n=args.top)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.valuation:
        codes = [c.strip() for c in args.valuation.split(",")]
        output["valuation"] = get_valuation_batch(codes)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if not args.code:
        parser.error("Stock code is required (or use --market-overview / --sectors / --valuation)")

    code = str(args.code).zfill(6)
    stock_name = resolve_stock_name(code)
    output["stock"] = {"code": code, "name": stock_name}

    # History
    df = get_stock_history(code, days_back=args.days)
    if df is not None and not df.empty:
        output["history"] = _format_history_json(df)

        # Technicals
        output["technicals"] = calculate_technical_indicators(df)

        # Price changes
        closes = [float(r["close"]) for r in output["history"] if "close" in r]
        if closes:
            latest = closes[-1]
            output["price_summary"] = {
                "latest_close": latest,
                "pct_1d": round(((latest / closes[-2]) - 1) * 100, 2) if len(closes) >= 2 else None,
                "pct_5d": round(((latest / closes[-5]) - 1) * 100, 2) if len(closes) >= 5 else None,
                "pct_20d": round(((latest / closes[-20]) - 1) * 100, 2) if len(closes) >= 20 else None,
            }
    else:
        output["history"] = []
        output["error"] = "Failed to fetch historical data"

    # Valuation
    val = get_valuation_batch([code])
    if code in val:
        output["valuation"] = val[code]

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
