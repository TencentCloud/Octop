# ai-stock-analyst

AI-powered Chinese A-share stock analyst skill for [OpenClaw](https://github.com/openclaw/openclaw).

Fetches real-time market data, technical indicators, valuations, and news from free Chinese financial data sources, then leverages Claude to generate scored investment analysis reports.

## Features

- **Single stock analysis** — historical prices, MA/RSI/volume technicals, PE/PB valuation, news aggregation
- **Market overview** — major indices (SSE, SZSE, ChiNext), northbound capital flow, sector movers
- **Sector rankings** — top/bottom industry sectors by daily change
- **Batch comparison** — side-by-side valuation lookup for multiple stocks
- **Scoring system** — multi-dimensional score from -5.00 to +5.00 across technical, fundamental, news, and capital flow dimensions

## Data Sources

All free, no API keys required:

| Source | Data |
|--------|------|
| [AkShare](https://github.com/akfamily/akshare) | Historical prices, technicals, indices, sector data, PE/PB |
| Sina Finance | Realtime quotes (fallback) |
| EastMoney | Stock news |
| Xueqiu | Stock news |

## Usage

### Install as OpenClaw Skill

```bash
openclaw skills add ai-stock-analyst
```

### Manual Usage

```bash
pip install akshare

# Single stock analysis
python scripts/stock_data.py 600519 --days 30

# Market overview
python scripts/stock_data.py --market-overview

# Sector rankings
python scripts/stock_data.py --sectors

# Stock news
python scripts/stock_news.py 600519 贵州茅台
```

## How It Works

```
User: "Analyze 600519"
  → stock_data.py fetches prices, technicals, valuation
  → stock_news.py fetches recent news
  → Claude analyzes all data using scoring methodology
  → Structured report with score, analysis, and risks
```

Scripts handle data fetching only. Claude acts as the analyst using the methodology defined in `references/analysis-guide.md` and templates in `references/prompt-templates.md`.

## Requirements

- Python 3.9+
- akshare >= 1.10.0

## License

MIT-0
