---
name: marketpulse
description: 'Query real-time and historical financial data for equities—prices, news, financial statements, metrics, analyst estimates, insider and institutional activity, SEC filings, earnings press releases, segmented revenues, stock screening, and macro interest rates. Use when: the user needs market data, stock analysis, watchlists, or portfolio workflows.'
author: AIsa
version: 1.0.2
license: MIT
user-invocable: true
primaryEnv: AISA_API_KEY
requires:
  bins:
  - python3
  env:
  - AISA_API_KEY
metadata:
  aisa:
    emoji: 📊
    requires:
      bins:
      - python3
      env:
      - AISA_API_KEY
    primaryEnv: AISA_API_KEY
    compatibility:
    - openclaw
    - claude-code
    - hermes
  openclaw:
    emoji: 📊
    requires:
      bins:
      - python3
      env:
      - AISA_API_KEY
    primaryEnv: AISA_API_KEY
---

# MarketPulse 📊

**Complete equity market data for autonomous agents. Powered by AIsa.**

One API key. Stocks, financials, filings, and macro data. Everything you need.

## Compatibility

Works with any [agentskills.io](https://agentskills.io)-compatible
harness, including:

- **Claude Code** and **Claude** (Anthropic)
- **OpenAI Codex**
- **Cursor**
- **Gemini CLI** (Google)
- **OpenCode**, **Goose**, **OpenClaw**, **Hermes**
- and any other harness that implements the [Agent Skills
  specification](https://agentskills.io/specification)

Requires Python 3, a POSIX shell, and `AISA_API_KEY` (get one at
[aisa.one](https://aisa.one)).

## 🔥 What Can You Do?

### Investment Research
```
"Full analysis: NVDA price trends, insider trades, analyst estimates, SEC filings"
```

### Earnings Analysis
```
"Get Tesla earnings press releases, analyst estimates, and price reaction"
```

### Market Screening
```
"Find stocks with P/E < 15 and revenue growth > 20%"
```

### Whale Watching
```
"Track insider trades at Apple and correlate with price movements"
```

### Segment Deep-Dive
```
"Break down Apple's revenue by product segment and geography"
```

## Quick Start

```bash
export AISA_API_KEY="your-key"
```

---

## 🏦 Traditional Finance

### Stock Prices

```bash
# Historical price data (daily)
curl "https://api.aisa.one/apis/v1/financial/prices?ticker=AAPL&interval=day&interval_multiplier=1&start_date=2025-01-01&end_date=2025-12-31" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Weekly price data
curl "https://api.aisa.one/apis/v1/financial/prices?ticker=AAPL&interval=week&interval_multiplier=1&start_date=2025-01-01&end_date=2025-12-31" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Minute-level data (intraday)
curl "https://api.aisa.one/apis/v1/financial/prices?ticker=AAPL&interval=minute&interval_multiplier=5&start_date=2025-01-15&end_date=2025-01-15" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

**Parameters:**
- `ticker`: Stock symbol (required)
- `interval`: `second`, `minute`, `day`, `week`, `month`, `year` (required)
- `interval_multiplier`: Multiplier for interval, e.g., 5 for 5-minute bars (required)
- `start_date`: Start date YYYY-MM-DD (required)
- `end_date`: End date YYYY-MM-DD (required)

### Company News

```bash
# Get news by ticker
curl "https://api.aisa.one/apis/v1/financial/news?ticker=AAPL&limit=10" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### Financial Statements

```bash
# All financial statements (requires period)
curl "https://api.aisa.one/apis/v1/financial/financials?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Income statements
curl "https://api.aisa.one/apis/v1/financial/financials/income-statements?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Balance sheets
curl "https://api.aisa.one/apis/v1/financial/financials/balance-sheets?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Cash flow statements
curl "https://api.aisa.one/apis/v1/financial/financials/cash-flow-statements?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

**Parameters:**
- `ticker`: Stock symbol (required)
- `period`: `annual`, `quarterly`, or `ttm` (required)

### Segmented Revenues

```bash
# Break down revenue by business segment and geography
curl "https://api.aisa.one/apis/v1/financial/financials/segmented-revenues?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

**Parameters:**
- `ticker`: Stock symbol (required)
- `period`: `annual` or `quarterly` (required)

### Financial Metrics

```bash
# Real-time financial metrics snapshot
curl "https://api.aisa.one/apis/v1/financial/financial-metrics/snapshot?ticker=AAPL" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Historical financial metrics (period required)
curl "https://api.aisa.one/apis/v1/financial/financial-metrics?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### Analyst Estimates

```bash
# Earnings per share estimates
curl "https://api.aisa.one/apis/v1/financial/analyst-estimates?ticker=AAPL&period=annual" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### Earnings Press Releases

```bash
# Get earnings press releases
curl "https://api.aisa.one/apis/v1/financial/earnings/press-releases?ticker=NVDA" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

**Note:** This endpoint has narrower ticker coverage than other financial endpoints. Passing an unsupported ticker returns `{"error":"Invalid ticker"}`. See [earnings-press-releases-tickers.md](./earnings-press-releases-tickers.md) for the full list of supported tickers (~2,776 as of 2026-04-14).

### Insider Trading

```bash
# Get insider trades
curl "https://api.aisa.one/apis/v1/financial/insider-trades?ticker=AAPL" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### Institutional Ownership

```bash
# Get institutional ownership (by ticker OR investor)
curl "https://api.aisa.one/apis/v1/financial/institutional-ownership?ticker=AAPL" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### SEC Filings

```bash
# Get SEC filings
curl "https://api.aisa.one/apis/v1/financial/filings?ticker=AAPL" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Get SEC filing items (requires filing type and year)
curl "https://api.aisa.one/apis/v1/financial/filings/items?ticker=AAPL&filing_type=10-K&year=2024" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### Company Facts

```bash
# Get company facts (by ticker or CIK)
curl "https://api.aisa.one/apis/v1/financial/company/facts?ticker=AAPL" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

### Stock Screener

```bash
# Screen for stocks matching criteria
curl -X POST "https://api.aisa.one/apis/v1/financial/financials/search/screener" \
  -H "Authorization: Bearer $AISA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"filters":{"pe_ratio":{"max":15},"revenue_growth":{"min":0.2}}}'
```

### Search Line Items

```bash
# Search specific financial line items across tickers
curl -X POST "https://api.aisa.one/apis/v1/financial/financials/search/line-items" \
  -H "Authorization: Bearer $AISA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tickers":["AAPL","MSFT"],"line_items":["revenue","net_income"],"period":"annual"}'
```

### Interest Rates (Macro)

```bash
# Current interest rates
curl "https://api.aisa.one/apis/v1/financial/macro/interest-rates/snapshot" \
  -H "Authorization: Bearer $AISA_API_KEY"

# Historical interest rates
curl "https://api.aisa.one/apis/v1/financial/macro/interest-rates?bank=fed" \
  -H "Authorization: Bearer $AISA_API_KEY"
```

---

## Python Client

```bash
# ==================== Stock Data ====================
# Note: start_date and end_date are REQUIRED for prices
python3 scripts/market_client.py stock prices --ticker AAPL --start 2025-01-01 --end 2025-01-31
python3 scripts/market_client.py stock prices --ticker AAPL --start 2025-01-01 --end 2025-01-31 --interval week
python3 scripts/market_client.py stock news --ticker AAPL --count 10

# ==================== Financial Statements ====================
python3 scripts/market_client.py stock statements --ticker AAPL --type all --period annual
python3 scripts/market_client.py stock statements --ticker AAPL --type income --period quarterly
python3 scripts/market_client.py stock statements --ticker AAPL --type balance --period annual
python3 scripts/market_client.py stock statements --ticker AAPL --type cash --period ttm

# ==================== Segmented Revenues ====================
python3 scripts/market_client.py stock segments --ticker AAPL --period annual

# ==================== Metrics & Analysis ====================
python3 scripts/market_client.py stock metrics --ticker AAPL
python3 scripts/market_client.py stock metrics --ticker AAPL --historical --period annual
python3 scripts/market_client.py stock analyst --ticker AAPL
python3 scripts/market_client.py stock earnings --ticker AAPL

# ==================== Insider & Institutional ====================
python3 scripts/market_client.py stock insider --ticker AAPL
python3 scripts/market_client.py stock ownership --ticker AAPL

# ==================== SEC Filings ====================
python3 scripts/market_client.py stock filings --ticker AAPL
python3 scripts/market_client.py stock filings --ticker AAPL --items --filing-type 10-K --year 2024

# ==================== Stock Screener / Line Items ====================
python3 scripts/market_client.py stock screen --pe-max 15 --growth-min 0.2
python3 scripts/market_client.py stock line-items --tickers AAPL,MSFT --items revenue,net_income --period annual

# ==================== Interest Rates ====================
python3 scripts/market_client.py stock rates
python3 scripts/market_client.py stock rates --historical --bank fed
```

---

## API Endpoints Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/financial/prices` | GET | Historical stock prices (requires interval params) |
| `/financial/news` | GET | Company news by ticker |
| `/financial/financials` | GET | All financial statements (requires `period`) |
| `/financial/financials/income-statements` | GET | Income statements (requires `period`) |
| `/financial/financials/balance-sheets` | GET | Balance sheets (requires `period`) |
| `/financial/financials/cash-flow-statements` | GET | Cash flow statements (requires `period`) |
| `/financial/financials/segmented-revenues` | GET | Revenue by segment/geography (requires `period`) |
| `/financial/financial-metrics/snapshot` | GET | Real-time financial metrics |
| `/financial/financial-metrics` | GET | Historical metrics (requires `period`) |
| `/financial/analyst-estimates` | GET | EPS estimates |
| `/financial/earnings/press-releases` | GET | Earnings press releases (see [supported tickers](./earnings-press-releases-tickers.md)) |
| `/financial/insider-trades` | GET | Insider trades |
| `/financial/institutional-ownership` | GET | Institutional ownership |
| `/financial/filings` | GET | SEC filings |
| `/financial/filings/items` | GET | SEC filing items (requires `filing_type`, `year`) |
| `/financial/company/facts` | GET | Company facts |
| `/financial/financials/search/screener` | POST | Stock screener |
| `/financial/financials/search/line-items` | POST | Search specific line items across tickers |
| `/financial/macro/interest-rates/snapshot` | GET | Current interest rates |
| `/financial/macro/interest-rates` | GET | Historical rates |

---

## Pricing

| API | Cost |
|-----|------|
| Stock prices | ~$0.001 |
| Company news | ~$0.001 |
| Financial statements | ~$0.002 |
| Segmented revenues | ~$0.002 |
| Analyst estimates | ~$0.002 |
| Earnings press releases | ~$0.001 |
| SEC filings | ~$0.001 |
| Line items / screener | ~$0.002 |
| Interest rates | ~$0.0005 |

---

## Get Started

1. Sign up at [aisa.one](https://aisa.one)
2. Get your API key
3. Add credits (pay-as-you-go)
4. Set environment variable: `export AISA_API_KEY="your-key"`

## Full API Reference

See [API Reference](https://aisa.one/docs/api-reference/) for complete endpoint documentation.
