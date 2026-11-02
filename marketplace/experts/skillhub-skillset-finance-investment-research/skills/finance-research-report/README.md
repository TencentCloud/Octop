# finance-research-report

> OpenClaw skill — A股每周金融投研报告生成器，自动生成专业券商研报风格的 PDF 报告。

## What it does

- 生成专业券商研报风格的 **PDF 报告**（A4 页面）
- 多标的技术分析：均线、RSI、MACD、KDJ、ATR 等指标
- 交易信号判断：买入/卖出信号、信号强度评估
- 风险评估与仓位建议：止损止盈、风险评分、仓位系数
- 数据可视化：价格走势图、MACD+RSI 图表、指数对比图
- 市场概览：大盘指数、北向资金、涨跌家数、持仓新闻

## Installation

```bash
clawhub install finance-research-report
```

Or search and install from within OpenClaw:

```bash
clawhub search finance-research-report
```

Once installed, use `/finance-research-report` in any OpenClaw session.

### System dependencies (macOS)

```bash
brew install pango ghostscript
```

## Quick start

```
/finance-research-report 000001,600519,000858
/finance-research-report 600519 --date 2026-03-14
/finance-research-report 000858,000333,601318 --author 投研团队
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| 股票代码 | Yes | 逗号分隔的 A 股代码，如 `000001,600519` |
| `--date` | No | 报告日期 (YYYY-MM-DD)，默认今天 |
| `--author` | No | 作者名称，默认 "AI投研助手" |
| `--skip-breadth` | No | 跳过全市场涨跌统计（更快） |

## Requirements

- `python3` on PATH
- `pango` — weasyprint PDF 渲染依赖
- `ghostscript` — PDF 兼容性优化（macOS Preview）
- No API keys needed — data fetched via AKShare public APIs

## Data sources

| Data | Source |
|------|--------|
| A 股日线行情、指数、实时行情 | 新浪财经 |
| 北向资金、个股新闻、宏观要闻 | 东方财富 |

## Report structure

1. Cover page with key findings & signal summary
2. Table of contents
3. Market overview (indices, breadth, northbound capital, news)
4. Individual stock technical analysis (with charts)
5. Trading signal summary
6. Risk assessment & position sizing
7. Risk disclaimer

## Disclaimer

This skill provides informational analysis only and does not constitute financial advice. Data sourced from AKShare / Sina Finance / Eastmoney.
