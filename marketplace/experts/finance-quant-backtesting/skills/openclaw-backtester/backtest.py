#!/usr/bin/env python3
"""
backtest.py — 策略回测引擎（修复版）
接入本地数据库 a_stock_complete.db
支持: SMA交叉、RSI、MACD、布林带等策略
"""

import argparse
import sqlite3
import pandas as pd
import numpy as np
from typing import Optional, Tuple
import os

# 本地数据库路径
DB_PATH = os.path.expanduser("~/.openclaw/workspace/trading/a_stock_complete.db")

def load_data(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """从本地数据库加载15分钟K线数据"""
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return None
    
    # 转换symbol格式
    if len(symbol) == 6 and symbol.isdigit():
        symbol = symbol + ('.SH' if symbol.startswith('6') else '.SZ')
    
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT datetime, date, open, high, low, close, volume, amount,
           ma8, ma21, ma65, ma144
    FROM stock_15m
    WHERE symbol = ? AND date >= ? AND date <= ?
    ORDER BY datetime
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=(symbol, start_date, end_date))
        conn.close()
        
        if df.empty:
            print(f"❌ 无数据: {symbol} [{start_date} ~ {end_date}]")
            return None
        
        df['datetime'] = pd.to_datetime(df['datetime'], format='mixed')
        df = df.set_index('datetime').sort_index()
        
        print(f"✅ 加载数据: {symbol} {len(df)} 条记录 [{df.index[0]} ~ {df.index[-1]}]")
        return df
        
    except Exception as e:
        print(f"❌ 数据库查询错误: {e}")
        conn.close()
        return None

def calculate_sma_crossover(df: pd.DataFrame, fast: int = 8, slow: int = 21) -> pd.DataFrame:
    """SMA交叉策略"""
    df = df.copy()
    df['sma_fast'] = df['close'].rolling(window=fast).mean()
    df['sma_slow'] = df['close'].rolling(window=slow).mean()
    df['signal'] = 0
    df.loc[df['sma_fast'] > df['sma_slow'], 'signal'] = 1  # 多头
    df.loc[df['sma_fast'] < df['sma_slow'], 'signal'] = -1  # 空头
    df['position'] = df['signal'].diff()
    return df

