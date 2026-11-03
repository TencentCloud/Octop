#!/usr/bin/env python3
"""
行业数据采集辅助脚本
从公开数据源获取行业关键数据，辅助行业研究报告编写。

用法:
    python3 scripts/industry_data_collector.py --industry "AI芯片" --market "CN"
    python3 scripts/industry_data_collector.py --industry "robotics" --market "US"
    python3 scripts/industry_data_collector.py --companies "NVDA,AMD,INTC" --compare
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime


def get_stock_data(ticker: str) -> dict:
    """从Yahoo Finance获取股票基本面数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            return {
                "ticker": ticker,
                "price": meta.get("regularMarketPrice"),
                "currency": meta.get("currency"),
                "exchange": meta.get("exchangeName"),
                "52w_high": meta.get("fiftyTwoWeekHigh"),
                "52w_low": meta.get("fiftyTwoWeekLow"),
            }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def compare_companies(tickers: list) -> list:
    """批量获取公司数据用于对比"""
    results = []
    for ticker in tickers:
        data = get_stock_data(ticker.strip())
        results.append(data)
    return results


def format_comparison_table(companies: list) -> str:
    """格式化为Markdown对比表"""
    if not companies:
        return "No data"
    
    headers = ["指标"] + [c.get("ticker", "?") for c in companies]
    rows = [
        ["当前价格"] + [f'{c.get("price", "N/A")} {c.get("currency", "")}' for c in companies],
        ["52周最高"] + [str(c.get("52w_high", "N/A")) for c in companies],
        ["52周最低"] + [str(c.get("52w_low", "N/A")) for c in companies],
        ["交易所"] + [str(c.get("exchange", "N/A")) for c in companies],
    ]
    
    # Build markdown table
    table = "| " + " | ".join(headers) + " |\n"
    table += "|" + "|".join(["---"] * len(headers)) + "|\n"
    for row in rows:
        table += "| " + " | ".join(row) + " |\n"
    
    return table


def main():
    parser = argparse.ArgumentParser(description="行业数据采集辅助工具")
    parser.add_argument("--industry", type=str, help="行业名称")
    parser.add_argument("--market", type=str, default="CN", help="市场: CN/US/HK")
    parser.add_argument("--companies", type=str, help="公司代码列表(逗号分隔)")
    parser.add_argument("--compare", action="store_true", help="对比模式")
    
    args = parser.parse_args()
    
    if args.companies:
        tickers = args.companies.split(",")
        print(f"\n## 公司数据对比 ({datetime.now().strftime('%Y-%m-%d')})\n")
        companies = compare_companies(tickers)
        print(format_comparison_table(companies))
        
        # Also output raw JSON for further processing
        print("\n<details><summary>原始数据(JSON)</summary>\n")
        print("```json")
        print(json.dumps(companies, indent=2, ensure_ascii=False))
        print("```\n</details>")
    
    elif args.industry:
        print(f"\n## 行业研究数据采集: {args.industry}")
        print(f"市场: {args.market}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"\n⚠️ 注意: 本脚本仅获取股票行情数据。")
        print(f"行业规模、增速等数据需通过web_search从IDC/Gartner等来源获取。")
        print(f"\n建议搜索关键词:")
        print(f'  - "{args.industry} market size {datetime.now().year}"')
        print(f'  - "{args.industry} 市场规模 {datetime.now().year}"')
        print(f'  - "{args.industry} competitive landscape"')
        print(f'  - "{args.industry} industry report"')
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
