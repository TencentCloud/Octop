#!/usr/bin/env python3
"""
每周金融投研报告生成器 - 主入口
用法: python generate_weekly_report.py --stocks 000001,600519 [--date 2026-03-14] [--author 名字]
"""
import argparse
import sys
import os
from datetime import datetime

import pandas as pd

from data_fetcher import (
    get_week_range,
    fetch_stock_hist_extended,
    fetch_index_hist_extended,
    fetch_stock_name_from_spot,
    fetch_market_breadth,
    fetch_north_flow,
    fetch_macro_news,
    fetch_stock_news,
)
from technical_analysis import analyze_stock
from report_generator import generate_report, render_pdf


# 常用指数 (新浪格式)
INDICES = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "沪深300": "sh000300",
    "创业板指": "sz399006",
}


def fetch_index_summary(start_date: str, end_date: str) -> dict:
    """获取主要指数本周表现"""
    result = {}
    for name, code in INDICES.items():
        try:
            df = fetch_index_hist_extended(code, days=30)
            if df.empty:
                result[name] = {}
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            pct = (latest["close"] / prev["close"] - 1) * 100
            result[name] = {
                "close": f"{latest['close']:.2f}",
                "pct_change": f"{pct:.2f}",
                "high": f"{latest['high']:.2f}",
                "low": f"{latest['low']:.2f}",
                "volume": f"{latest['volume'] / 1e8:.2f}亿",
            }
        except Exception as e:
            print(f"  [WARN] 获取{name}数据失败: {e}", file=sys.stderr)
            result[name] = {}
    return result


def fetch_north_summary(start_date: str, end_date: str) -> dict:
    """北向资金汇总"""
    try:
        df = fetch_north_flow(start_date, end_date)
        if df.empty:
            return {"total": 0}
        # net_flow 单位是万元，转亿
        total = df["net_flow"].sum()
        if abs(total) > 1e6:
            total = total / 1e4  # 万 -> 亿
        return {"total": total}
    except Exception:
        return {"total": 0}


def main():
    parser = argparse.ArgumentParser(description="每周金融投研报告生成器")
    parser.add_argument("--stocks", required=True, help="股票代码，逗号分隔，如: 000001,600519,000858")
    parser.add_argument("--date", default=None, help="报告日期，默认今天，格式: YYYY-MM-DD")
    parser.add_argument("--author", default="AI投研助手", help="作者名称")
    parser.add_argument("--output", default=None, help="输出文件路径，默认 output/周报_日期.md")
    parser.add_argument("--skip-breadth", action="store_true", help="跳过市场涨跌统计（较慢）")
    args = parser.parse_args()

    report_date = args.date or datetime.now().strftime("%Y-%m-%d")
    stock_list = [s.strip() for s in args.stocks.split(",") if s.strip()]
    week_range = get_week_range(report_date)

    print(f"=== 每周金融投研报告生成器 ===")
    print(f"报告日期: {report_date}")
    print(f"报告周期: {week_range[0]} - {week_range[1]}")
    print(f"跟踪标的: {stock_list}")
    print()

    # 1. 获取指数数据
    print("[1/5] 获取主要指数数据...")
    index_data = fetch_index_summary(week_range[0], week_range[1])

    # 2. 获取市场情绪
    market_breadth = {}
    if not args.skip_breadth:
        print("[2/5] 获取市场情绪指标（约1分钟）...")
        market_breadth = fetch_market_breadth()
    else:
        print("[2/5] 跳过市场情绪指标")

    # 3. 获取北向资金
    print("[3/5] 获取北向资金数据...")
    north_flow = fetch_north_summary(week_range[0], week_range[1])

    # 4. 获取个股数据并分析
    print("[4/5] 获取个股数据并进行技术分析...")
    stock_signals = []
    stock_dfs = {}  # 保存 DataFrame 用于图表生成
    for symbol in stock_list:
        try:
            name = fetch_stock_name_from_spot(symbol)
            print(f"  - 分析 {name}({symbol})...")
            df = fetch_stock_hist_extended(symbol, days=90)
            sig = analyze_stock(df, symbol, name)
            stock_signals.append(sig)
            stock_dfs[symbol] = df
        except Exception as e:
            print(f"  [WARN] {symbol} 分析失败: {e}", file=sys.stderr)

    # 5. 获取持仓相关新闻 + 宏观要闻
    print("[5/6] 获取持仓相关新闻...")
    stock_news = {}
    for symbol in stock_list:
        try:
            news = fetch_stock_news(symbol, count=3)
            if news:
                stock_news[symbol] = news
                print(f"  - {symbol}: {len(news)} 条新闻")
        except Exception:
            pass

    print("[6/6] 获取宏观要闻...")
    headlines = fetch_macro_news()

    # 生成报告
    print("\n正在生成报告...")
    report = generate_report(
        report_date=report_date,
        week_range=week_range,
        index_data=index_data,
        stock_signals=stock_signals,
        sector_flow=[],  # 板块资金流向在当前网络不可用，留空
        market_breadth=market_breadth,
        north_flow_summary=north_flow,
        macro_headlines=headlines,
        author=args.author,
        stock_dfs=stock_dfs,
        stock_news=stock_news,
    )

    # 输出 PDF
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = args.output or os.path.join(output_dir, f"周报_{report_date}.pdf")

    print(f"\n正在渲染 PDF...")
    render_pdf(report, output_path)

    print(f"报告已生成: {output_path}")
    file_size = os.path.getsize(output_path)
    print(f"文件大小: {file_size / 1024:.1f} KB")
    return output_path


if __name__ == "__main__":
    main()