def calculate_rsi(df: pd.DataFrame, period: int = 14, upper: int = 70, lower: int = 30) -> pd.DataFrame:
    """RSI策略"""
    df = df.copy()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['signal'] = 0
    df.loc[df['rsi'] < lower, 'signal'] = 1  # 超卖买入
    df.loc[df['rsi'] > upper, 'signal'] = -1  # 超买卖出
    df['position'] = df['signal'].diff()
    return df

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD策略"""
    df = df.copy()
    ema_fast = df['close'].ewm(span=fast).mean()
    ema_slow = df['close'].ewm(span=slow).mean()
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=signal).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    df['signal'] = 0
    df.loc[df['macd'] > df['macd_signal'], 'signal'] = 1
    df.loc[df['macd'] < df['macd_signal'], 'signal'] = -1
    df['position'] = df['signal'].diff()
    return df

def calculate_bollinger(df: pd.DataFrame, period: int = 20, std: int = 2) -> pd.DataFrame:
    """布林带策略"""
    df = df.copy()
    df['sma'] = df['close'].rolling(window=period).mean()
    df['std'] = df['close'].rolling(window=period).std()
    df['upper'] = df['sma'] + (df['std'] * std)
    df['lower'] = df['sma'] - (df['std'] * std)
    
    df['signal'] = 0
    df.loc[df['close'] < df['lower'], 'signal'] = 1  # 触及下轨买入
    df.loc[df['close'] > df['upper'], 'signal'] = -1  # 触及上轨卖出
    df['position'] = df['signal'].diff()
    return df

def run_backtest(df: pd.DataFrame, initial_cash: float = 100000, 
                 commission: float = 0.0005, slippage: float = 0.001) -> dict:
    """执行回测"""
    
    # 找到所有交易信号
    entries = df[df['position'] == 2].copy()  # 0->1 (买入)
    exits = df[df['position'] == -2].copy()   # 1->0/-1 或 -1->0/1 (卖出)
    
    trades = []
    position = 0
    cash = initial_cash
    shares = 0
    entry_price = 0
    
    for idx, row in df.iterrows():
        price = row['close']
        
        if row['position'] in [1, 2] and position == 0:  # 买入信号 (1或2)
            position = 1
            entry_price = price * (1 + slippage)
            shares = cash / entry_price
            cash = 0
            trades.append({
                'type': 'BUY',
                'date': idx,
                'price': entry_price,
                'shares': shares,
                'value': shares * entry_price
            })
            
        elif row['position'] in [-1, -2] and position == 1:  # 卖出信号 (-1或-2)
            position = 0
            exit_price = price * (1 - slippage)
            cash = shares * exit_price * (1 - commission)
            pnl = (exit_price - entry_price) / entry_price * 100
            trades.append({
                'type': 'SELL',
                'date': idx,
                'price': exit_price,
                'shares': shares,
                'value': cash,
                'pnl_pct': pnl
            })
            shares = 0
    
    # 计算最终权益
    final_value = cash if position == 0 else shares * df['close'].iloc[-1]
    
    # 统计指标
    trades_df = pd.DataFrame(trades)
    if len(trades_df) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'sharpe': 0
        }
    
    sells = trades_df[trades_df['type'] == 'SELL']
    if len(sells) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'sharpe': 0
        }
    
    wins = len(sells[sells['pnl_pct'] > 0])
    total_sells = len(sells)
    win_rate = (wins / total_sells * 100) if total_sells > 0 else 0
    
    total_return = (final_value - initial_cash) / initial_cash * 100
    
    # 计算最大回撤
    equity_curve = [initial_cash]
    for t in trades:
        if t['type'] == 'SELL':
            equity_curve.append(t['value'])
    
    max_drawdown = 0
    peak = equity_curve[0]
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return {
        'total_trades': total_sells,
        'win_rate': win_rate,
        'total_return': total_return,
        'max_drawdown': max_drawdown,
        'final_value': final_value,
        'trades': trades_df.to_dict('records')
    }

def main():
    p = argparse.ArgumentParser(description='A股策略回测引擎')
    p.add_argument('--strategy', default='sma_crossover', 
                   choices=['sma_crossover', 'rsi', 'macd', 'bollinger'],
                   help='策略类型')
    p.add_argument('--ticker', default='000001.SZ', help='股票代码')
    p.add_argument('--start', default='2025-01-01', help='开始日期 YYYY-MM-DD')
    p.add_argument('--end', default='2025-03-31', help='结束日期 YYYY-MM-DD')
    p.add_argument('--cash', type=float, default=100000, help='初始资金')
    args = p.parse_args()
    
    # 加载数据
    df = load_data(args.ticker, args.start, args.end)
    if df is None:
        return
    
    # 应用策略
    if args.strategy == 'sma_crossover':
        df = calculate_sma_crossover(df)
    elif args.strategy == 'rsi':
        df = calculate_rsi(df)
    elif args.strategy == 'macd':
        df = calculate_macd(df)
    elif args.strategy == 'bollinger':
        df = calculate_bollinger(df)
    
    # 执行回测
    results = run_backtest(df, initial_cash=args.cash)
    
    # 输出结果
    print(f"\n{'='*60}")
    print(f"📈 回测结果: {args.strategy.upper()} | {args.ticker}")
    print(f"{'='*60}")
    print(f"回测区间: {args.start} ~ {args.end}")
    print(f"总交易次数: {results['total_trades']}")
    print(f"胜率: {results['win_rate']:.1f}%")
    print(f"总收益率: {results['total_return']:.2f}%")
    print(f"最大回撤: {results['max_drawdown']:.2f}%")