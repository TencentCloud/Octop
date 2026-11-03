"""
data.py — 量化数据接入层
支持：A股（tushare/akshare）、美股（yfinance）、宏观指标
作者：Jarvis | 2026-03-07
"""

import pandas as pd
import os
from typing import Optional, Union

# 尝试导入依赖，失败则提供友好提示
try:
    import tushare as ts
except ImportError:
    ts = None

try:
    import akshare as ak
except ImportError:
    ak = None

try:
    import yfinance as yf
except ImportError:
    yf = None

def _ensure_symbol(symbol: str) -> str:
    """自动补全 A 股交易所后缀"""
    if symbol.endswith(('.SH', '.SZ')):
        return symbol
    if symbol.isdigit() and len(symbol) == 6:
        # 假设为 A 股
        return symbol + ('.SH' if symbol[0] in '6' else '.SZ')
    return symbol

def get_stock(symbol: str, start_date: str, end_date: str, adjust: str = 'qfq') -> pd.DataFrame:
    """
    获取股票日线数据
    :param symbol: 股票代码（支持 600519 / 600519.SH）
    :param start_date: YYYY-MM-DD
    :param end_date: YYYY-MM-DD
    :param adjust: 复权方式：'qfq'(前复权), 'hfq'(后复权), 'none'
    :return: DataFrame with columns: open, high, low, close, vol, amount
    """
    symbol = _ensure_symbol(symbol)
    
    # 优先尝试 tushare
    if ts and hasattr(ts, 'pro_api'):
        try:
            pro = ts.pro_api(os.getenv('TUSHARE_TOKEN') or '')
            df = pro.daily(
                ts_code=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adj=adjust
            )
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.rename(columns={'trade_date': 'date', 'vol': 'volume'})
            return df.set_index('date').sort_index()
        except Exception as e:
            print(f"[tushare failed] {e}")

    # fallback to akshare
    if ak:
        try:
            if symbol.endswith('.SH') or symbol.endswith('.SZ'):
                df = ak.stock_zh_a_hist(
                    symbol=symbol[:6],
                    period="daily",
                    start_date=start_date.replace('-', ''),
                    end_date=end_date.replace('-', ''),
                    adjust=adjust
                )
                df.columns = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'change', 'turnover']
                df['date'] = pd.to_datetime(df['date'])
                return df.set_index('date').sort_index()[['open', 'high', 'low', 'close', 'volume', 'amount']]
        except Exception as e:
            print(f"[akshare failed] {e}")

    raise RuntimeError("No data source available. Please install tushare or akshare.")

def get_index(index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数数据（如 000300.SH）"""
    if ak:
        try:
            df = ak.index_zh_a_hist(
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                index_code=index_code[:6]
            )
            df['date'] = pd.to_datetime(df['date'])
            return df.set_index('date').sort_index()[['open', 'high', 'low', 'close', 'volume']]
        except Exception:
            pass
    raise NotImplementedError("Index data not available")

def get_us_stock(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取美股数据"""
    if yf:
        try:
            df = yf.download(ticker, start=start_date, end=end_date)
            return df[['Open', 'High', 'Low', 'Close', 'Volume']].rename(
                columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}
            )
        except Exception:
            pass
    raise NotImplementedError("US stock data not available")