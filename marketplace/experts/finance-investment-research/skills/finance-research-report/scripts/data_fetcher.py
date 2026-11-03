"""
数据获取模块 - 使用 akshare 获取金融市场数据
优先使用新浪源 API（稳定可靠），东方财富 push2 系列在部分网络环境下不可用。
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


def get_week_range(date: Optional[str] = None) -> tuple[str, str]:
    """获取指定日期所在周的起止日期 (周一到周五)"""
    if date:
        dt = datetime.strptime(date, "%Y-%m-%d")
    else:
        dt = datetime.now()
    monday = dt - timedelta(days=dt.weekday())
    friday = monday + timedelta(days=4)
    return monday.strftime("%Y%m%d"), friday.strftime("%Y%m%d")


def _sina_symbol(symbol: str) -> str:
    """将纯数字代码转换为新浪格式 (sh600519 / sz000001)"""
    if symbol.startswith(("sh", "sz")):
        return symbol
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


def fetch_stock_daily(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取个股日线数据（新浪源，前复权）"""
    sina_sym = _sina_symbol(symbol)
    df = ak.stock_zh_a_daily(symbol=sina_sym, start_date=start_date, end_date=end_date, adjust="qfq")
    df = df.reset_index(drop=True) if "date" in df.columns else df.reset_index()
    # 统一列名
    col_map = {
        "date": "date", "open": "open", "close": "close", "high": "high",
        "low": "low", "volume": "volume", "outstanding_share": "outstanding_share",
        "turnover": "turnover_rate",
    }
    df = df.rename(columns={c: col_map.get(c, c) for c in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 计算换手率（如果缺失）
    if "turnover_rate" not in df.columns or df["turnover_rate"].isna().all():
        if "outstanding_share" in df.columns:
            df["turnover_rate"] = df["volume"] / df["outstanding_share"] * 100
        else:
            df["turnover_rate"] = 0.0
    else:
        df["turnover_rate"] = df["turnover_rate"] * 100  # 转为百分比

    return df


def fetch_index_daily(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数日线数据（新浪源）
    symbol: 000001(上证), 399001(深证), 000300(沪深300), 399006(创业板)
    """
    sina_sym = _sina_symbol(symbol)
    df = ak.stock_zh_index_daily(symbol=sina_sym)
    df = df.reset_index(drop=True) if "date" in df.columns else df.reset_index()
    df["date"] = pd.to_datetime(df["date"])
    mask = (df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))
    df = df.loc[mask].sort_values("date").reset_index(drop=True)
    return df


def fetch_stock_name_from_spot(symbol: str) -> str:
    """从新浪实时行情获取股票名称（轻量级，只查单只）"""
    try:
        import urllib.request
        import json
        sina_sym = _sina_symbol(symbol)
        # 使用新浪行情接口获取名称
        url = f"https://hq.sinajs.cn/list={sina_sym}"
        req = urllib.request.Request(url, headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("gbk")
        # 格式: var hq_str_sh600519="贵州茅台,..."
        parts = text.split('"')[1].split(",")
        return parts[0] if parts[0] else symbol
    except Exception:
        return symbol


def fetch_market_breadth() -> dict:
    """获取市场涨跌家数统计（新浪源）"""
    try:
        df = ak.stock_zh_a_spot()
        up = (df["涨跌幅"] > 0).sum()
        down = (df["涨跌幅"] < 0).sum()
        flat = (df["涨跌幅"] == 0).sum()
        limit_up = (df["涨跌幅"] >= 9.9).sum()
        limit_down = (df["涨跌幅"] <= -9.9).sum()
        return {
            "上涨家数": int(up),
            "下跌家数": int(down),
            "平盘家数": int(flat),
            "涨停家数": int(limit_up),
            "跌停家数": int(limit_down),
            "总家数": len(df),
        }
    except Exception:
        return {}


def fetch_north_flow(start_date: str, end_date: str) -> pd.DataFrame:
    """获取北向资金历史数据"""
    try:
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        df["日期"] = pd.to_datetime(df["日期"])
        mask = (df["日期"] >= pd.to_datetime(start_date)) & (df["日期"] <= pd.to_datetime(end_date))
        result = df.loc[mask].sort_values("日期").reset_index(drop=True)
        result = result.rename(columns={"日期": "date", "当日成交净买额": "net_flow"})
        return result
    except Exception:
        return pd.DataFrame()


def fetch_macro_news() -> list[str]:
    """获取全球财经要闻"""
    try:
        df = ak.stock_info_global_em()
        col = "content" if "content" in df.columns else df.columns[1] if len(df.columns) > 1 else df.columns[0]
        return df[col].head(10).tolist()
    except Exception:
        return []


def fetch_stock_news(symbol: str, count: int = 5) -> list[dict]:
    """获取个股相关新闻（东方财富源）
    返回: [{"title": "...", "time": "...", "source": "..."}]
    """
    try:
        df = ak.stock_news_em(symbol=symbol)
        results = []
        for _, row in df.head(count).iterrows():
            results.append({
                "title": row.get("新闻标题", ""),
                "time": str(row.get("发布时间", "")),
                "source": row.get("文章来源", ""),
            })
        return results
    except Exception:
        return []


def fetch_stock_hist_extended(symbol: str, days: int = 90) -> pd.DataFrame:
    """获取较长周期的历史数据，用于计算技术指标"""
    end = datetime.now()
    start = end - timedelta(days=days)
    return fetch_stock_daily(
        symbol,
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
    )


def fetch_index_hist_extended(symbol: str, days: int = 90) -> pd.DataFrame:
    """获取较长周期的指数历史数据"""
    end = datetime.now()
    start = end - timedelta(days=days)
    return fetch_index_daily(
        symbol,
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
    )
