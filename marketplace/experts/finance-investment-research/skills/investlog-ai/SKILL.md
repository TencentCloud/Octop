---
name: investlog-ai
version: 1.0.2
homepage: https://api.investlog.ai
description: "美股实时数据研究工具：股价行情、估值分析、财报数据、分析师评级、目标价、内部人交易、国会议员交易、机构持仓、ETF持仓、技术指标、分红拆股、财务健康评分。Real-time US stock research: quotes, valuation, financials, analyst ratings, insider trades, congress trades, fund holdings, ETF exposure, technical analysis, dividends, and financial health. Use when checking stock prices, analyzing earnings, researching who owns a stock, or evaluating if a stock is overvalued. 支持中英文自然语言查询，免费10次，无需API Key。"
---

**AI-powered US stock research API covering 5,700+ stocks. Ask in natural language, get structured financial data.**

## How to use

Use the `web_fetch` tool to query the InvestLog API. The system automatically detects the stock ticker and selects the right data to return.

### Basic query

```
web_fetch url="https://api.investlog.ai/api/v1/query?query=Is+NVDA+overvalued" extractMode=text
```

### Query with specific skill and symbol

For more precise results, specify the skill name and ticker:

```
web_fetch url="https://api.investlog.ai/api/v1/query?query=AAPL+earnings&skill=financials&symbol=AAPL" extractMode=text
```

### Compound analysis (multiple calls)

For comprehensive stock analysis, make multiple calls to combine different data:

```
# 1. Get current price and valuation
web_fetch url="https://api.investlog.ai/api/v1/query?query=NVDA+valuation&skill=valuation&symbol=NVDA" extractMode=text

# 2. Get analyst ratings and price targets
web_fetch url="https://api.investlog.ai/api/v1/query?query=NVDA+analyst+ratings&skill=analyst-view&symbol=NVDA" extractMode=text

# 3. Get recent earnings performance
web_fetch url="https://api.investlog.ai/api/v1/query?query=NVDA+earnings+history&skill=financials&symbol=NVDA" extractMode=text
```

Combine the results from multiple calls to provide a thorough analysis.

## Steps

1. Map user input to query parameters (URL-encode spaces as +)
2. Call the API endpoint using web_fetch
3. Extract data from the `results` array in the response
4. Reply in user's language (Chinese or English)

## Response format

```json
{
  "data": {
    "skill": "valuation",
    "symbol": "NVDA",
    "results": [
      {"tool": "get_stock_quote", "symbol": "NVDA", "data": {"price": 172.7, "change_percent": -3.28}},
      {"tool": "get_financial_ratios", "symbol": "NVDA", "data": {"pe": 34.96, "peg": 0.54}}
    ]
  },
  "usage": {"queries_remaining": 9}
}
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Natural language question about US stocks |
| `skill` | No | Skill name for direct routing (see list below). If omitted, auto-detected from query |
| `symbol` | No | US stock ticker (e.g. NVDA, AAPL). If omitted, extracted from query automatically |

## Available skills

| Skill | What it returns |
|-------|----------------|
| `stock-quote` | Real-time price, daily change, multi-period returns (1D/1M/1Y/5Y) |
| `valuation` | PE, PB, PS, PEG, ROE, margins, FCF yield, DCF intrinsic value |
| `financials` | Income statement, balance sheet, cash flow, growth rates, earnings history |
| `analyst-view` | Analyst ratings, rating trends, price targets, EPS/revenue estimates |
| `company-profile` | Business description, sector, executives, compensation, revenue segmentation |
| `insider-activity` | Insider buy/sell transactions, quarterly insider trading statistics |
| `congress-trades` | US Senate and House stock trading records |
| `fund-exposure` | Institutional 13F holdings, ETF exposure, ETF holdings |
| `financial-health` | Altman Z-Score, Piotroski F-Score, composite financial rating |
| `dividends-splits` | Dividend history, stock splits, shares float |
| `news` | Latest stock-specific news articles |
| `market-overview` | Top gainers/losers/most active, IPO calendar, index constituents (no symbol required) |
| `technicals` | RSI, MACD, SMA, EMA, Bollinger, KDJ, ATR, OBV, CCI, crossover signals |

## Security

- Network: GET requests to https://api.investlog.ai only
- No files read or written on your machine
- No system commands executed
- API key is optional (first 10 queries free, no key needed)

## Setup

- **Free trial**: No setup needed. First 10 queries are free — just start asking.
- **API key**: After free trial, register at https://api.investlog.ai to get your API key and pass it as a query parameter: `&api_key=il_your_key`
- **Plans**: Basic ($9.9/mo, 100 queries/day) | Pro ($19.9/mo, 300 queries/day)

## Output guidelines

- Present data in a clear, readable format
- For list data (holdings, transactions), use tables when possible
- Highlight key metrics and trends
- Include the stock ticker with every data point

## Chinese language support

Supports Chinese natural language queries:
- "巴菲特前十大持仓股票是哪几个？"
- "英伟达的分析师评级是怎么样的？"
- "哪个参议员买了PLTR？"
